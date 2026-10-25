"""Adversarial application checks use real snapshots and disposable source only."""
import pytest

from core.security.llm_solver import apply_tested_proposal
from core.security.solver import apply_solution
from infrastructure.repository.git import git
from infrastructure.safety.sandbox.worktree import source_signature
from test_challenge import project, proposal, execute, ORIGINAL


def commit(repo):
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'synthetic snapshot')


def refuse(repo, db, solution, monkeypatch):
    """No call into the write layer and no record changes on rejection."""
    saved = db.latest_solution().model_dump_json()
    module = 'core.security.solver' if solution.method == 'recipe' else 'core.security.llm_solver'
    def no_write(*args, **kwargs):
        pytest.fail('Refusal reached the patch write layer')
    monkeypatch.setattr(module + '.apply_edits', no_write)
    with pytest.raises(ValueError):
        (apply_solution if solution.method == 'recipe' else apply_tested_proposal)(repo, db, solution)
    assert db.latest_solution().model_dump_json() == saved
    assert not list(repo.rglob('.ghost-patch-*.tmp'))


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('flag', ['--assume-unchanged', '--skip-worktree'])
@pytest.mark.parametrize('target', ['parser.py', 'test_contract.py'])
def test_git_hidden_source_or_test_edits_refuse_before_writes(project, monkeypatch, method, flag, target):
    commit(project)
    git(project, 'update-index', flag, target)
    db, solution = proposal(project, method=method)
    assert execute(project, db, solution).status == 'supported'
    old_signature = source_signature(project)
    changed = (project / target).read_text() + '# later developer edit\n'
    (project / target).write_text(changed)
    assert source_signature(project) == old_signature  # The actual blind spot being exercised.
    refuse(project, db, solution, monkeypatch)
    assert (project / target).read_text() == changed


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('change', ['source', 'new_file', 'head', 'missing_snapshot'])
def test_current_source_and_missing_snapshot_refuse_before_writes(project, monkeypatch, method, change):
    commit(project)
    db, solution = proposal(project, method=method)
    result = execute(project, db, solution)
    assert result.status == 'supported'
    if change == 'source':
        (project / 'parser.py').write_text(ORIGINAL + '# developer change\n')
    elif change == 'new_file':
        (project / 'new.py').write_text('value = 1\n')
    elif change == 'head':
        commit(project)
    else:
        result.source_snapshot_sha256 = None
        db.save_solution(solution)
    before = (project / 'parser.py').read_bytes()
    refuse(project, db, solution, monkeypatch)
    assert (project / 'parser.py').read_bytes() == before
    if change == 'new_file':
        assert (project / 'new.py').read_text() == 'value = 1\n'


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('target', ['traversal', 'absolute', 'git', 'ghost'])
def test_tampered_paths_never_reach_the_write_layer(project, monkeypatch, method, target):
    db, solution = proposal(project, method=method)
    assert execute(project, db, solution).status == 'supported'
    outside = project.parent / (project.name + '-outside.py')
    outside.write_text(ORIGINAL)
    solution.patch[0].path = {'traversal': '../' + outside.name, 'absolute': str(outside),
                              'git': '.git/config', 'ghost': '.ghost/ghost.db'}[target]
    db.save_solution(solution)
    config = (project / '.git/config').read_bytes()
    refuse(project, db, solution, monkeypatch)
    assert (project / 'parser.py').read_text() == outside.read_text() == ORIGINAL
    assert (project / '.git/config').read_bytes() == config


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('kind', ['file', 'parent'])
def test_symlink_swap_after_challenge_does_not_touch_either_source(project, monkeypatch, method, kind):
    relative = 'parser.py'
    if kind == 'parent':
        (project / 'src').mkdir()
        (project / 'src/__init__.py').write_text('')
        (project / 'parser.py').rename(project / 'src/parser.py')
        test = project / 'test_contract.py'
        test.write_text(test.read_text().replace('from parser import', 'from src.parser import'))
        relative = 'src/parser.py'
    commit(project)
    db, solution = proposal(project, method=method)
    solution.patch[0].path = relative
    db.save_solution(solution)
    assert execute(project, db, solution).status == 'supported'
    outside = project.parent / (project.name + '-external')
    outside.mkdir()
    (outside / 'parser.py').write_text(ORIGINAL)
    if kind == 'file':
        (project / 'parser.py').unlink()
        (project / 'parser.py').symlink_to(outside / 'parser.py')
    else:
        (project / 'src').rename(project / 'saved_src')
        (project / 'src').symlink_to(outside, target_is_directory=True)
    refuse(project, db, solution, monkeypatch)
    assert (outside / 'parser.py').read_text() == ORIGINAL
    if kind == 'parent':
        assert (project / 'saved_src/parser.py').read_text() == ORIGINAL
    assert (project / ('src' if kind == 'parent' else 'parser.py')).is_symlink()


def test_hidden_edit_during_last_run_invalidates_challenge(project, monkeypatch):
    import core.security.challenge as module
    commit(project)
    git(project, 'update-index', '--assume-unchanged', 'parser.py')
    db, solution = proposal(project)
    original_run = module.run
    stages = []
    def change_after_last_run(*args, **kwargs):
        result = original_run(*args, **kwargs)
        stages.append(result)
        if len(stages) == 4:
            (project / 'parser.py').write_text(ORIGINAL + '# concurrent editor change\n')
        return result
    monkeypatch.setattr(module, 'run', change_after_last_run)
    result = execute(project, db, solution)
    assert len(stages) == 4 and result.status == 'inconclusive'
    assert (project / 'parser.py').read_text() == ORIGINAL + '# concurrent editor change\n'
    assert not list((project / '.ghost/worktrees').iterdir())
