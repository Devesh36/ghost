"""Deterministic host routing and fake-provider proposals; no live model calls."""
import io
import json
import subprocess

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

from core.llm.actions import Action, PendingAction, arguments, direct_action
from core.llm.base import FakeProvider
from core.llm.conversation import Conversation
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.shared.conversation import run_ask


@pytest.fixture
def project(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', '--template=', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '--allow-empty', '-qm', 'baseline'], check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path, Database(tmp_path)


@pytest.mark.parametrize('question, action', [('scan this project', Action.SCAN),
    ('show my findings', Action.FINDINGS), ('what are finding which you have find?', Action.FINDINGS),
    ('summarize the findings', Action.BRIEF), ('review this repo', Action.REVIEW),
    ('fix the parser', Action.FIX), ('show my changes', Action.DIFF)])
def test_explicit_workflows_route_without_model(project, monkeypatch, question, action):
    repo, db = project
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: pytest.fail('No model needed'))
    calls = []
    run_ask(repo, db, Console(file=io.StringIO()), question, execute=lambda argv: calls.append(argv))
    assert calls == [arguments(action, question)]


def test_fake_typed_proposal_needs_followup_and_cannot_supply_flags(project, monkeypatch):
    repo, db = project
    provider = FakeProvider([{'reply': 'I can collect local scan evidence.', 'action': 'scan'}])
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: provider)
    conversation, calls, output = Conversation(), [], io.StringIO()
    console = Console(file=output, width=120)
    run_ask(repo, db, console, 'Investigate potential security problems here', conversation=conversation, execute=calls.append)
    assert not calls and conversation.pending_action.action == Action.SCAN
    assert json.loads(provider.calls[0][1])['saved_audit_summary'] is None
    run_ask(repo, db, console, 'do that for me', conversation=conversation, execute=calls.append)
    assert calls == [['find']] and conversation.pending_action is None
    run_ask(repo, db, console, 'yes', conversation=conversation, execute=calls.append)
    assert len(calls) == 1 and 'Nothing has run' in output.getvalue()


@pytest.mark.parametrize('payload', [{'reply': 'Run this', 'action': 'run'},
    {'reply': 'scan', 'action': 'scan', 'command': 'rm -rf .'},
    {'reply': 'scan', 'action': ['scan']}, {'reply': '', 'action': 'scan'}])
def test_malformed_or_arbitrary_commands_never_run(project, monkeypatch, payload):
    repo, db = project
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: FakeProvider([payload]))
    calls, conversation = [], Conversation()
    with pytest.raises(typer.Exit):
        run_ask(repo, db, Console(file=io.StringIO()), 'Please investigate this workspace', conversation=conversation, execute=calls.append)
    assert not calls and conversation.pending_action is None


@pytest.mark.parametrize('reply', ['```sh\nrm -rf .\n```', 'Run ghost find --llm --apply now'])
def test_plain_model_text_is_inert(project, monkeypatch, reply):
    repo, db = project
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: FakeProvider([{'reply': reply, 'action': None}]))
    calls = []
    run_ask(repo, db, Console(file=io.StringIO()), 'What might help here?', execute=calls.append)
    assert not calls


@pytest.mark.parametrize('followup', ['cancel', 'forget', 'other repo', 'new question'])
def test_pending_actions_clear_or_expire(project, monkeypatch, followup):
    repo, db = project
    conversation, calls = Conversation(), []
    conversation.pending_action = PendingAction(action=Action.FIX, request='repair parser', repository=str(repo.resolve()))
    console = Console(file=io.StringIO())
    if followup == 'forget':
        conversation.clear()
    elif followup == 'other repo':
        conversation.pending_action.repository = str(repo.parent)
    elif followup == 'new question':
        monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: FakeProvider([{'reply': 'Advice', 'action': None}]))
        run_ask(repo, db, console, 'What is happening?', conversation=conversation, execute=calls.append)
    else:
        run_ask(repo, db, console, followup, conversation=conversation, execute=calls.append)
    run_ask(repo, db, console, 'yes', conversation=conversation, execute=calls.append)
    assert not calls and conversation.pending_action is None


def test_fix_request_remains_literal(project, monkeypatch):
    request = 'fix parser --apply --llm; touch hacked'
    assert arguments(Action.FIX, request) == ['fix', '--', request]
    assert direct_action("don't scan this project") is None
    repo, _ = project
    monkeypatch.setattr('surfaces.cli.commands.fix.load_provider', lambda _: pytest.fail('No flags may be injected'))
    result = CliRunner().invoke(app, ['ask', request])
    assert result.exit_code == 2 and '--path' in result.output
    assert not (repo / 'hacked').exists()


def test_one_shot_chat_executes_real_local_scan_without_provider(project):
    repo, db = project
    (repo / 'parser.py').write_text('def parse(value):\n    return eval(value)\n')
    result = CliRunner().invoke(app, ['chat', 'scan this project'])
    assert result.exit_code == 0, result.output
    assert 'Ghost action: find' in result.output
    assert db.latest_audit().findings


def test_noninteractive_chat_needs_prompt(project):
    result = CliRunner().invoke(app, ['chat'])
    assert result.exit_code == 2 and 'interactive terminal' in result.output


def test_scan_failure_does_not_claim_success(project):
    repo, db = project
    conversation = Conversation()
    with pytest.raises(typer.Exit):
        run_ask(repo, db, Console(file=io.StringIO()), 'scan this project', conversation=conversation, execute=lambda _: 2)
    assert 'exit 2' in conversation.history[-1]['content']


def test_expired_action_cannot_execute(project):
    repo, db = project
    conversation, calls = Conversation(), []
    conversation.pending_action = PendingAction(action=Action.SCAN, request='scan', repository=str(repo.resolve()), created_at=0)
    run_ask(repo, db, Console(file=io.StringIO()), 'yes', conversation=conversation, execute=calls.append)
    assert not calls and conversation.pending_action is None


def test_advisory_question_clears_pending_action(project, monkeypatch):
    repo, db = project
    conversation, calls = Conversation(), []
    conversation.pending_action = PendingAction(action=Action.FIX, request='fix', repository=str(repo.resolve()))
    monkeypatch.setattr('surfaces.shared.conversation.load_provider', lambda _: FakeProvider([{'reply': 'advice'}]))
    run_ask(repo, db, Console(file=io.StringIO()), 'What next?', conversation=conversation, execute=calls.append, advice_only=True)
    run_ask(repo, db, Console(file=io.StringIO()), 'yes', conversation=conversation, execute=calls.append)
    assert not calls
