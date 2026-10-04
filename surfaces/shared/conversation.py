"""CLI and REPL assistant presentation, with explicit saved-audit sharing."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar

import typer
from rich.text import Text

from bootstrap.providers import load_provider
from core.llm.conversation import CAPABILITIES, Conversation, capabilities_question
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


def audit_summary(db):
    audit = db.latest_audit()
    if audit is None:
        return {'status': 'no saved audit'}
    return {'id': audit.id, 'started_at': audit.started_at, 'status': audit.status, 'scope': audit.scope,
            'files_scanned': len(audit.files), 'unsupported_files': audit.unsupported_files,
            'excluded_files': audit.excluded_files, 'total_static_findings': len(audit.findings),
            'findings_limit': 20,
            'static_findings': [item.model_dump(include={'id', 'rule', 'path', 'line', 'severity', 'confidence', 'state'})
                                for item in audit.findings[:20]],
            'authorization_verdicts': [item.verdict for item in audit.authorization]}


def run_ask(repo, db, console, question, *, include_context=False, conversation=None):
    conversation = conversation or _conversation.get() or Conversation()
    try:
        provider = load_provider(repo)
    except ValueError as exc:
        if capabilities_question(question) and not include_context:
            show_answer(console, CAPABILITIES, guide=True)
            return
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
    try:
        evidence = audit_summary(db) if include_context else None
        if include_context:
            console.print(Text('Sharing saved audit metadata; no source or command output.', style=theme.MUTED))
        with activity(console, 'Asking the connected model'):
            answer = asyncio.run(conversation.ask(provider, question, evidence=evidence))
        show_answer(console, answer)
    except (ProviderError, ModelInputBlocked, ValueError) as exc:
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
    except Exception:
        console.print('AI request failed safely. Run ghost connect --check to inspect the connection.', style='yellow')
        raise typer.Exit(2) from None
