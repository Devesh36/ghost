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


@contextmanager
def conversation_scope(conversation):
    token = _conversation.set(conversation)
    try:
        yield
    finally:
        _conversation.reset(token)


def audit_summary(db, *, finding=None):
    return audit_context(db.latest_audit(), finding=finding)


def run_ask(repo, db, console, question, *, include_context=False, finding=None, conversation=None):
    conversation = conversation or _conversation.get() or Conversation()
    sharing = include_context or finding is not None
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
            answer = asyncio.run(conversation.ask(provider, question, evidence=evidence))
        show_answer(console, answer)
    except (ProviderError, ModelInputBlocked, ValueError) as exc:
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
    except Exception:
        console.print('AI request failed safely. Run ghost connect --check to inspect the connection.', style='yellow')
        raise typer.Exit(2) from None
