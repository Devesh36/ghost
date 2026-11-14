"""Abrupt process death, conservative ownership and retained repair archives."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from core.domain.types import PatchEdit
from core.security.models import SecuritySolution
from core.security.repair_recovery import RepairWorkspace, require_finished_recovery
from infrastructure.database.locking import investigation_lock
from infrastructure.database.repository import Database
from infrastructure.database.storage import StorageError
from infrastructure.repository.git import git
from infrastructure.safety.sandbox.recovery import recovery_plan
from infrastructure.safety.sandbox.repair_archive import archive_repair
from surfaces.entrypoint import app


@pytest.fixture
def project(tmp_path, monkeypatch):
    git(tmp_path, 'init', '-q', '--template=')
    (tmp_path / '.gitignore').write_text('.ghost/\n__pycache__/\n')
    (tmp_path / 'parser.py').write_text('def parse(value):\n    return eval(value)\n')
    (tmp_path / 'test_parser.py').write_text(
        'import unittest\nfrom parser import parse\nclass Tests(unittest.TestCase):\n'
        '    def test_literal(self):\n        self.assertEqual(parse("[1, 2]"), [1, 2])\n')
    git(tmp_path, 'add', '.')
    git(tmp_path, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '-qm', 'synthetic baseline')
    monkeypatch.chdir(tmp_path)
    return tmp_path


CRASH_SOLVER = '''
import os, signal, sys
from pathlib import Path
from core.security.solver import solve
from core.security.repair_recovery import RepairWorkspace
from infrastructure.database.repository import Database
from infrastructure.database.locking import investigation_lock
from infrastructure.security.review import find_risks
repo = Path(sys.argv[1])
db = Database(repo)
with investigation_lock(repo):
    audit = find_risks(repo, db)
    finding = next(f for f in audit.findings if f.rule == 'B307')
    original = RepairWorkspace.checkpoint
    def checkpoint(self, stage):
        original(self, stage)
        if stage == sys.argv[2]:
            os.kill(os.getpid(), signal.SIGKILL)
    RepairWorkspace.checkpoint = checkpoint
    solve(repo, db, audit, finding, 'python -m unittest test_parser')
'''


@pytest.mark.parametrize('stage', ['creating', 'prepared', 'testing', 'patching',
                                  'rescanning', 'cleanup_pending', 'cleaned'])
def test_killed_real_solver_retains_checkpoint_and_never_verifies(project, stage):
    original = (project / 'parser.py').read_bytes()
    process = subprocess.run([sys.executable, '-c', CRASH_SOLVER, str(project), stage],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=60)
    assert process.returncode == -signal.SIGKILL, process.stderr.decode()
    plan = recovery_plan(project)
    assert plan['complete'] and plan['exit_code'] == 1
    repair = plan['repairs'][0]
    assert repair['needs_review'] and not repair['has_finish_time']
    assert repair['recorded_status'] not in {'verified', 'tested', 'applied'}
    run = repair['runs'][0]
    assert run['stage'] == stage
    assert run['archive_available'] == (stage in {'prepared', 'cleanup_pending'})
    assert (project / 'parser.py').read_bytes() == original
    if run['archive_available']:
        result = archive_repair(project, run['id'])
        assert not result['deleted'] and not result['verification_changed']
        assert (project / result['archive'] / 'parser.py').is_file()
    else:
        with pytest.raises(ValueError):
            archive_repair(project, run['id'])
    assert Database(project).latest_solution().status not in {'verified', 'tested', 'applied'}
    assert (project / 'parser.py').read_bytes() == original


def leftover(repo, *, stage='prepared'):
    db = Database(repo)
    solution = SecuritySolution(audit_id='synthetic', finding_id='synthetic', notes=['private evidence'])
    with investigation_lock(repo):
        workspace = RepairWorkspace(repo, db, solution)
        path = workspace.__enter__()
        workspace.checkpoint(stage)
    return db, solution, workspace, path


def test_explicit_archive_keeps_dirty_ignored_and_untracked_files_and_evidence(project):
    db, solution, workspace, path = leftover(project, stage='cleanup_pending')
    (path / 'parser.py').write_text('user-edited candidate\n')
    (path / 'notes.txt').write_text('retain my notes\n')
    (path / '__pycache__').mkdir()
    (path / '__pycache__/saved').write_bytes(b'ignored bytes')
    before = solution.model_dump(exclude={'recovery_runs'})
    response = CliRunner().invoke(app, ['recover', '--archive', workspace.record.id, '--json'])
    assert response.exit_code == 0, response.output
    result = json.loads(response.output)
    archive = project / result['archive']
    assert not path.exists()
    assert (archive / 'parser.py').read_text() == 'user-edited candidate\n'
    assert (archive / 'notes.txt').read_text() == 'retain my notes\n'
    assert (archive / '__pycache__/saved').read_bytes() == b'ignored bytes'
    saved = db.latest_solution()
    assert saved.model_dump(exclude={'recovery_runs'}) == before
    assert saved.recovery_runs[0].stage == 'archived'
    with pytest.raises(ValueError, match='fresh solve'):
        require_finished_recovery(saved)
    assert 'private evidence' not in CliRunner().invoke(app, ['recover', '--json']).output


@pytest.mark.parametrize('change', ['symlink', 'replacement', 'gitfile', 'locked', 'attached', 'destination', 'archive_link'])
def test_uncertain_workspace_or_destination_is_never_moved(project, change):
    _, _, workspace, path = leftover(project)
    destination = project / '.ghost/recovered' / path.name
    if change == 'symlink':
        path.rename(path.with_name('retained'))
        path.symlink_to(path.with_name('retained'), target_is_directory=True)
    elif change == 'replacement':
        path.rename(path.with_name('retained'))
        path.mkdir()
        (path / '.git').write_text((path.with_name('retained') / '.git').read_text())
    elif change == 'gitfile':
        (path / '.git').write_text('gitdir: /not-a-ghost-registration\n')
    elif change == 'locked':
        git(project, 'worktree', 'lock', str(path))
    elif change == 'attached':
        git(path, 'checkout', '-b', 'user-branch')
    elif change == 'destination':
        destination.mkdir(parents=True)
        (destination / 'keep').write_text('user data')
    else:
        outside = project / 'outside'
        outside.mkdir()
        (project / '.ghost/recovered').symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        archive_repair(project, workspace.record.id)
    assert os.path.lexists(path)
    if change == 'destination':
        assert (destination / 'keep').read_text() == 'user data'


def test_held_lock_and_unknown_id_never_move_a_workspace(project):
    _, _, workspace, path = leftover(project)
    with investigation_lock(project), pytest.raises(ValueError, match='available'):
        archive_repair(project, workspace.record.id)
    for selector in ['../escape', '0' * 32, workspace.record.id[:8]]:
        with pytest.raises(ValueError):
            archive_repair(project, selector)
    assert path.exists()


def test_move_then_save_failure_can_be_reconciled_without_overwrite(project, monkeypatch):
    db, solution, workspace, path = leftover(project)
    original = Database.save_solution
    def fail(*args):
        raise OSError('synthetic storage failure')
    monkeypatch.setattr(Database, 'save_solution', fail)
    with pytest.raises(StorageError):
        archive_repair(project, workspace.record.id)
    assert not path.exists()
    assert db.latest_solution().recovery_runs[0].stage == 'prepared'
    assert recovery_plan(project)['repairs'][0]['runs'][0]['archive_available']
    monkeypatch.setattr(Database, 'save_solution', original)
    result = archive_repair(project, workspace.record.id)
    assert (project / result['archive'] / 'parser.py').exists()
    assert db.latest_solution().recovery_runs[0].stage == 'archived'


@pytest.mark.parametrize('method', ['recipe', 'llm'])
def test_interrupted_workspace_blocks_application_before_source_mutation(project, method):
    from core.security.solver import apply_solution
    from core.security.llm_solver import apply_tested_proposal
    db, solution, workspace, _ = leftover(project, stage='testing')
    solution.method = method
    solution.status = 'verified' if method == 'recipe' else 'tested'
    solution.patch = [PatchEdit(path='parser.py', old='eval(value)', new='value')]
    before = (project / 'parser.py').read_bytes()
    with pytest.raises(ValueError, match='fresh solve'):
        (apply_solution if method == 'recipe' else apply_tested_proposal)(project, db, solution)
    assert (project / 'parser.py').read_bytes() == before


def test_legacy_solution_without_checkpoints_remains_readable(project):
    db = Database(project)
    solution = SecuritySolution(audit_id='synthetic', finding_id='synthetic')
    db.save_solution(solution)
    plan = recovery_plan(project)
    assert plan['complete'] and plan['repairs'][0]['needs_review']
    assert plan['repairs'][0]['runs'] == []
    assert 'Legacy record' in CliRunner().invoke(app, ['recover']).output


@pytest.mark.parametrize('stage', ['prepared', 'testing', 'proposing', 'patching', 'rescanning', 'cleanup_pending'])
def test_killed_llm_repair_retains_checkpoint_without_qualifying(project, stage):
    script = CRASH_SOLVER.replace('from core.security.solver import solve',
        'from core.security.llm_solver import solve_with_llm\nfrom core.llm.base import FakeProvider')
    script = script.replace("solve(repo, db, audit, finding, 'python -m unittest test_parser')",
        "solve_with_llm(repo, db, audit, finding, 'python -m unittest test_parser', "
        "FakeProvider([{'old': 'return eval(value)', 'new': 'return __import__(\"ast\").literal_eval(value)'}]))")
    before = (project / 'parser.py').read_bytes()
    process = subprocess.run([sys.executable, '-c', script, str(project), stage],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=60)
    assert process.returncode == -signal.SIGKILL, process.stderr.decode()
    repair = recovery_plan(project)['repairs'][0]
    assert repair['method'] == 'llm' and repair['runs'][0]['stage'] == stage
    assert repair['recorded_status'] not in {'tested', 'applied'}
    assert (project / 'parser.py').read_bytes() == before


@pytest.mark.parametrize('attempt', [1, 2, 3, 4])
def test_killed_challenge_stage_requires_fresh_verification(project, attempt):
    from core.security.solver import apply_solution
    (project / 'test_contract.py').write_text(
        'import unittest\nfrom parser import parse\nclass Contract(unittest.TestCase):\n'
        '    def test_calls(self):\n        with self.assertRaises((ValueError, SyntaxError)):\n'
        '            parse("sum([1,2])")\n')
    script = CRASH_SOLVER[:CRASH_SOLVER.index('    original = RepairWorkspace.checkpoint')]
    script += '''
    from core.security.challenge import challenge
    solution = solve(repo, db, audit, finding, 'python -m unittest test_parser')
    assert solution.status == 'verified', solution.notes
    original = RepairWorkspace.checkpoint
    count = 0
    def checkpoint(self, stage):
        global count
        original(self, stage)
        if stage == 'testing':
            count += 1
            if count == int(sys.argv[2]):
                os.kill(os.getpid(), signal.SIGKILL)
    RepairWorkspace.checkpoint = checkpoint
    challenge(repo, db, solution, 'python -m unittest test_contract')
'''
    before = (project / 'parser.py').read_bytes()
    process = subprocess.run([sys.executable, '-c', script, str(project), str(attempt)],
                             cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=90)
    assert process.returncode == -signal.SIGKILL, process.stderr.decode()
    db = Database(project)
    solution = db.latest_solution()
    assert solution.status == 'verified'
    assert solution.challenges[-1].status == 'inconclusive'
    assert solution.challenges[-1].finished_at is None
    assert solution.recovery_runs[-1].kind == 'challenge'
    assert solution.recovery_runs[-1].label == ['original', 'patched', 'original_repeated', 'patched_repeated'][attempt - 1]
    assert solution.recovery_runs[-1].stage == 'testing'
    assert len(solution.challenges[-1].stages) == attempt - 1
    with pytest.raises(ValueError, match='fresh solve'):
        apply_solution(project, db, solution)
    assert (project / 'parser.py').read_bytes() == before


def test_home_and_repl_warn_without_resuming_work(project):
    import io
    from rich.console import Console
    from typer.main import get_command
    from core.domain.types import Session
    from surfaces.interactive_shell.shell import GhostREPL
    db, _, _, _ = leftover(project, stage='testing')
    response = CliRunner().invoke(app, ['home'])
    assert 'ghost recover' in response.output
    stream = io.StringIO()
    session = Session(repository_path=str(project), starting_commit='head', branch='main')
    GhostREPL(project, db, session, get_command(app), Console(file=stream, width=100))
    assert 'ghost recover' in stream.getvalue()
    assert db.latest_solution().recovery_runs[0].stage == 'testing'


def test_fresh_completed_solve_clears_old_archive_notice_without_rewriting_evidence(project):
    from infrastructure.database.repair_inspection import repair_recovery_notice
    db, solution, workspace, _ = leftover(project)
    archive_repair(project, workspace.record.id)
    before = db.latest_solution().model_dump()
    fresh = SecuritySolution(audit_id='new', finding_id='new', started_at='2099-01-01',
                             finished_at='2099-01-02', status='blocked')
    db.save_solution(fresh)
    assert repair_recovery_notice(project) is None
    with db.connect(write=False) as connection:
        old = connection.execute('SELECT payload FROM security_solutions WHERE id=?', (solution.id,)).fetchone()[0]
    assert SecuritySolution.model_validate_json(old).model_dump() == before


def test_duplicate_workspace_receipts_block_inspection_and_archiving(project):
    db, solution, workspace, path = leftover(project)
    duplicate = solution.model_copy(deep=True)
    duplicate.id = 'another-solution'
    db.save_solution(duplicate)
    plan = recovery_plan(project)
    assert not plan['complete'] and plan['exit_code'] == 2
    with pytest.raises(ValueError):
        archive_repair(project, workspace.record.id)
    assert path.exists()
