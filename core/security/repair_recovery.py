"""Persist security-workspace checkpoints independently of verification evidence."""
import hashlib

from core.security.models import RepairRun
from infrastructure.safety.sandbox.worktree import Worktree


class RepairWorkspace:
    def __init__(self, repo, db, solution, *, kind='solve', label='solve'):
        self.db, self.solution = db, solution
        self.record = RepairRun(kind=kind, label=label)
        self.tree = Worktree(repo, name='repair-' + self.record.id)
        solution.recovery_runs.append(self.record)
        self.checkpoint('creating')

    def checkpoint(self, stage):
        self.record.stage = stage
        self.db.save_solution(self.solution)

    def __enter__(self):
        path = self.tree.__enter__()
        info = path.stat()
        self.record.workspace_identity = (info.st_dev, info.st_ino)
        self.record.gitfile_sha256 = hashlib.sha256((path / '.git').read_bytes()).hexdigest()
        self.checkpoint('prepared')
        return path

    def __exit__(self, exc_type, exc, traceback):
        # An interrupted test/proposal never gains a cleanup checkpoint. Normal
        # worktree teardown still runs; failed teardown leaves its prior stage.
        if exc_type is None:
            self.checkpoint('cleanup_pending')
        self.tree.__exit__(exc_type, exc, traceback)
        self.checkpoint('cleaned')
        return False


def require_finished_recovery(solution):
    if any(run.stage != 'cleaned' for run in solution.recovery_runs):
        raise ValueError('Repair workspace recovery is unfinished. Inspect ghost recover, '
                         'then run a fresh solve and any required Challenge before applying.')
