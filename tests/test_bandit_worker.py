"""Compact scanner transport retains complete evidence and bounds raw output."""
import json
import subprocess
import sys

from infrastructure.security import bandit
from infrastructure.security.bandit_worker import compact_report, REPORT_TOO_LARGE
from surfaces.cli.commands.demo import create_demo


def test_compaction_omits_source_and_messages_without_losing_accounting():
    report = {'results': [{'filename': 'scan/0000.py', 'test_id': 'B307', 'test_name': 'eval',
                          'line_number': 2, 'issue_severity': 'HIGH', 'issue_confidence': 'HIGH',
                          'issue_cwe': {'id': 95, 'link': 'not-needed'},
                          'code': 'DO_NOT_EXPORT_SOURCE', 'issue_text': 'DO_NOT_EXPORT_MESSAGE'}],
              'errors': [{'reason': 'DO_NOT_EXPORT_ERROR'}],
              'metrics': {'scan/0000.py': {'loc': 10}, '_totals': {'loc': 10}}}
    compact = compact_report(report)
    assert compact['metrics'] == report['metrics']
    assert len(compact['errors']) == 1 and compact['errors'][0] == {}
    assert compact['results'][0]['test_id'] == 'B307'
    assert compact['results'][0]['issue_cwe'] == {'id': 95}
    assert 'DO_NOT_EXPORT' not in json.dumps(compact)


def test_large_real_scan_keeps_every_finding_without_exporting_source(tmp_path):
    repo = create_demo(tmp_path / 'project', broken=False)
    (repo / 'many.py').write_text(''.join(
        f'assert True  # DO_NOT_EXPORT_SOURCE_{number}\n' for number in range(3000)))
    audit = bandit.audit_repository(repo)
    candidates = [item for item in audit.findings if item.path == 'many.py' and item.rule == 'B101']
    assert audit.status == 'completed', audit.notes
    assert audit.sandboxed and len(candidates) == 3000
    assert {item.line for item in candidates} == set(range(1, 3001))
    assert 'DO_NOT_EXPORT_SOURCE' not in audit.model_dump_json()


def test_worker_fails_closed_when_native_report_hits_the_bound(tmp_path):
    # Exercise the worker in a subprocess: its file-size limit must not affect pytest.
    script = tmp_path / 'probe.py'
    script.write_text(
        'import subprocess\n'
        'from infrastructure.security import bandit_worker as worker\n'
        'def oversized(*args, **kwargs):\n'
        '    kwargs["stdout"].truncate(worker.MAX_REPORT_BYTES)\n'
        '    return subprocess.CompletedProcess(args, 1)\n'
        'worker.subprocess.run = oversized\n'
        'raise SystemExit(worker.main())\n')
    outcome = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=False)
    assert outcome.returncode == REPORT_TOO_LARGE
    assert outcome.stdout == '' and outcome.stderr == ''
