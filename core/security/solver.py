"""Evidence-gated Python repair; callers hold the checkout investigation lock."""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys

from core.domain.types import now
from core.security.models import SecuritySolution
from core.security.repair import literal_parser_patch
from infrastructure.repository.git import git
from infrastructure.repository.patches import apply_edits
from infrastructure.safety.guardrails.commands import run, parse
from infrastructure.safety.sandbox.worktree import Worktree, source_signature
from infrastructure.security.bandit import source_bytes, audit_repository, MAX_FILES, MAX_TOTAL_BYTES
from infrastructure.security.review import inventory


def test_command(command: str) -> str:
    argv = parse(command, agent=True)
    # Use Ghost's known interpreter; accept only familiar test runners.
    if argv[0] == 'pytest':
        tail = ['-m', 'pytest', *argv[1:]]
    elif Path(argv[0]).name in {'python', 'python3', 'python3.12', Path(sys.executable).name} and argv[1:3] in (['-m', 'pytest'], ['-m', 'unittest']):
        tail = argv[1:]
    else:
        raise ValueError('Use --tests "python -m pytest ..." or "python -m unittest discover -v".')
    return shlex.join([sys.executable, *tail])


def passed_tests(output: str) -> int:
    unittest = re.search(r'(?m)^Ran (\d+) tests? in .+\n\s*\nOK(?:\s|$)', output)
    pytest = re.search(r'(\d+) passed(?:[,\s]|$)', output)
    # A recipe is not verified by zero tests or a suite with skipped/error cases.
    if re.search(r'\b(skipped|xfailed|xpassed|deselected|failed|errors?)\b', output, re.I):
        return 0
    return int((unittest or pytest).group(1)) if unittest or pytest else 0


