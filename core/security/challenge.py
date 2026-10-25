"""Try to refute a Python repair with repeated original/patched negative controls."""
import json
import os
from pathlib import Path
import re
import shlex
import sys

from core.domain.types import now
from core.security.models import RepairChallenge
from core.security.test_runners import RunnerKind, python_runner
from infrastructure.repository.git import git
from infrastructure.repository.patches import apply_edits
from infrastructure.safety.guardrails.commands import run
from infrastructure.safety.sandbox.worktree import Worktree, source_signature
from infrastructure.security.bandit import MAX_FILES, MAX_TOTAL_BYTES, source_bytes
from infrastructure.security.review import inventory


class ChallengeBlocked(ValueError):
    pass


def selected_cases(repo, command):
    if not command or len(command) > 4096:
        raise ChallengeBlocked('Select a bounded unittest command explicitly with --tests.')
    try:
        runner = python_runner(command)
    except ValueError:
        raise ChallengeBlocked('Select a direct python -m unittest command; shell operations and inline code are not accepted.') from None
    if runner.kind != RunnerKind.UNITTEST:
        raise ChallengeBlocked('Challenge currently supports Python unittest, not pytest or Node.')
    selectors = [arg for arg in runner.argv[3:] if arg not in {'-v', '-q'}]
    if (not 1 <= len(selectors) <= 20 or any(len(s) > 300 or not re.fullmatch(
            r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', s) for s in selectors) or 'discover' in selectors):
        raise ChallengeBlocked('Select explicit unittest modules/classes/cases; discovery, filters and runner flags are unsupported.')
    files = set()
    visible = inventory(repo)
    for selector in selectors:
        parts = selector.split('.')
        for end in range(len(parts), 0, -1):
            path = '/'.join(parts[:end]) + '.py'
            if path in visible:
                source_bytes(repo, path)
                files.add(path)
                break
        else:
            raise ChallengeBlocked('Every selected test must resolve to a Git-visible local Python module.')
    return selectors, files


def snapshot(repo, *, exclude_path=None):
    paths = inventory(repo) - ({exclude_path} if exclude_path is not None else set())
    if len(paths) > MAX_FILES:
        raise ChallengeBlocked('Challenge snapshot exceeds the source file budget.')
    result = {}
    total = 0
    for path in sorted(paths):
        data = source_bytes(repo, path)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ChallengeBlocked('Challenge snapshot exceeds the source byte budget.')
        result[path] = data
    return result


def evidence(payload):
    try:
        report = json.loads(payload)
        if not isinstance(report, dict) or set(report) != {'schema_version', 'complete', 'cases'}:
            raise ValueError
        if type(report['schema_version']) is not int or report['schema_version'] != 1 or report['complete'] is not True:
            raise ValueError
        cases = report['cases']
        if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
            raise ValueError
        for case in cases:
            if (not isinstance(case, dict) or set(case) != {'id', 'outcome'}
                    or not re.fullmatch(r'[0-9a-f]{64}', case['id'])
                    or case['outcome'] not in {'pass', 'failure', 'error', 'skip', 'expected_failure', 'unexpected_success'}):
                raise ValueError
        if len({case['id'] for case in cases}) != len(cases):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ChallengeBlocked('Structured test evidence is incomplete or unsupported; zero tests and subtests cannot qualify.') from None
    return cases


def challenge(repo, db, solution, tests, *, timeout=30):
    """Caller holds investigation_lock through execution, cleanup and persistence."""
    from core.security.challenge_report import patch_digest, snapshot_digest
    result = RepairChallenge(selected_tests=tests, patch_sha256=patch_digest(solution.patch))
    solution.challenges.append(result)
    db.save_solution(solution)
    try:
        if os.getenv('GHOST_DISABLE_OS_SANDBOX') == '1':
            raise ChallengeBlocked('Challenge requires OS confinement. Unset GHOST_DISABLE_OS_SANDBOX.')
        if ((solution.method, solution.status) not in {('recipe', 'verified'), ('llm', 'tested')}
                or len(solution.patch) != 1):
            raise ChallengeBlocked('Challenge needs one unapplied verified recipe or tested LLM Python proposal from ghost solve.')
        from core.security.repair_evidence import require_current_proposal
        try:
            require_current_proposal(repo, solution)
        except ValueError as exc:
            raise ChallengeBlocked(str(exc)) from None
        selectors, test_files = selected_cases(repo, tests)
        edit = solution.patch[0]
        if edit.path in test_files or Path(edit.path).name.startswith('test_') or Path(edit.path).suffix != '.py':
            raise ChallengeBlocked('Challenge cannot patch a selected test or a test module.')
        result.source_signature = source_signature(repo)
        result.base_commit = git(repo, 'rev-parse', 'HEAD').strip()
        if result.source_signature != solution.source_signature or result.base_commit != solution.base_commit:
            raise ChallengeBlocked('Source changed since the proposal. Rerun ghost find and ghost solve before challenging it.')
        original = snapshot(repo)
        result.source_snapshot_sha256 = snapshot_digest(original)
        command = shlex.join([sys.executable, '-I', '-m', 'infrastructure.security.challenge_worker', *selectors])
        first_ids = None
        first_failures = None
        result.status = 'inconclusive'
        for label, patched in [('original', False), ('patched', True), ('original_repeated', False), ('patched_repeated', True)]:
            if source_signature(repo) != result.source_signature:
                raise ChallengeBlocked('Developer source changed during the challenge; its result cannot qualify.')
            with Worktree(repo) as workspace:
                if snapshot(workspace) != original:
                    raise ChallengeBlocked('The isolated snapshot did not match the reviewed source.')
                if patched:
                    apply_edits(workspace, solution.patch)
                expected = snapshot(workspace)
                outcome = run(command, workspace, agent=True, timeout=timeout, output_limit=200_000)
                stage = {'stage': label, 'patched': patched, 'exit_code': outcome.exit_code,
                         'sandboxed': outcome.sandboxed, 'timed_out': outcome.timed_out,
                         'output_truncated': outcome.output_truncated, 'duration': outcome.duration}
                result.stages.append(stage)
                if outcome.exit_code or outcome.timed_out or outcome.output_truncated or not outcome.sandboxed:
                    raise ChallengeBlocked('Test execution failed its confinement/time/output policy; a crash is not a regression witness.')
                stage['snapshot_unchanged'] = snapshot(workspace) == expected
                if not stage['snapshot_unchanged']:
                    raise ChallengeBlocked('The selected tests changed source or fixtures; refusing challenge evidence.')
                cases = evidence(outcome.stdout)
                stage['cases'] = cases
                ids = {row['id'] for row in cases}
                if first_ids is None:
                    first_ids = ids
                if ids != first_ids:
                    raise ChallengeBlocked('The selected test inventory changed between code variants.')
                if any(row['outcome'] not in {'pass', 'failure'} for row in cases):
                    raise ChallengeBlocked('Errors, skips and expected/unexpected failures cannot qualify a challenge.')
                failures = {row['id'] for row in cases if row['outcome'] == 'failure'}
                stage['passed'] = len(cases) - len(failures)
                stage['failed'] = len(failures)
                if (patched and failures) or (not patched and not failures):
                    result.status = 'not_supported'
                    result.notes.append('The selected tests still fail on the repair.' if patched else
                                        'The selected tests pass on the original code too; they do not discriminate this repair.')
                    break
                if not patched:
                    if first_failures is not None and failures != first_failures:
                        raise ChallengeBlocked('The original failed different cases on repetition; the witness is unstable.')
                    first_failures = failures
            db.save_solution(solution)
        else:
            result.status = 'supported'
            result.notes.append('The same selected cases reject the original, accept the repair, and repeat that result in fresh isolated snapshots.')
        if (source_signature(repo) != result.source_signature
                or git(repo, 'rev-parse', 'HEAD').strip() != result.base_commit
                or snapshot(repo) != original):
            raise ChallengeBlocked('Developer source or HEAD changed during the challenge; its result cannot qualify.')
    except ChallengeBlocked as exc:
        result.status = 'blocked' if not result.stages else 'inconclusive'
        result.notes.append(str(exc))
    except KeyboardInterrupt:
        result.status = 'inconclusive'
        result.notes.append('Challenge interrupted; it did not qualify the repair.')
        raise
    except Exception:
        result.status = 'inconclusive'
        result.notes.append('Challenge stopped safely. No test output or source excerpt was exported; inspect ghost doctor before retrying.')
    finally:
        result.notes.append('Local regression evidence only. Tests are trusted code; application reachability and exploitability are not established.')
        result.finished_at = now()
        db.save_solution(solution)
    return result
