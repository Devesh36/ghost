"""Bound Bandit's raw report and emit only the metadata Ghost needs."""
import json
import os
import resource
import signal
import subprocess
import sys
import tempfile


MAX_REPORT_BYTES = 8_000_000
REPORT_TOO_LARGE = 3
FIELDS = ('filename', 'test_id', 'test_name', 'line_number', 'issue_severity', 'issue_confidence')


def compact_report(data):
    if (not isinstance(data, dict) or not isinstance(data.get('results'), list)
            or not isinstance(data.get('errors'), list) or not isinstance(data.get('metrics'), dict)):
        raise ValueError('Invalid scanner report')
    results = []
    for item in data['results']:
        result = {key: item[key] for key in FIELDS}
        result['issue_cwe'] = {'id': (item.get('issue_cwe') or {}).get('id')}
        results.append(result)
    # Preserve error counts and per-file accounting; discard messages and excerpts.
    return {'results': results, 'errors': [{} for _ in data['errors']], 'metrics': data['metrics']}


def main():
    _, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    ceiling = MAX_REPORT_BYTES if hard == resource.RLIM_INFINITY else min(MAX_REPORT_BYTES, hard)
    resource.setrlimit(resource.RLIMIT_FSIZE, (ceiling, ceiling))
    with tempfile.TemporaryFile(mode='w+b') as report:
        outcome = subprocess.run(
            [sys.executable, '-I', '-m', 'bandit', '-q', '-r', 'scan', '-f', 'json',
             '--ignore-nosec', '--ini', os.devnull, '--configfile', 'scanner.yaml'],
            stdout=report, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=False)
        if outcome.returncode == -signal.SIGXFSZ or os.fstat(report.fileno()).st_size >= ceiling:
            return REPORT_TOO_LARGE
        if outcome.returncode not in {0, 1}:
            return 2
        report.seek(0)
        try:
            data = compact_report(json.loads(report.read(MAX_REPORT_BYTES + 1)))
        except (ValueError, KeyError, TypeError, AttributeError):
            return 2
        sys.stdout.write(json.dumps(data, separators=(',', ':')))
        return outcome.returncode


if __name__ == '__main__':
    raise SystemExit(main())