def solve(repo: Path, db, audit, finding, tests: str, *, timeout: int = 120) -> SecuritySolution:
    result = SecuritySolution(audit_id=audit.id, finding_id=finding.id)
    db.save_solution(result)
    try:
        if os.getenv('GHOST_DISABLE_OS_SANDBOX') == '1':
            raise ValueError('Security repairs require OS confinement. Unset GHOST_DISABLE_OS_SANDBOX.')
        if audit.status != 'completed':
            raise ValueError('Complete ghost find before requesting a repair.')
        if finding.rule != 'B307':
            raise ValueError('No verified repair recipe for this rule yet. Python standalone literal parsers (B307) are supported first.')
        content = source_bytes(repo, finding.path)
        if hashlib.sha256(content).hexdigest() != finding.file_sha256:
            raise ValueError('Finding is stale. Rerun ghost find.')
        edit = literal_parser_patch(finding.path, content.decode('utf-8'), finding.line)
        command = test_command(tests)
        result.base_commit = git(repo, 'rev-parse', 'HEAD').strip()
        result.source_signature = source_signature(repo)
        with Worktree(repo) as sandbox:
            if source_signature(repo) != result.source_signature or source_bytes(sandbox, finding.path) != content:
                raise ValueError('Source changed while preparing the sandbox. Rerun ghost find.')
            selected = inventory(sandbox)
            if len(selected) > MAX_FILES:
                raise ValueError('Repair snapshot exceeds the 1,000-file budget.')
            original_files = {}
            total = 0
            for path in sorted(selected):
                data = source_bytes(sandbox, path)
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise ValueError('Repair snapshot exceeds the 16 MB budget.')
                original_files[path] = data
            result.status = 'failed'
            def check_snapshot(check):
                # Test-generated files can change imports/fixtures just as edits
                # to existing files can. Ignore only the established scan scope.
                try:
                    unchanged = (inventory(sandbox) == selected and all(
                        source_bytes(sandbox, path) == data
                        for path, data in original_files.items()))
                except (OSError, ValueError):
                    unchanged = False
                check['snapshot_unchanged'] = unchanged
                db.save_solution(result)
                if not unchanged:
                    raise ValueError(f"{check['label']} changed project files; refusing verification. "
                                     'Keep generated fixtures and build output outside the reviewed source scope.')

            def execute(label, cmd):
                outcome = run(cmd, sandbox, timeout=timeout, output_limit=64_000, agent=True)
                check = {'label': label, 'exit_code': outcome.exit_code, 'duration': outcome.duration,
                         'sandboxed': outcome.sandboxed, 'timed_out': outcome.timed_out,
                         'output_truncated': outcome.output_truncated}
                result.checks.append(check)
                db.save_solution(result)
                if outcome.exit_code or outcome.timed_out or outcome.output_truncated or not outcome.sandboxed:
                    raise ValueError(f'{label} did not pass its execution policy. No verified fix is available.')
                check_snapshot(check)
                return outcome, check
            def probe(mode):
                cmd = shlex.join([sys.executable, '-I', '-m', 'infrastructure.security.probe', finding.path, mode])
                output, check = execute(f'{mode} security probe', cmd)
                facts = json.loads(output.stdout)
                check['facts'] = facts
                expected = {'literal_cases': 3, 'literals_preserved': True,
                            'function_call_executed': mode == 'original', 'function_call_rejected': mode == 'patched'}
                if facts != expected:
                    raise ValueError('Security probe did not establish the expected behavior.')
            baseline, check = execute('baseline project tests', command)
            count = passed_tests(baseline.stdout + '\n' + baseline.stderr)
            check['passed_tests'] = count
            if count < 1:
                raise ValueError('Baseline needs passing tests with a recognized summary and no skipped cases.')
            probe('original')
            apply_edits(sandbox, [edit])
            # The proposed edit is the only permitted change in the snapshot.
            expected = content.decode('utf-8').replace(edit.old, edit.new, 1).encode('utf-8')
            original_files[finding.path] = expected
            probe('patched')
            verified, check = execute('patched project tests', command)
            check['passed_tests'] = passed_tests(verified.stdout + '\n' + verified.stderr)
            if check['passed_tests'] != count:
                raise ValueError('Patched test coverage did not match the passing baseline.')
            scan = audit_repository(sandbox, timeout=timeout)
            result.checks.append({'label': 'Python rescan', 'status': scan.status,
                                  'target_rule_absent': not any(f.rule == 'B307' and f.path == finding.path for f in scan.findings)})
            check_snapshot(result.checks[-1])
            if scan.status != 'completed' or not result.checks[-1]['target_rule_absent']:
                raise ValueError('Patched Python rescan did not confirm removal of the target rule.')
            if source_signature(repo) != result.source_signature or git(repo, 'rev-parse', 'HEAD').strip() != result.base_commit:
                raise ValueError('Developer checkout changed during verification. Rerun ghost find.')
            result.patch = [edit]
        result.status = 'verified'
        result.notes.append('Helper-level proof: function-call evaluation reproduced, then rejected; three literal cases preserved. Application reachability is not established.')
        result.notes.append('This repair intentionally rejects expressions. Review whether the function is intended to parse literals. Project tests are trusted code; their coverage is not a security guarantee.')
    except ValueError as exc:
        result.notes.append(str(exc))
    except Exception:
        result.status = 'failed'
        result.notes.append('Repair stopped safely. Check ghost doctor. No verified patch was applied; inspect git worktree list for leftover worktrees.')
    finally:
        result.finished_at = now()
        db.save_solution(result)
    return result


def apply_solution(repo: Path, db, result: SecuritySolution) -> None:
    if result.status != 'verified' or not result.patch:
        raise ValueError('Only a verified patch can be applied.')
    if source_signature(repo) != result.source_signature or git(repo, 'rev-parse', 'HEAD').strip() != result.base_commit:
        raise ValueError('Checkout changed after verification. Rerun ghost find and ghost solve.')
    apply_edits(repo, result.patch)
    result.status = 'applied'
    db.save_solution(result)
