"""Read-only workflow guidance shared by the CLI and interactive shell."""
from enum import Enum

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from config import theme




class Workflow(str, Enum):
    daily = 'daily'
    review = 'review'
    repair = 'repair'


# Commands are examples, never queued actions. Keep scope and proof limitations explicit.
WORKFLOWS = {
    Workflow.daily: (
        'While you code', 'Remember changes and make failures easier to investigate.',
        (
            ('Remember edits', 'watch', 'Records source edits in this REPL while you use your editor. Use unwatch to stop.'),
            ('Record your tests', 'run python -m pytest -q', 'Captures output and the result. Replace pytest with your project\'s test command.'),
            ('Understand a failure', 'failures --output', 'Read recorded failures; use debug to investigate one in isolated worktrees.'),
            ('Review your session', 'timeline --limit 20', 'See how edits and commands relate. Only watched edits and Ghost-run commands are recorded.'),
        ),
    ),
    Workflow.review: (
        'Before you ship', 'Review security candidates and understand what was actually checked.',
        (
            ('Check coverage', 'scope', 'See selected Python and JavaScript/TypeScript files, exclusions and blind spots.'),
            ('Find candidates', 'find', 'Run local static checks. Findings are suspected risks, not confirmed exploits.'),
            ('Read the evidence', 'findings', 'Inspect severity, paths and IDs. Use findings --id <id> for one finding; audits lists earlier reviews for findings --audit <audit-id>.'),
            ('Check user access', 'auth --init', 'Create a local access-check template. Configure test users and cases, then use auth --check and auth to run the configured checks.'),
        ),
    ),
    Workflow.repair: (
        'Repair a finding', 'Require executable evidence before changing your project.',
        (
            ('Choose a finding', 'findings', 'Copy a finding ID from the latest audit. Only supported Python recipes can be repaired today.'),
            ('Verify in isolation', 'solve <id> --tests "python -m pytest -q"', 'Replace <id> and the test command. Ghost tests the original behavior and proposed patch in a worktree, then asks before applying. Answer N to inspect it first.'),
            ('Review the patch', 'solution', 'Inspect the saved patch, probe results and project tests. Failed verification is not a verified repair.'),
            ('Approve and recheck', 'find', 'When ready, run solve again and approve its verified patch at the prompt. Then rerun find and your project tests. A clean scan is not deployment approval.'),
        ),
    ),
}


def guide_card(console: Console, body: Text, title: str | Text) -> None:
    if console.width < 36:
        console.print(Text(str(title), style=f'bold {theme.TEXT}'))
        console.print(body)
        console.print()
    else:
        console.print(Panel(body, title=title, title_align='left',
                            box=box.ROUNDED, border_style=theme.BORDER, padding=(0, 1)))


def show_guide(console: Console, workflow: Workflow | None = None, *, repl: bool = False) -> None:
    prefix = '' if repl else 'ghost '
    console.print(Text('\n  Ghost / Your workflow', style=f'bold {theme.TEXT}'))
    if workflow is None:
        console.print(Text('  Find security risks, inspect evidence, verify supported repairs.', style=theme.MUTED))
        for choice, (title, benefit, _) in WORKFLOWS.items():
            body = Text()
            body.append(title + '\n', style=f'bold {theme.TEXT}')
            body.append(benefit + '\n\n', style=theme.MUTED)
            body.append(prefix + 'guide ' + choice.value, style=theme.MINT)
            guide_card(console, body, choice.value)
        console.print(Text('  Try a disposable sample: ' + prefix + 'demo --security', style=theme.VIOLET))
    else:
        title, benefit, steps = WORKFLOWS[workflow]
        console.print(Text('  ' + title + '\n  ' + benefit, style=theme.MUTED))
        console.print()
        for number, (label, command, explanation) in enumerate(steps, 1):
            body = Text()
            body.append(prefix + command + '\n\n', style=theme.MINT)
            if console.width < 36:
                explanation = explanation.replace('JavaScript/TypeScript', 'JS/TS')
            body.append(explanation, style=theme.MUTED)
            guide_card(console, body, Text(f'{number} / {label}', style=theme.TEXT))
        if workflow == Workflow.daily and not repl:
            console.print(Text('  Start with ghost repl: watch stays in the background there.\n'
                               '  Standalone ghost watch occupies its terminal until Ctrl-C.', style=theme.MUTED))
    console.print(Text('  Examples only; nothing has run. Replace <id> and test commands for your project.', style=theme.MUTED))
    console.print(Text('  Ask for advice: ' + prefix + 'ask "What should I review first?"\n'
                       '  AI setup: ' + prefix + 'connect --help  /  Command help: ' +
                       ('help <command>' if repl else 'ghost <command> --help'), style=theme.MUTED))
    console.print()
