"""Terminal rendering and interactive approval for the investigation reporter."""
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
import typer

from core.agent_harness.reporting import (
    EvidenceGathered, ExperimentFinished, FailureReproduced, HypothesesJudged,
    InvestigationEvent, PatchReview, PatchVerified, Reproducing, Started,
)
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal


class TerminalReporter:
    def __init__(self, console: Console):
        self.console = console

    def activity(self, label: str):
        return activity(self.console, literal(label).plain)

    def publish(self, event: InvestigationEvent) -> None:
        console = self.console
        if isinstance(event, Started):
            console.rule('👻 Ghost Investigation')
        elif isinstance(event, EvidenceGathered):
            console.print('[green]✓[/green] Code, Git, and runtime evidence gathered.')
            console.print(f'[green]✓[/green] {event.hypotheses} testable hypotheses generated.')
        elif isinstance(event, Reproducing):
            console.print(Text('Reproducing ', style='cyan') + literal(event.command))
        elif isinstance(event, FailureReproduced):
            console.print(f'[green]✓[/green] Failure reproduced. Testing {event.hypotheses} hypotheses.')
        elif isinstance(event, ExperimentFinished):
            marker = '[green]✓[/green]' if event.supported else '[yellow]–[/yellow]'
            console.print(Text.from_markup(marker) + literal(f' {event.hypothesis_id}: {event.conclusion}'))
        elif isinstance(event, HypothesesJudged):
            table = Table(title='Hypothesis evidence', box=None)
            table.add_column('ID', no_wrap=True)
            table.add_column('Hypothesis')
            table.add_column('Result')
            for row in event.rows:
                table.add_row(literal(row.id), literal(row.title), literal(row.status))
            console.print(table)
        elif isinstance(event, PatchVerified):
            console.print('[green]✓[/green] Patch verified in a sandbox.')
        elif isinstance(event, PatchReview):
            console.print(Panel.fit(Text('Root cause found\n', style='bold green')
                + literal(f'{event.root_cause}\nConfidence: {event.confidence}\n'
                          'Reproduced ✓  Hypothesis tested ✓  Patch verified ✓', multiline=True),
                title='👻 Ghost Investigation', border_style='green'))
            console.print('\n[bold]Evidence[/bold]')
            console.print(f'• Control command failed with exit {event.control_exit_code}.')
            for evidence in event.evidence:
                console.print(literal('• ' + evidence))
            if event.rejected:
                console.print('\n[bold]Rejected hypotheses[/bold]')
                for rejected in event.rejected:
                    console.print(literal('• ' + rejected))
            console.print('\n[bold]Patch[/bold]')
            for patch in event.patches:
                console.print(literal(patch.diff, multiline=True))
            table = Table(title='Verification', box=None)
            table.add_column('Command')
            table.add_column('Exit', justify='right')
            table.add_column('Duration', justify='right')
            for row in event.verification:
                table.add_row(literal(row.command), str(row.exit_code), f'{row.duration:.2f}s')
            console.print(table)

    def approve_patch(self, review: PatchReview) -> bool:
        if not sys.stdin.isatty():
            return False
        return typer.confirm('Apply verified patch to working tree?', default=False)
