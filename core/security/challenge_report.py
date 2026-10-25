"""Check saved regression evidence for both reports and repair application."""
import hashlib
import json
import re

from core.security.challenge import evidence, snapshot, ChallengeBlocked

STAGES = ('original', 'patched', 'original_repeated', 'patched_repeated')


def patch_digest(patch):
    payload = json.dumps([edit.model_dump(mode='json') for edit in patch],
                         sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def snapshot_digest(files):
    """Identify the sorted snapshot paths and exact bytes without exporting source."""
    manifest = [[path, hashlib.sha256(data).hexdigest()] for path, data in sorted(files.items())]
    return hashlib.sha256(json.dumps(manifest, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def assess(solution, result):
    """Consistency check of local records, not a signature or a new execution."""
    if result.status != 'supported':
        return result.status, 'This saved attempt did not support the repair.'
    try:
        if (not result.finished_at or len(solution.patch) != 1
                or not result.patch_sha256 or result.patch_sha256 != patch_digest(solution.patch)
                or not re.fullmatch(r'[0-9a-f]{64}', result.source_signature)
                or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', result.base_commit)
                or result.source_signature != solution.source_signature
                or result.base_commit != solution.base_commit
                or len(result.stages) != 4):
            raise ValueError
        inventory = failures = None
        for index, stage in enumerate(result.stages):
            patched = index % 2 == 1
            if (stage.get('stage') != STAGES[index] or stage.get('patched') is not patched
                    or type(stage.get('exit_code')) is not int or stage['exit_code'] != 0
                    or stage.get('sandboxed') is not True or stage.get('snapshot_unchanged') is not True
                    or stage.get('timed_out') is not False or stage.get('output_truncated') is not False):
                raise ValueError
            cases = evidence(json.dumps({'schema_version': 1, 'complete': True, 'cases': stage.get('cases')}))
            ids = {row['id'] for row in cases}
            failed = {row['id'] for row in cases if row['outcome'] == 'failure'}
            if (any(row['outcome'] not in {'pass', 'failure'} for row in cases)
                    or (inventory is not None and ids != inventory)
                    or (patched and failed) or (not patched and not failed)
                    or (not patched and failures is not None and failed != failures)
                    or type(stage.get('passed')) is not int or stage['passed'] != len(cases) - len(failed)
                    or type(stage.get('failed')) is not int or stage['failed'] != len(failed)):
                raise ValueError
            inventory = ids
            if not patched:
                failures = failed
    except (ValueError, TypeError, KeyError, AttributeError, ChallengeBlocked):
        return 'inconclusive', 'Saved evidence is incomplete or inconsistent with the proposal. Run a new challenge.'
    return 'supported', 'The saved cases reject the original and accept the patch in both repetitions.'


def require_supported_challenge(solution, repo):
    """An existing challenge must support this exact proposal before any write."""
    if solution.challenges and assess(solution, solution.challenges[-1])[0] != 'supported':
        raise ValueError('The latest Challenge did not support this proposal and patch. Run a new challenge before applying.')

    if solution.challenges:
        latest = solution.challenges[-1]
        if not latest.source_snapshot_sha256:
            raise ValueError('The latest Challenge has no snapshot fingerprint. Run a new challenge before applying.')
        try:
            matches = snapshot_digest(snapshot(repo)) == latest.source_snapshot_sha256
        except (OSError, ValueError):
            raise ValueError('Checkout snapshot is unreadable or unsafe. Run a new review and challenge before applying.') from None
        if not matches:
            raise ValueError('Checkout snapshot changed after the Challenge. Run a new review and challenge before applying.')
