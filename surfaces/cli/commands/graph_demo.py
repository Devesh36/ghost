"""One-command, recording-friendly presentation of the live FalkorDB walkthrough."""
import json
import sys

import typer

from core.security.graph_triage import TriageError
from infrastructure.security.graph_demo import walkthrough
from surfaces.shared.terminal.graph_triage import show_triage


def run_graph_demo(console, *, port=6379, pause=True, json_output=False):
    interactive = pause and not json_output and sys.stdin.isatty() and console.file.isatty()
    headings = {
        'baseline': '1/3 · Query the original relationships',
        'incident_link_removed': '2/3 · Remove F-002 → INC-042 and query again',
        'restored': '3/3 · Restore the incident link and query again',
    }

    def show_stage(stage, answer):
        console.rule(headings[stage])
        show_triage(answer, console, export_command='ghost demo --graph --json')
        if interactive and stage != 'restored':
            action = 'remove the incident link' if stage == 'baseline' else 'restore the incident link'
            console.input(f'\nPress Enter to {action} and query FalkorDB again (Ctrl+C to stop). ')

    if not json_output:
        console.print('Ghost × FalkorDB / live graph demo', markup=False)
        console.print('Three real queries per stage. Synthetic data. A separate temporary graph.', markup=False)
    try:
        result = walkthrough(port, on_stage=None if json_output else show_stage)
    except TriageError as exc:
        typer.echo(str(exc), err=True)
        typer.echo('Setup: install Ghost with the graph extra and start local FalkorDB. See docs/graph-hacks.md.', err=True)
        raise typer.Exit(2) from None
    except (KeyboardInterrupt, EOFError):
        typer.echo('Graph demo stopped. The temporary graph was cleaned up.', err=True)
        raise typer.Exit(130) from None
    except (ValueError, TypeError, KeyError):
        typer.echo('FalkorDB returned inconsistent demo evidence; no recorded answer was substituted.', err=True)
        raise typer.Exit(2) from None
    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        console.print('\nVerified: F-002 (115) → F-003 (75) → F-002 (115).', markup=False)
        console.print('Only a graph relationship changed. Temporary graph deleted; your normal demo is preserved.', markup=False)
