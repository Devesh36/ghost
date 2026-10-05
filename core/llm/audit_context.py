"""Bounded, explicitly selected audit metadata for advisory conversations."""
import json
import re

from core.security.models import SecurityAudit

CONTEXT_BYTES = 24_576
FINDINGS_LIMIT = 20
VERDICTS_LIMIT = 20
FIELDS = {'id', 'rule', 'path', 'line', 'severity', 'confidence', 'state'}


def encoded_size(value) -> int:
    # ASCII JSON bounds escaped controls and Unicode as well as ordinary paths.
    return len(json.dumps(value, ensure_ascii=True).encode('utf-8'))


def audit_context(audit: SecurityAudit | None, *, finding: str | None = None) -> dict:
    if finding is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', finding):
        raise ValueError('Use a full finding ID or unique prefix from ghost findings --json.')
    if audit is None:
        if finding is not None:
            raise ValueError('No saved audit. Run ghost find before asking about a finding.')
        return {'status': 'no saved audit'}
    selected = audit.findings[:FINDINGS_LIMIT]
    if finding is not None:
        exact = [item for item in audit.findings if item.id == finding]
        selected = exact or [item for item in audit.findings if item.id.startswith(finding)]
        if len(selected) != 1:
            raise ValueError('Finding ID missing or ambiguous in the latest audit. '
                             'Run ghost findings --json and use a full ID or unique prefix.')
    truncated = []

    def text(name, value, limit):
        if len(value) > limit:
            truncated.append(name)
            return value[:limit]
        return value

    verdicts = [] if finding is not None else [item.verdict for item in audit.authorization[:VERDICTS_LIMIT]]
    result = {'id': text('id', audit.id, 128), 'started_at': text('started_at', audit.started_at, 64),
              'status': audit.status, 'scope': text('scope', audit.scope, 1024),
              'files_scanned': len(audit.files), 'unsupported_files': audit.unsupported_files,
              'excluded_files': audit.excluded_files, 'total_static_findings': len(audit.findings),
              'findings_limit': 1 if finding is not None else FINDINGS_LIMIT,
              'static_findings': [], 'findings_omitted': len(audit.findings),
              'authorization_verdicts': verdicts,
              'authorization_verdicts_omitted': len(audit.authorization) - len(verdicts),
              'context_bytes_limit': CONTEXT_BYTES, 'truncated_fields': truncated}
    for item in selected:
        row = item.model_dump(include=FIELDS)
        # Avoid serializing arbitrarily large saved strings before the byte check.
        if any(isinstance(value, str) and len(value) > CONTEXT_BYTES for value in row.values()):
            fits = False
        else:
            candidate = {**result, 'static_findings': [*result['static_findings'], row],
                         'findings_omitted': result['findings_omitted'] - 1}
            fits = encoded_size(candidate) <= CONTEXT_BYTES
        if fits:
            result = candidate
        elif finding is not None:
            raise ValueError('Selected finding metadata exceeds the chat context limit. '
                             'Inspect it locally with ghost findings --id <id>.')
    return result
