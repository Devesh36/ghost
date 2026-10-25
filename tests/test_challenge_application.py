"""Both application paths must consume the same evidence as the review report."""
from copy import deepcopy

import pytest

from core.security.llm_solver import apply_tested_proposal
from core.security.solver import apply_solution
from infrastructure.safety.sandbox.worktree import source_signature
from test_challenge import project, proposal, execute, ORIGINAL


@pytest.mark.parametrize('method', ['recipe', 'llm'])
@pytest.mark.parametrize('damage', ['patch', 'legacy', 'empty_stages', 'counts', 'case_inventory',
                                    'unstable_failure', 'truncated', 'latest_inconclusive'])
def test_application_rejects_inconsistent_challenge_without_writes(project, method, damage):
    db, solution = proposal(project, method=method)
    result = execute(project, db, solution)
    assert result.status == 'supported'
    if damage == 'patch':
        solution.patch[0].new += '# untested change\n'
    elif damage == 'legacy':
        result.patch_sha256 = None
    elif damage == 'empty_stages':
        result.stages = [{}, {}, {}, {}]
    elif damage == 'counts':
        result.stages[1]['passed'] = 99
    elif damage == 'case_inventory':
        result.stages[1]['cases'][0]['id'] = 'f' * 64
    elif damage == 'unstable_failure':
        for case in result.stages[2]['cases']:
            case['outcome'] = 'pass' if case['outcome'] == 'failure' else 'failure'
    elif damage == 'truncated':
        result.stages[1]['output_truncated'] = True
    elif damage == 'latest_inconclusive':
        latest = deepcopy(result)
        latest.status = 'inconclusive'
        solution.challenges.append(latest)
    db.save_solution(solution)
    saved = db.latest_solution().model_dump_json()
    before = source_signature(project)
    apply = apply_solution if method == 'recipe' else apply_tested_proposal
    with pytest.raises(ValueError, match='latest Challenge'):
        apply(project, db, solution)
    assert source_signature(project) == before
    assert (project / 'parser.py').read_text() == ORIGINAL
    assert db.latest_solution().model_dump_json() == saved


@pytest.mark.parametrize('method', ['recipe', 'llm'])
def test_unchallenged_proposals_keep_existing_application_flow(project, method):
    db, solution = proposal(project, method=method)
    apply = apply_solution if method == 'recipe' else apply_tested_proposal
    apply(project, db, solution)
    assert not solution.challenges
    assert db.latest_solution().status == 'applied'
    assert 'literal_eval' in (project / 'parser.py').read_text()


@pytest.mark.parametrize('method', ['recipe', 'llm'])
def test_cli_rechecks_patch_after_display_before_application(project, monkeypatch, method):
    from typer.testing import CliRunner
    from surfaces.entrypoint import app
    db, solution = proposal(project, method=method)
    def changed_proposal(record, console):
        record.patch[0].new += '# changed after challenge\n'
    monkeypatch.setattr('surfaces.cli.commands.security.show_solution', changed_proposal)
    response = CliRunner().invoke(app, ['challenge', '--tests', 'python -m unittest test_contract', '--apply', '--json'])
    assert response.exit_code == 2
    assert response.stdout == ''
    assert (project / 'parser.py').read_text() == ORIGINAL
    saved = db.latest_solution()
    assert saved.status == solution.status
    assert not saved.challenges[-1].applied
