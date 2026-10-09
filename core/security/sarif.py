"""Export saved static evidence without reading source or invoking tools."""
import hashlib
import json
import re
from urllib.parse import quote

from core.security.models import SecurityAudit


LEVEL = {'HIGH': 'error', 'MEDIUM': 'warning', 'LOW': 'note', 'UNDEFINED': 'none'}


def source_uri(path: str) -> str:
    # Always a relative URI. Encoding prevents filenames becoming remote links,
    # URI queries/fragments or a consumer's interpretation of percent escapes.
    if not path or any(part in {'', '.', '..'} for part in path.split('/')) or '\\' in path:
        raise ValueError('Cannot export an unsafe source path from saved evidence.')
    try:
        return quote(path, safe='/')
    except UnicodeError:
        raise ValueError('Cannot export an invalid source path from saved evidence.') from None


def digest(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def audit_sarif(audit: SecurityAudit, *, version: str) -> dict:
    """Format version 1: all static results, with coverage and provenance separate."""
    paths = sorted(set(audit.files) | {finding.path for finding in audit.findings})
    indices = {path: index for index, path in enumerate(paths)}
    artifacts = []
    for path in paths:
        artifact = {'location': {'uri': source_uri(path)}, 'roles': ['analysisTarget']}
        if digest(audit.files.get(path)):
            artifact['hashes'] = {'sha-256': audit.files[path]}
        artifacts.append(artifact)
    rules = sorted({finding.rule for finding in audit.findings})
    rule_indices = {rule: index for index, rule in enumerate(rules)}
    results = []
    for finding in audit.findings:
        identity = json.dumps([finding.rule, finding.path, finding.line, finding.file_sha256],
                              ensure_ascii=True, separators=(',', ':')).encode('utf-8')
        properties = {'findingId': finding.id, 'staticSeverity': finding.severity,
                      'staticConfidence': finding.confidence, 'evidence': 'static', 'state': 'suspected',
                      'sourceIdentityConsistent': digest(finding.file_sha256)
                      and audit.files.get(finding.path) == finding.file_sha256}
        if digest(finding.file_sha256):
            properties['recordedFileSha256'] = finding.file_sha256
        if finding.cwe is not None:
            properties['cwe'] = finding.cwe
        results.append({
            'ruleId': finding.rule, 'ruleIndex': rule_indices[finding.rule],
            'kind': 'review', 'level': LEVEL[finding.severity],
            'message': {'text': f'{finding.rule}: suspected static candidate; application exploitability was not verified.'},
            'locations': [{'physicalLocation': {
                'artifactLocation': {'uri': source_uri(finding.path), 'index': indices[finding.path]},
                'region': {'startLine': finding.line}}}],
            'partialFingerprints': {'ghost/source-location/v1': hashlib.sha256(identity).hexdigest()},
            'properties': properties,
        })
    warnings = []
    if audit.status != 'completed':
        warnings.append('The saved review is incomplete; resolve its diagnostic notes in Ghost before relying on coverage.')
    if not audit.sandboxed:
        warnings.append('Scanner confinement was not recorded in this saved review.')
    if not audit.finished_at or not audit.files or any(not digest(value) for value in audit.files.values()):
        warnings.append('Finished source inventory or valid source hashes are missing from saved evidence.')
    if any(not result['properties']['sourceIdentityConsistent'] for result in results):
        warnings.append('Some finding hashes do not match the recorded source inventory.')
    static_runs = [run for run in audit.engine_runs if run.get('engine') != 'local authorization contract']
    versions_recorded = (all(isinstance(run.get('version'), str) and run['version'] for run in static_runs)
                         if static_runs else bool(audit.engine_version))
    if not versions_recorded or not digest(audit.configuration_sha256):
        warnings.append('Scanner version or configuration identity is missing from saved evidence.')
    if any(run.get('status') != 'completed' for run in static_runs):
        warnings.append('A recorded static scanner run is incomplete.')
    if audit.unsupported_files or audit.excluded_files:
        warnings.append('Unsupported or excluded paths were outside the selected static review coverage.')
    properties = {
        'exportFormatVersion': 1, 'auditId': audit.id, 'startedAt': audit.started_at,
        'auditStatus': audit.status, 'baseCommit': audit.base_commit, 'scope': audit.scope,
        'scanner': audit.engine, 'scannerVersion': audit.engine_version,
        'sourceFiles': len(audit.files), 'staticCandidates': len(audit.findings),
        'unsupportedFiles': audit.unsupported_files, 'excludedPaths': audit.excluded_files,
        'diagnosticNotesOmitted': len(audit.notes), 'currentSourceRechecked': False,
        'authorizationResultsOmitted': len(audit.authorization),
        'authorizationCandidateResultsOmitted': len(audit.authorization_candidate),
        'coverageWarnings': warnings,
    }
    if digest(audit.configuration_sha256):
        properties['configurationSha256'] = audit.configuration_sha256
    if audit.finished_at:
        properties['finishedAt'] = audit.finished_at
    # Engine runs can contain diagnostic messages. Export only typed provenance.
    properties['scannerRuns'] = [
        {key: run[key] for key in ('engine', 'version', 'scope', 'status', 'configuration_sha256')
         if isinstance(run.get(key), str)}
        for run in static_runs
    ]
    return {
        '$schema': 'https://json.schemastore.org/sarif-2.1.0.json', 'version': '2.1.0',
        'runs': [{
            'tool': {'driver': {'name': 'Ghost', 'version': version,
                              'informationUri': 'https://github.com/Devesh36/ghost',
                              'rules': [{'id': rule, 'shortDescription': {'text': f'{rule} static candidate'}}
                                        for rule in rules]}},
            'artifacts': artifacts, 'results': results, 'properties': properties,
            'invocations': [{
                'executionSuccessful': (audit.status == 'completed' and audit.sandboxed
                                        and all(run.get('status') == 'completed' for run in static_runs)),
                'toolExecutionNotifications': [{'level': 'warning', 'message': {'text': message}}
                                              for message in warnings],
            }],
        }],
    }
