"""Local bundled JS/TS checks; no registry downloads, metrics, or project config."""
import hashlib
import json
from pathlib import Path
import shlex
import sys
import config
from core.security.models import SecurityFinding

EXTENSIONS = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts'}
RULES = {
    'GJS001': ('Dynamic expression evaluation', 'MEDIUM', 95),
    'GJS002': ('Dynamic function construction', 'MEDIUM', 95),
    'GJS003': ('Shell command execution', 'MEDIUM', 78),
    'GJS004': ('TLS certificate verification disabled', 'HIGH', 295),
}


def command(workspace: Path) -> str:
    rules = Path(config.__file__).parent / 'security_rules.yaml'
    (workspace / 'scanner.yaml').write_bytes(rules.read_bytes())
    return shlex.join([sys.executable, '-I', '-m', 'infrastructure.security.semgrep_worker', 'scan', '--config', 'scanner.yaml',
                      '--metrics', 'off', '--disable-version-check', '--disable-nosem', '--no-git-ignore',
                      '--no-rewrite-rule-ids', '--strict', '--optimizations', 'none', '--json', '--quiet', '--jobs', '1',
                      '--max-target-bytes', '512000', 'scan'])


def parse_report(payload: str, mapping: dict[str, str], audit) -> bool:
    data = json.loads(payload)
    if not isinstance(data.get('results'), list) or not isinstance(data.get('errors'), list):
        raise ValueError('Invalid scanner report')
    if set(data.get('paths', {}).get('scanned', [])) != set(mapping):
        raise ValueError('Scanner skipped selected files')
    for item in data['results']:
        rule = item['check_id']
        title, severity, cwe = RULES[rule]
        path = mapping[item['path']]
        line = item['start']['line']
        identity = hashlib.sha256(f'{path}\0{rule}\0{line}\0{audit.files[path]}'.encode()).hexdigest()[:20]
        audit.findings.append(SecurityFinding(id=identity, rule=rule, title=title, path=path, line=line,
            severity=severity, confidence='MEDIUM', cwe=cwe, file_sha256=audit.files[path]))
    if data['errors']:
        audit.notes.append('JavaScript/TypeScript parsing or scanner errors occurred; review is incomplete.')
        return False
    return True
