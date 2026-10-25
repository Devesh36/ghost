"""Bind security proposals to the bounded bytes actually tested by the solver."""
from core.security.challenge import snapshot
from core.security.challenge_report import patch_digest, snapshot_digest
from infrastructure.repository.git import git


def require_current_proposal(repo, solution, *, staged_path=None):
    """The sole excluded path is the patch writer's own newly created temporary file."""
    if (not solution.source_snapshot_sha256 or not solution.patch_sha256
            or solution.patch_sha256 != patch_digest(solution.patch)):
        raise ValueError('Repair evidence is missing or does not match this patch. Run a new review and solve.')
    try:
        current = snapshot_digest(snapshot(repo, exclude_path=staged_path))
    except (OSError, ValueError):
        raise ValueError('Checkout snapshot is unreadable or unsafe. Run a new review and solve.') from None
    if current != solution.source_snapshot_sha256 or git(repo, 'rev-parse', 'HEAD').strip() != solution.base_commit:
        raise ValueError('Checkout changed since repair testing. Run a new review and solve.')
