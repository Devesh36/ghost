"""Test model proposals in isolation without promoting tests to security proof."""
import hashlib
import json
import os
import sys
from pathlib import Path

from core.domain.types import PatchEdit, now
from core.security.assistance import MAX_SOURCE_BYTES, Replacement, request
from core.security.models import SecuritySolution
from core.security.test_runners import RunnerKind, TestRunnerError, select_runner
from infrastructure.repository.git import git
from infrastructure.repository.patches import apply_edits
from infrastructure.safety.guardrails.commands import run
from infrastructure.safety.masking.model_input import sensitive_path, validate_model_input
from infrastructure.safety.sandbox.worktree import Worktree, source_signature
from infrastructure.security.bandit import MAX_FILES, MAX_TOTAL_BYTES, source_bytes
from infrastructure.security.review import find_risks, inventory


class RepairBlocked(ValueError):
    """A host-written, safe reason that a proposal cannot qualify."""


def eligible_target(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name.lower()
    return (not Path(path).is_absolute() and not sensitive_path(path)
            and not any(p.casefold() in {'..', '.git', '.ghost', 'test', 'tests', '__tests__'} for p in parts)
            and not name.startswith(('test_', 'conftest.'))
            and name not in {'test.py', 'tests.py'} and not name.endswith('_test.py')
            and not any(marker in name for marker in ('.test.', '.spec.'))
            and Path(path).suffix.lower() in {'.py', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.mts', '.cts'})


def solve_with_llm(repo, db, audit, finding, tests, provider, *, timeout=120):
    result = SecuritySolution(audit_id=audit.id, finding_id=finding.id, method='llm',
                              selected_test_command=tests if isinstance(tests, str) and len(tests) <= 4096 else None)
    db.save_solution(result)
    try:
        if os.getenv('GHOST_DISABLE_OS_SANDBOX') == '1':
            raise RepairBlocked('LLM repairs require OS confinement.')
        if audit.status != 'completed' or not eligible_target(finding.path):
            raise RepairBlocked('LLM repairs need a complete scan and an eligible application source file; test files are excluded.')
        runner = select_runner(tests, finding.path, repo)
        command = runner.command
        result.test_runner = runner.kind
        result.test_command = list(runner.argv)
        if runner.kind != RunnerKind.NODE:
            result.test_runner_version = sys.version.split()[0]
        content = source_bytes(repo, finding.path)
        if (hashlib.sha256(content).hexdigest() != finding.file_sha256
                or git(repo, 'rev-parse', 'HEAD').strip() != audit.base_commit
                or any(hashlib.sha256(source_bytes(repo, path)).hexdigest() != digest for path, digest in audit.files.items())):
            raise RepairBlocked('Finding is stale. Rerun ghost find.')
        if len(content) > MAX_SOURCE_BYTES:
            raise RepairBlocked('Repair source exceeds the 64 KB model budget.')
        source = content.decode('utf-8')
        prompt = ('Propose one minimal replacement in the specified application file. Do not change tests, '
                  'disable checks, add suppressions or commands. Return old and new text only; old must occur exactly once. '
                  'Passing tests will not establish security proof.\n' + json.dumps({
                      'finding': finding.model_dump(), 'source': source}))
        validate_model_input(prompt)
        result.base_commit = audit.base_commit
        result.source_signature = source_signature(repo)
        with Worktree(repo) as sandbox:
            if source_signature(repo) != result.source_signature or source_bytes(sandbox, finding.path) != content:
                raise RepairBlocked('Source changed while preparing the sandbox. Rerun ghost find.')
            selected = inventory(sandbox)
            if len(selected) > MAX_FILES:
                raise RepairBlocked('Repair snapshot exceeds the file budget.')
            expected, total = {}, 0
            for path in sorted(selected):
                data = source_bytes(sandbox, path)
                total += len(data)
                if total > MAX_TOTAL_BYTES:
                    raise RepairBlocked('Repair snapshot exceeds the byte budget.')
                expected[path] = data

            def unchanged(check):
                try:
                    check['snapshot_unchanged'] = inventory(sandbox) == selected and all(
                        source_bytes(sandbox, path) == data for path, data in expected.items())
                except (OSError, ValueError):
                    check['snapshot_unchanged'] = False
                db.save_solution(result)
                if not check['snapshot_unchanged']:
                    raise RepairBlocked('A verification step changed project files; proposal rejected.')

            if runner.version_command:
                version = run(runner.version_command, sandbox, timeout=timeout, output_limit=4096, agent=True)
                check = {'label': 'Node runner version', 'command': version.argv, 'exit_code': version.exit_code, 'duration': version.duration,
                         'sandboxed': version.sandboxed, 'timed_out': version.timed_out, 'output_truncated': version.output_truncated}
                result.checks.append(check)
                unchanged(check)
                result.test_runner_version = runner.node_version(version)
            result.status = 'failed'

            def execute(label):
                outcome = run(command, sandbox, timeout=timeout, output_limit=64_000, agent=True)
                check = {'label': label, 'command': outcome.argv, 'exit_code': outcome.exit_code, 'duration': outcome.duration,
                         'sandboxed': outcome.sandboxed, 'timed_out': outcome.timed_out,
                         'output_truncated': outcome.output_truncated}
                evidence = runner.evidence(outcome)
                check['test_evidence'] = evidence.model_dump(mode='json')
                check['passed_tests'] = evidence.passed
                result.checks.append(check)
                db.save_solution(result)
                unchanged(check)
                if evidence.issue or not evidence.complete or evidence.passed < 1:
                    raise RepairBlocked(label + ': ' + (evidence.issue or 'No complete passing test evidence was available.'))
                return evidence

            baseline = execute('baseline project tests')
            replacement = request(provider, prompt, Replacement)
            old, new = replacement.old, replacement.new
            if '\r\n' in source and '\n' not in source.replace('\r\n', ''):
                old = old.replace('\r\n', '\n').replace('\n', '\r\n')
                new = new.replace('\r\n', '\n').replace('\n', '\r\n')
            if '\0' in old + new or source.count(old) != 1 or old == new:
                raise RepairBlocked('Model replacement must change one unique source fragment.')
            edit = PatchEdit(path=finding.path, old=old, new=new)
            apply_edits(sandbox, [edit])
            expected[finding.path] = source.replace(old, new, 1).encode('utf-8')
            runner.compare(baseline, execute('patched project tests'))
            scan = find_risks(sandbox, db, timeout=timeout)
            before = {(f.rule, f.path) for f in audit.findings if f.severity in {'HIGH', 'MEDIUM'}}
            new_risks = {(f.rule, f.path) for f in scan.findings if f.severity in {'HIGH', 'MEDIUM'}} - before
            target_absent = not any(f.rule == getattr(finding, 'rule', None) and f.path == finding.path for f in scan.findings)
            check = {'label': 'static rescan', 'status': scan.status, 'new_priority_rules': len(new_risks),
                     'target_rule_absent': target_absent if hasattr(finding, 'rule') else None}
            result.checks.append(check)
            unchanged(check)
            if scan.status != 'completed' or new_risks or (hasattr(finding, 'rule') and not target_absent):
                raise RepairBlocked('Static rescan did not satisfy the proposal gates; target-rule removal and no new priority rule/path pairs are required.')
            if source_signature(repo) != result.source_signature or git(repo, 'rev-parse', 'HEAD').strip() != result.base_commit:
                raise RepairBlocked('Developer checkout changed during testing. Rerun ghost find.')
            result.patch = [edit]
        result.status = 'tested'
        result.notes.append('Node evidence compares flat test identities and counts, not assertion or application coverage.' if runner.kind == RunnerKind.NODE else
                            'Python evidence compares passing counts, not individual test identities or assertion coverage.')
        result.notes.append('LLM proposal passed the selected project tests and static rescan. Security behavior was not independently reproduced or verified. Review the diff and test coverage before approving.')
    except (RepairBlocked, TestRunnerError) as exc:
        result.notes.append(str(exc))
    except Exception:
        result.status = 'failed' if result.status != 'blocked' else 'blocked'
        result.notes.append('LLM repair stopped safely. Check source freshness, test results, provider/privacy settings and response format. No patch was applied.')
    finally:
        result.finished_at = now()
        db.save_solution(result)
    return result


def apply_tested_proposal(repo, db, result):
    """Caller must display the complete proposal and obtain explicit approval."""
    if result.method != 'llm' or result.status != 'tested' or len(result.patch) != 1:
        raise ValueError('Only a tested LLM proposal can be approved here.')
    if source_signature(repo) != result.source_signature or git(repo, 'rev-parse', 'HEAD').strip() != result.base_commit:
        raise ValueError('Checkout changed after testing. Rerun ghost find and ghost solve.')
    apply_edits(repo, result.patch)
    result.status = 'applied'
    db.save_solution(result)
