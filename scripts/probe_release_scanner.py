"""Diagnose a confined JS scanner on a fixed synthetic fixture, never a project."""
import hashlib
import json
from pathlib import Path
import tempfile

from core.security.models import SecurityAudit
from infrastructure.security import semgrep
from infrastructure.safety.guardrails.commands import run


def main():
    source = b'eval(value);\n'
    with tempfile.TemporaryDirectory(prefix='ghost-release-probe-') as temporary:
        workspace = Path(temporary).resolve()
        (workspace / 'scan').mkdir()
        (workspace / 'scan/0000.js').write_bytes(source)
        outcome = run(semgrep.command(workspace), workspace, timeout=60, output_limit=1_000_000, agent=True)
        data = json.loads(outcome.stdout)
        print(json.dumps({'exit_code': outcome.exit_code, 'sandboxed': outcome.sandboxed,
                          'paths': data.get('paths'),
                          'rule_ids': [item.get('check_id') for item in data.get('results', [])],
                          'errors': data.get('errors', [])}))
        audit = SecurityAudit(files={'fixture.js': hashlib.sha256(source).hexdigest()})
        assert outcome.sandboxed and not outcome.timed_out and not outcome.output_truncated
        assert outcome.exit_code in {0, 1}
        assert semgrep.parse_report(outcome.stdout, {'scan/0000.js': 'fixture.js'}, audit)
        assert any(item.rule == 'GJS001' for item in audit.findings)


if __name__ == '__main__':
    main()
