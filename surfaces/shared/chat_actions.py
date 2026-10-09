"""Execute approved typed workflows through the caller's ordinary CLI guards."""
import shlex
import time

import typer

from core.llm.actions import ACCEPT, DECLINE, PendingAction, arguments, direct_action, normalized
from surfaces.shared.terminal.console import literal


def execute_action(repo, console, conversation, question, action, execute):
    argv = arguments(action, question)
    conversation.pending_action = None
    console.print(literal('Ghost action: ' + shlex.join(argv)))
    try:
        result = execute(argv)
        code = result if isinstance(result, int) else 0
    except typer.Exit as exc:
        code = exc.exit_code
    conversation.remember(question, f'Host workflow {action.value} finished with exit {code}. '
                          'This alone does not establish a scan was clean or a patch was applied.')
    if code not in ({0, 1} if action.value == 'scan' else {0}):
        console.print('Workflow blocked or incomplete. No successful action is claimed; inspect the result above.', style='yellow')
        raise typer.Exit(code or 2)


def handle_direct(repo, console, conversation, question, execute):
    text = normalized(question)
    if text in DECLINE and conversation.pending_action:
        conversation.pending_action = None
        console.print('Proposed action cancelled. No workflow ran.')
        return True
    if text in ACCEPT:
        pending = conversation.pending_action
        conversation.pending_action = None
        if pending is None:
            console.print('No pending action. Tell Ghost what to do, for example: scan this project.')
        elif time.monotonic() - pending.created_at > 300:
            console.print('The proposed action expired. Request it again; nothing ran.', style='yellow')
        elif pending.repository != str(repo.resolve()):
            console.print('The repository changed. Request the action again in this workspace.', style='yellow')
        else:
            execute_action(repo, console, conversation, pending.request, pending.action, execute)
        return True
    # A new request supersedes an old offer; "yes" cannot approve stale advice.
    conversation.pending_action = None
    action = direct_action(question)
    if action is None:
        return False
    execute_action(repo, console, conversation, question, action, execute)
    return True


def offer_action(repo, console, conversation, question, action):
    if action is None:
        return
    conversation.pending_action = PendingAction(action=action, request=question, repository=str(repo.resolve()))
    console.print(literal('Proposed Ghost workflow: ghost ' + shlex.join(arguments(action, question))))
    console.print('Nothing has run. Say "do that for me" to run this workflow, or "cancel". '
                  'Source sharing and patch application still require their own approval. '
                  'Offers live only in this conversation; for one-shot chat, run the printed Ghost command or open ghost chat.')
