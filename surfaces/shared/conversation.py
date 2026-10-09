"""CLI and REPL assistant presentation, with explicit saved-audit sharing."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar

import typer
from rich.text import Text

from bootstrap.providers import load_provider
from core.llm.conversation import CAPABILITIES, Conversation, capabilities_question
from core.llm.audit_context import audit_context
from core.llm.transport import ProviderError
from infrastructure.safety.masking.model_input import ModelInputBlocked
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal
from surfaces.shared.terminal.assistant import show_answer
from config import theme

_conversation = ContextVar('ghost_chat', default=None)
_executor = ContextVar('ghost_chat_executor', default=None)


@contextmanager
def conversation_scope(conversation, execute=None):
    token = _conversation.set(conversation)
    action_token = _executor.set(execute)
    try:
        yield
    finally:
        _conversation.reset(token)
        _executor.reset(action_token)


def audit_summary(db, *, finding=None):
    return audit_context(db.latest_audit(), finding=finding)


def run_ask(repo, db, console, question, *, include_context=False, finding=None, conversation=None, execute=None, advice_only=False):
    conversation = conversation or _conversation.get() or Conversation()
    sharing = include_context or finding is not None
    execute = None if advice_only or sharing else (execute or _executor.get())
    if not question.strip() or len(question.encode('utf-8')) > 8192:
        console.print('Ask a nonempty question of at most 8 KB.', style='yellow')
        raise typer.Exit(2)
    if execute is None:
        conversation.pending_action = None
    if execute is not None:
        from surfaces.shared.chat_actions import handle_direct
        if handle_direct(repo, console, conversation, question, execute):
            return
    try:
        evidence = audit_summary(db, finding=finding) if sharing else None
    except ValueError as exc:
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
    try:
        provider = load_provider(repo)
    except ValueError as exc:
        if capabilities_question(question) and not sharing:
            show_answer(console, CAPABILITIES, guide=True)
            return
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
    try:
        if sharing:
            console.print(Text('Sharing saved audit metadata; no source or command output.', style=theme.MUTED))
            if 'static_findings' in evidence:
                console.print(Text(f'Included {len(evidence["static_findings"])} of '
                                   f'{evidence["total_static_findings"]} findings; '
                                   f'{evidence["findings_omitted"]} omitted.', style=theme.MUTED))
                if evidence['truncated_fields'] or evidence['authorization_verdicts_omitted']:
                    console.print(Text('Some audit fields or authorization verdicts were shortened or omitted. '
                                       'Use ghost findings for the saved evidence.', style=theme.MUTED))
        with activity(console, 'Asking the connected model'):
            if execute is not None and hasattr(provider, 'tool_call') and not capabilities_question(question):
                reply = asyncio.run(conversation.propose(provider, question))
                answer = reply.reply
            else:
                reply = None
                answer = asyncio.run(conversation.ask(provider, question, evidence=evidence))
        show_answer(console, answer, actions_enabled=execute is not None)
        if reply is not None:
            from surfaces.shared.chat_actions import offer_action
            offer_action(repo, console, conversation, question, reply.action)
    except (ProviderError, ModelInputBlocked, ValueError) as exc:
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
    except Exception:
        console.print('AI request failed safely. Run ghost connect --check to inspect the connection.', style='yellow')
        raise typer.Exit(2) from None
