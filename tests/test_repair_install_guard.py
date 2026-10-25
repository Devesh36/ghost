"""Refuse stale unchallenged proposals and late edits without touching source."""
import pytest

from core.domain.types import PatchEdit
from core.security.solver import apply_solution
from core.security.llm_solver import apply_tested_proposal
from infrastructure.repository.git import git
from infrastructure.repository import patches
from test_challenge import project, proposal, ORIGINAL
from test_challenge_adversarial import commit


def apply(repo, db, solution):
    (apply_solution if solution.method == 'recipe' else apply_tested_proposal)(repo, db, solution)


def unchanged_record_and_no_temps(repo, db, saved):
    assert db.latest_solution().model_dump_json() == saved
    assert not [p for p in repo.rglob('.ghost-patch-*.tmp') if p.name != '.ghost-patch-editor.tmp']


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('flag', ['--assume-unchanged', '--skip-worktree'])
@pytest.mark.parametrize('target', ['parser.py', 'test_contract.py'])
def test_unchallenged_hidden_edits_are_refused(project, method, flag, target):
    commit(project)
    git(project, 'update-index', flag, target)
    db, solution = proposal(project, method=method)
    assert not solution.challenges
    saved = db.latest_solution().model_dump_json()
    changed = (project / target).read_text() + '# developer change\n'
    (project / target).write_text(changed)
    with pytest.raises(ValueError, match='Checkout changed'):
        apply(project, db, solution)
    assert (project / target).read_text() == changed
    unchanged_record_and_no_temps(project, db, saved)


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('moment', ['before_writer', 'staging_target', 'staging_tests', 'staging_newfile', 'staging_head', 'staging_patch'])
def test_late_edits_refuse_install_and_preserve_user_state(project, monkeypatch, method, moment):
    commit(project)
    db, solution = proposal(project, method=method)
    saved = db.latest_solution().model_dump_json()
    changed = ORIGINAL + '# concurrent developer change\n'
    if moment == 'before_writer':
        original_apply = patches.apply_edits
        def writer(repo, edits, **kwargs):
            (project / 'parser.py').write_text(changed)
            return original_apply(repo, edits, **kwargs)
        monkeypatch.setattr('core.security.' + ('solver' if method == 'recipe' else 'llm_solver') + '.apply_edits', writer)
    else:
        fsync = patches.os.fsync
        def edit_after_staging(fd):
            if moment == 'staging_target':
                (project / 'parser.py').write_text(changed)
            elif moment == 'staging_tests':
                (project / 'test_contract.py').write_text('# changed tests\n')
            elif moment == 'staging_newfile':
                # Only Ghost's own exact staging path may be excluded, not a prefix.
                (project / '.ghost-patch-editor.tmp').write_text('developer content')
            elif moment == 'staging_head':
                git(project, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'new HEAD')
            else:
                solution.patch[0].new += '# untested patch edit\n'
            fsync(fd)
        monkeypatch.setattr(patches.os, 'fsync', edit_after_staging)
    with pytest.raises(ValueError):
        apply(project, db, solution)
    assert (project / 'parser.py').read_text() == (changed if moment in {'before_writer', 'staging_target'} else ORIGINAL)
    if moment == 'staging_tests':
        assert (project / 'test_contract.py').read_text() == '# changed tests\n'
    if moment == 'staging_newfile':
        assert (project / '.ghost-patch-editor.tmp').read_text() == 'developer content'
    if moment == 'staging_head':
        assert git(project, 'rev-parse', 'HEAD').strip() != solution.base_commit
    unchanged_record_and_no_temps(project, db, saved)


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('field', ['source_snapshot_sha256', 'patch_sha256'])
def test_legacy_proposal_without_byte_evidence_requires_new_solve(project, method, field):
    db, solution = proposal(project, method=method)
    setattr(solution, field, None)
    db.save_solution(solution)
    saved = db.latest_solution().model_dump_json()
    with pytest.raises(ValueError, match='Run a new review and solve'):
        apply(project, db, solution)
    assert (project / 'parser.py').read_text() == ORIGINAL
    unchanged_record_and_no_temps(project, db, saved)


@pytest.mark.parametrize('damage', ['bytes', 'mode', 'delete'])
def test_staging_corruption_is_not_installed(project, monkeypatch, damage):
    db, solution = proposal(project)
    saved = db.latest_solution().model_dump_json()
    fsync = patches.os.fsync
    def corrupt_candidate(fd):
        candidate = next(project.glob('.ghost-patch-*.tmp'))
        if damage == 'bytes':
            candidate.write_text('unverified content')
        elif damage == 'mode':
            candidate.chmod(0o777)
        else:
            candidate.unlink()
        fsync(fd)
    monkeypatch.setattr(patches.os, 'fsync', corrupt_candidate)
    with pytest.raises(ValueError, match='Staged patch changed'):
        apply(project, db, solution)
    assert (project / 'parser.py').read_text() == ORIGINAL
    unchanged_record_and_no_temps(project, db, saved)


@pytest.mark.parametrize('operation', ['replace', 'create', 'delete'])
def test_writer_callback_refusal_preserves_originals_and_cleans_owned_state(tmp_path, operation):
    target = 'nested/code.py' if operation == 'create' else 'code.py'
    if operation != 'create':
        (tmp_path / target).write_text('old')
    edit = PatchEdit(path=target, operation=operation, old='' if operation == 'create' else 'old',
                     new='' if operation == 'delete' else 'new')
    seen = []
    def refuse(staged_path):
        seen.append(staged_path)
        if operation != 'delete':
            assert staged_path and (tmp_path / staged_path).is_file()
        raise ValueError('pre-install refusal')
    with pytest.raises(ValueError, match='pre-install refusal'):
        patches.apply_edits(tmp_path, [edit], before_install=refuse)
    assert len(seen) == 1
    if operation == 'create':
        assert list(tmp_path.iterdir()) == []
    else:
        assert (tmp_path / target).read_text() == 'old'
        assert list(tmp_path.iterdir()) == [tmp_path / target]


@pytest.mark.parametrize('method', ['recipe', 'llm'])
def test_real_solver_rejects_hidden_changes_during_verification(project, monkeypatch, method):
    import core.security.solver as recipe
    import core.security.llm_solver as llm
    from core.llm.base import FakeProvider
    from test_security_workflow import parser_fixture
    from test_security_assistance import PATCH
    (project / 'test_contract.py').unlink()  # This fixture needs a passing ordinary baseline.
    parser_fixture(project)
    commit(project)
    db, audit, finding = parser_fixture(project)
    git(project, 'update-index', '--assume-unchanged', 'test_parser.py')
    module, name = (recipe, 'audit_repository') if method == 'recipe' else (llm, 'find_risks')
    original = getattr(module, name)
    def scan_then_edit(*args, **kwargs):
        result = original(*args, **kwargs)
        (project / 'test_parser.py').write_text('# hidden developer edit during verification\n')
        return result
    monkeypatch.setattr(module, name, scan_then_edit)
    args = (project, db, audit, finding, 'python -m unittest test_parser')
    result = recipe.solve(*args) if method == 'recipe' else llm.solve_with_llm(*args, FakeProvider([PATCH]))
    assert result.status == 'failed', result.notes
    assert (project / 'parser.py').read_text() == ORIGINAL
    assert (project / 'test_parser.py').read_text() == '# hidden developer edit during verification\n'
    assert not list((project / '.ghost/worktrees').iterdir())
