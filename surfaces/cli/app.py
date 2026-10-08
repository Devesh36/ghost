from __future__ import annotations

import asyncio
import json
import shlex
import sqlite3
from pathlib import Path
from watchdog.observers import Observer
import typer
from rich.panel import Panel
from rich.console import Console
from rich.syntax import Syntax
from config import theme as appearance
from core.agent_harness.orchestrator import debug as run_debug
from infrastructure.collectors.commands import recorded_run
from infrastructure.collectors.files import ChangeHandler, configured_ignores
from core.agent_harness.progress import progress_handler
from surfaces.shared.terminal.brand import activity
from bootstrap.runtime import session_for, model_provider
from infrastructure.database.repository import Database
from infrastructure.database.storage import StorageError
from infrastructure.database.locking import InvestigationBusy
from core.domain.types import Event, EventType, Session, now
from infrastructure.repository.git import root, state, git, GitError
from infrastructure.safety.guardrails.commands import UnsafeCommand
from surfaces.shared.terminal.console import (literal, show_status, show_timeline, show_report,
                                              show_sessions, show_investigations, show_watch_start,
                                              show_watch_event)
from surfaces.shared.terminal.runtime import terminal_console
from surfaces.shared.terminal.guide import Workflow, show_guide

app = typer.Typer(no_args_is_help=True, help="👻 Ghost: find security risks before you ship; verify repairs before applying")
console = terminal_console()


@app.command()
def guide(workflow: Workflow | None = typer.Argument(None, help="daily, review or repair; omit for an overview")):
    """Learn a practical Ghost workflow without running commands or requiring a repository."""
    show_guide(console, workflow)


@app.command()
def theme(name: str | None = typer.Argument(None, help="Theme name; omit to browse palettes"),
          preview: str | None = typer.Option(None, "--preview", help="Preview a theme without saving or switching"),
          json_output: bool = typer.Option(False, "--json", help="Print active and saved theme settings")):
    """Browse, preview or save a terminal theme; works outside a Git repository."""
    from surfaces.cli.commands.theme import run_theme
    run_theme(console, name, preview=preview, json_output=json_output)


def context(*, errors: Console | None = None) -> tuple[Path, Database]:
    target = errors or console
    try:
        repo = root(Path.cwd())
    except Exception as exc:
        target.print(literal(f'Ghost needs a Git repository: {exc}', style='red'))
        raise typer.Exit(2) from exc
    try:
        git(repo, "rev-parse", "--verify", "HEAD")
    except GitError as exc:
        target.print('Ghost needs an initial Git commit before starting a session.', style='red')
        raise typer.Exit(2) from exc
    try:
        return repo, Database(repo)
    except StorageError as exc:
        target.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from exc
    except sqlite3.Error as exc:
        target.print('Ghost could not open its database. Back up .ghost before inspecting '
                      'ghost.db, permissions or concurrent writers. Saved data has not been deleted.',
                      style='yellow')
        raise typer.Exit(2) from exc


@app.command()
def connect(provider: str | None = typer.Argument(None, help="codex, claude-code, claude, openai, compatible, openrouter or ollama"),
            model: str | None = typer.Option(None, help="Your provider's model ID; optional for Codex and Claude Code"),
            base_url: str | None = typer.Option(None, help="Credential-free API base URL"),
            key_env: str | None = typer.Option(None, help="Name of the environment variable containing your API key"),
            check: bool = typer.Option(False, "--check", help="Make an actual model request to test the connection"),
            json_output: bool = typer.Option(False, "--json", help="Print credential-free connection status")):
    """Connect an AI provider or inspect the current connection."""
    from surfaces.cli.commands.connect import run_connect
    repo, _ = context()
    run_connect(repo, console, provider, model=model, base_url=base_url,
                key_env=key_env, check=check, json_output=json_output)


@app.command()
def ask(question: list[str] = typer.Argument(..., help="A question for Ghost, quoted or as words"),
        include_context: bool = typer.Option(False, "--context", help="Share a summary of the latest saved audit, without source or logs"),
        finding: str | None = typer.Option(None, "--finding", help="Share one latest-audit finding by full ID or unique prefix")):
    """Ask the connected AI for advice; chat never executes commands."""
    from surfaces.shared.conversation import run_ask
    repo, db = context()
    run_ask(repo, db, console, " ".join(question), include_context=include_context, finding=finding)


@app.command()
def watch():
    """Watch source changes in a development session."""
    repo, db = context()
    git_state = state(repo, include_diff=False)
    session = Session(repository_path=str(repo), starting_commit=git_state["head"], branch=git_state["branch"])
    db.start(session)
    db.add_event(Event(session_id=session.id, event_type=EventType.GIT_STATE,
                       metadata={"status": git_state["status"][:4000], "head": git_state["head"]}))
    handler = ChangeHandler(repo, db, session.id, patterns=configured_ignores(repo),
                            callback=lambda e: show_watch_event(e, target=console))
    observer = Observer()
    observer.schedule(handler, str(repo), recursive=True)
    observer.start()
    show_watch_start(repo, session, target=console)
    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        handler.flush_all()
        db.end(session.id, now())
        console.print("[dim]Session ended.[/dim]")


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(ctx: typer.Context, command: str = typer.Argument(..., help="Command to execute, for example 'pytest -q'"),
        timeout: int = typer.Option(120, min=1, max=3600)):
    """Run a command, display output, and record its result."""
    repo, db = context()
    session = session_for(db, repo)
    try:
        full_command = shlex.join([*shlex.split(command), *ctx.args])
    except ValueError as exc:
        console.print(f"[red]Invalid command:[/red] {exc}")
        raise typer.Exit(2) from exc
    try:
        result = recorded_run(db, session.id, repo, full_command, timeout=timeout)
    except (UnsafeCommand, OSError) as exc:
        console.print(f"[red]Command blocked:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print(f"\n[dim]Ghost recorded exit {result.exit_code} in {result.duration:.2f}s[/dim]")
    raise typer.Exit(result.exit_code)


@app.command()
def find(timeout: int = typer.Option(120, min=1, max=600, help="Time budget per scanner, in seconds"),
         json_output: bool = typer.Option(False, "--json", help="Export findings, scope and recorded session context"),
         auth: bool = typer.Option(False, "--auth", help="Run the opt-in local owner/other-user contract"),
         auth_python: str | None = typer.Option(None, "--auth-python", help="Python environment for the local ASGI app"),
         candidate: bool = typer.Option(False, "--candidate", help="Test the private authorization candidate in a second worktree")):
    """Find Python and JavaScript/TypeScript security risks before shipping."""
    from surfaces.cli.commands.security import run_find
    if (auth_python or candidate) and not auth:
        console.print('Use --auth with --auth-python or --candidate.', style='yellow')
        raise typer.Exit(2)
    repo, db = context()
    run_find(repo, db, console, timeout=timeout, json_output=json_output, auth=auth, auth_python=auth_python, candidate=candidate)


@app.command()
def sandboxes(limit: int = typer.Option(20, min=1, max=1000, help="Maximum sandbox paths shown; JSON includes every inventoried path"),
              json_output: bool = typer.Option(False, "--json", help="Export read-only sandbox inventory and diagnostic exit code")):
    """Inspect leftover experiment paths without opening source or deleting anything."""
    from surfaces.cli.commands.sandboxes import run_sandboxes
    try:
        repo = root(Path.cwd())
    except GitError:
        message = 'Ghost needs a Git repository. Run this command inside your project.'
        if json_output:
            typer.echo(json.dumps({'complete': False, 'error': message, 'exit_code': 2}))
        else:
            console.print(message, style='yellow')
        raise typer.Exit(2) from None
    run_sandboxes(repo, console, limit=limit, json_output=json_output)


@app.command()
def scope(limit: int = typer.Option(20, min=1, max=1000, help="Maximum paths shown per group in terminal output"),
          json_output: bool = typer.Option(False, "--json", help="List all Git-visible paths by scanner category")):
    """Inspect scan candidates and blind spots without running a scan."""
    from surfaces.cli.commands.scope import run_scope
    repo, _ = context()
    run_scope(repo, console, limit=limit, json_output=json_output)


@app.command()
def auth(init: bool = typer.Option(False, "--init", help="Create a private example contract in .ghost/auth.json"),
         check: bool = typer.Option(False, "--check", help="Validate the private contract and app source without running project code"),
         prepare_candidate: bool = typer.Option(False, "--prepare-candidate", help="Copy the app into a private file for isolated fix testing"),
         candidate: bool = typer.Option(False, "--candidate", help="Test that candidate against the baseline in a separate worktree"),
         timeout: int = typer.Option(120, min=1, max=600, help="Time budget per scanner, in seconds"),
         json_output: bool = typer.Option(False, "--json", help="Export the combined review as JSON"),
         python: str | None = typer.Option(None, "--python", help="Python environment for the local ASGI app")):
    """Set up, validate or run a local cross-user access check."""
    repo, db = context()
    if sum((init, check, prepare_candidate, candidate)) > 1:
        console.print('Choose one of --init, --check, --prepare-candidate or --candidate.', style='yellow')
        raise typer.Exit(2)
    if init:
        if python or json_output:
            console.print('--init only creates a local example; remove --python and --json.', style='yellow')
            raise typer.Exit(2)
        from infrastructure.security.authorization import init_contract
        try:
            path = init_contract(repo)
        except FileExistsError:
            console.print('.ghost/auth.json already exists; edit it to define your local test actors.', style='yellow')
            raise typer.Exit(2) from None
        except (OSError, ValueError):
            console.print('Could not create a private .ghost/auth.json safely. Inspect .ghost and retry.', style='yellow')
            raise typer.Exit(2) from None
        console.print(f'Created {path}. Edit the app, path, test actors and protected marker, then run ghost auth --check.', markup=False)
        return
    if check:
        if python:
            message = '--check validates files without launching Python; use --python with an authorization run.'
            if json_output:
                typer.echo(json.dumps({'status': 'invalid', 'reason': message}))
            else:
                console.print(message, style='yellow')
            raise typer.Exit(2)
        from infrastructure.security.authorization import inspect_contract
        try:
            contract, source = inspect_contract(repo)
        except ValueError as exc:
            if json_output:
                typer.echo(json.dumps({'status': 'invalid', 'reason': str(exc)}))
            else:
                console.print(literal(str(exc), style='yellow'))
            raise typer.Exit(2) from None
        if json_output:
            typer.echo(json.dumps({'status': 'valid', 'runtime': contract.runtime,
                                   'app_source': source, 'cases': len(contract.cases),
                                   'project_code_executed': False}))
        else:
            kind = 'Python ASGI' if contract.runtime == 'python_asgi' else 'Node handler'
            if console.width < 38:
                count = len(contract.cases)
                summary = (f'{kind}\n{source}\n{count} case{"s" if count != 1 else ""}\n'
                           'No app code run\nNext:\nghost find --auth')
                title = 'AUTH / VALID'
            else:
                summary = (f'Runtime: {kind}\nApp source: {source}\nCases: {len(contract.cases)}\n'
                           'Project code was not run.\nNext: ghost find --auth')
                title = 'GHOST / AUTH CONTRACT VALID'
            body = literal(summary, multiline=True)
            console.print(Panel(body, title=title, border_style='green',
                                width=min(console.width, 72)))
        return
    if prepare_candidate:
        if python or json_output:
            console.print('--prepare-candidate only creates a private copy; remove --python and --json.', style='yellow')
            raise typer.Exit(2)
        from infrastructure.security.authorization import prepare_candidate as copy_candidate
        try:
            path = copy_candidate(repo)
        except FileExistsError:
            console.print('Candidate already exists in .ghost; edit it or remove it before preparing another.', style='yellow')
            raise typer.Exit(2) from None
        except (OSError, ValueError):
            console.print('Could not safely prepare a candidate. Check .ghost/auth.json and the app source.', style='yellow')
            raise typer.Exit(2) from None
        console.print(f'Created {path}. Edit this private copy, then run ghost auth --candidate.', markup=False)
        return
    from surfaces.cli.commands.security import run_find
    run_find(repo, db, console, timeout=timeout, json_output=json_output, auth=True, auth_python=python, candidate=candidate)


@app.command()
def solve(finding_id: str = typer.Argument(..., help="Finding ID or unique prefix from ghost find"),
          tests: str = typer.Option(..., "--tests", help="Existing Python test command; must collect and pass tests"),
          timeout: int = typer.Option(120, min=1, max=120, help="Timeout per verification command"),
          apply: bool = typer.Option(False, "--apply", help="Explicitly apply the patch after successful verification")):
    """Verify a supported Python repair in isolation, then ask before applying."""
    from surfaces.cli.commands.security import run_solve
    repo, db = context()
    run_solve(repo, db, console, finding_id, tests=tests, timeout=timeout, apply=apply)


@app.command()
def solution(json_output: bool = typer.Option(False, "--json", help="Export the latest repair record")):
    """Inspect the latest security repair, patch, and executable evidence."""
    from surfaces.cli.commands.security import show_solution
    _, db = context()
    result = db.latest_solution()
    if not result:
        if json_output:
            typer.echo("null")
        else:
            console.print("No security repair saved. Start with ghost find.")
        raise typer.Exit(1)
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_solution(result, console)


@app.command()
def audit(timeout: int = typer.Option(120, min=1, max=600, help="Scanner time budget in seconds"),
          json_output: bool = typer.Option(False, "--json", help="Emit the complete audit record as JSON")):
    """Audit Python source offline; exit 1 for findings, 2 for incomplete coverage."""
    from surfaces.cli.commands.audit import run_audit
    repo, db = context()
    run_audit(repo, db, console, timeout=timeout, json_output=json_output)


@app.command()
def audits(limit: int = typer.Option(20, min=1, max=1000, help="Maximum saved audits, newest first"),
           json_output: bool = typer.Option(False, "--json", help="Export full saved audit records and IDs")):
    """Browse security review history without running another scan."""
    from surfaces.shared.terminal.security_history import show_audits
    _, db = context()
    items = db.audits(limit)
    if json_output:
        typer.echo(json.dumps([item.model_dump(mode="json") for item in items], indent=2))
    else:
        show_audits(items, console)


@app.command()
def compare(base_id: str | None = typer.Option(None, '--base', help='Baseline audit ID or unique prefix; defaults to the previous saved audit'),
            audit_id: str | None = typer.Option(None, '--audit', help='Target audit ID or unique prefix; requires --base; defaults to latest'),
            limit: int = typer.Option(10, '--limit', min=1, max=1000, help='Terminal rows per category; JSON always includes all rows'),
            json_output: bool = typer.Option(False, '--json', help='Export static report-location comparison and exit policy')):
    """Compare saved reviews; exit 1 for new locations/escalations, 2 for coverage gaps."""
    from core.security.comparison import compare_audits
    from surfaces.shared.terminal.comparison import show_comparison
    _, db = context()
    try:
        if audit_id is not None and base_id is None:
            raise ValueError('Use --base with --audit to select both saved reviews explicitly.')
        if base_id is not None:
            baseline = db.resolve_audit(base_id)
            target = db.resolve_audit(audit_id) if audit_id is not None else db.latest_audit()
            if target is None:
                raise ValueError('No target audit saved. Run ghost find, then ghost audits.')
        else:
            items = db.audits(2)
            if len(items) < 2:
                raise ValueError('Two saved reviews are needed. Run ghost find before and after changes.')
            target, baseline = items
        result = compare_audits(baseline, target)
    except ValueError as exc:
        if json_output:
            typer.echo(json.dumps({'error': str(exc), 'exit_code': 2}))
        else:
            console.print(literal(str(exc)), style='yellow')
        raise typer.Exit(2) from exc
    if json_output:
        typer.echo(json.dumps({**result.model_dump(mode='json'), 'exit_code': result.exit_code}, indent=2))
    else:
        show_comparison(result, console, limit=limit)
    raise typer.Exit(result.exit_code)


@app.command()
def brief(audit_id: str | None = typer.Option(None, '--audit', help='Saved audit ID or unique prefix; defaults to latest'),
          limit: int = typer.Option(5, min=1, max=50, help='Maximum static candidates in the summary'),
          markdown: bool = typer.Option(False, '--markdown', help='Export a Markdown summary to stdout; review before sharing')):
    """Summarize saved security evidence and next steps without rescanning."""
    from surfaces.shared.terminal.brief import brief_markdown, show_brief
    _, db = context(errors=Console(stderr=True, no_color=True) if markdown else None)
    try:
        result = db.resolve_audit(audit_id) if audit_id is not None else db.latest_audit()
    except ValueError as exc:
        typer.echo(literal(str(exc)).plain, err=True)
        raise typer.Exit(2) from exc
    if result is None:
        typer.echo('No security review saved. Run ghost scope, then ghost find.', err=True)
        raise typer.Exit(1)
    if markdown:
        typer.echo(brief_markdown(result, limit=limit), nl=False)
    else:
        show_brief(result, console, limit=limit)


@app.command()
def findings(finding_id: str | None = typer.Option(None, "--id", help="Finding ID or unique prefix in the selected audit"),
             audit_id: str | None = typer.Option(None, "--audit", help="Saved audit ID or unique prefix; defaults to latest"),
             severity: str | None = typer.Option(None, "--severity", help="Show only HIGH, MEDIUM, LOW or UNDEFINED static findings"),
             limit: int = typer.Option(20, "--limit", min=1, max=1000, help="Maximum finding cards shown in terminal output"),
             json_output: bool = typer.Option(False, "--json", help="Emit the complete selected audit record as JSON")):
    """Read a saved security review; --audit selects history, including incomplete runs."""
    from surfaces.cli.commands.audit import show_audit
    if severity is not None:
        severity = severity.upper()
        if severity not in {'HIGH', 'MEDIUM', 'LOW', 'UNDEFINED'}:
            console.print('Use --severity HIGH, MEDIUM, LOW or UNDEFINED.', style='yellow')
            raise typer.Exit(2)
    if json_output and (finding_id is not None or severity is not None or limit != 20):
        console.print('Use --json without finding filters for the complete record; --audit selects a saved review.', style='yellow')
        raise typer.Exit(2)
    if finding_id is not None and (severity is not None or limit != 20):
        console.print('Use --id alone for one finding; --severity and --limit filter the list.', style='yellow')
        raise typer.Exit(2)
    _, db = context()
    try:
        result = db.resolve_audit(audit_id) if audit_id is not None else db.latest_audit()
    except ValueError as exc:
        console.print(str(exc), style='yellow', markup=False)
        raise typer.Exit(2) from exc
    if not result:
        if json_output:
            typer.echo("null")
        else:
            console.print("No security audit saved. Start with ghost find.")
        raise typer.Exit(1)
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_audit(result, console, finding_id=finding_id, severity=severity, limit=limit,
                   historical=audit_id is not None)


@app.command()
def retry(dry_run: bool = typer.Option(False, "--dry-run", help="Preview and validate the saved command without executing it"),
          timeout: int = typer.Option(120, min=1, max=3600, help="Command timeout in seconds; defaults to 120")):
    """Rerun the latest session's last failed command in the current working tree."""
    from surfaces.cli.commands.retry import retry_command
    repo, db = context()
    retry_command(repo, db, console, dry_run=dry_run, timeout=timeout)


def selected_session(db: Database, selector: str | None) -> Session | None:
    if selector is None:
        return db.latest_session()
    try:
        return db.resolve_session(selector)
    except ValueError as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(2) from exc


@app.command()
def sessions(limit: int = typer.Option(20, min=1, max=1000),
             json_output: bool = typer.Option(False, "--json", help="Emit saved sessions with full IDs as JSON")):
    """Browse saved sessions, newest first; use --session ID on inspection commands."""
    import json
    _, db = context()
    items = db.sessions(limit)
    if json_output:
        typer.echo(json.dumps([item.model_dump() for item in items], indent=2))
    else:
        show_sessions(items, target=console)


@app.command()
def status(session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Show a saved session summary."""
    repo, db = context()
    session = selected_session(db, session_id)
    if not session:
        console.print("No Ghost session yet. Run ghost watch or ghost run.")
        return
    show_status(session, db.events(session.id, limit=100000))


@app.command()
def timeline(limit: int = typer.Option(50, min=1, max=1000),
             session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Show recent development events for a saved session."""
    repo, db = context()
    session = selected_session(db, session_id)
    if not session:
        console.print("No Ghost session yet.")
        return
    show_timeline([e for e in db.events(session.id, limit) if e.event_type != EventType.AGENT_ACTION])


@app.command()
def debug(apply: bool = typer.Option(False, "--apply", help="Apply a verified patch without an interactive prompt"),
          max_commands: int = typer.Option(24, min=1, max=100, help="Maximum experiment and verification commands"),
          time_budget: int = typer.Option(600, min=1, max=3600, help="Investigation time budget in seconds")):
    """Investigate the latest recorded failure in isolated worktrees."""
    repo, db = context()
    session = session_for(db, repo)
    provider = model_provider(repo)
    try:
        from core.agent_harness.execution import ExecutionLimits
        with progress_handler(activity):
            result = asyncio.run(run_debug(repo, db, session.id, provider, console, apply=apply,
                                          limits=ExecutionLimits(max_commands=max_commands, wall_timeout=time_budget)))
    except InvestigationBusy as exc:
        console.print("Investigation not started", style="bold yellow")
        console.print(str(exc), markup=False)
        raise typer.Exit(2) from exc
    except Exception as exc:
        console.print(f"[red]Investigation stopped:[/red] {exc}")
        raise typer.Exit(2) from exc
    for note in result.notes:
        console.print(f"[yellow]•[/yellow] {note}")
    if not result.root_cause:
        console.print("[yellow]Root cause not established.[/yellow]")
    elif not result.patch_verified:
        console.print(f"[yellow]Cause identified ({result.confidence}), but no verified patch is available.[/yellow]")
    if result.status in {"failed", "stopped", "cancelled"} or not result.patch_verified or (apply and not result.applied):
        raise typer.Exit(1)


@app.command()
def failures(limit: int = typer.Option(10, min=1, max=100),
             output: bool = typer.Option(False, "--output", help="Include the tail of captured stdout and stderr"),
             session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """List failed commands from a saved session."""
    _, db = context()
    session = selected_session(db, session_id)
    events = db.events(session.id, limit=100000) if session else []
    failed = [event for event in events if event.event_type == EventType.COMMAND_FINISHED
              and event.exit_code != 0][-limit:]
    if not failed:
        console.print("No recorded failures in this session. Use ghost sessions to browse others.")
        return
    show_timeline(failed)
    if output:
        for event in failed:
            console.print(f"\n{event.command} (exit {event.exit_code})", style="bold", markup=False)
            for label, content in (("stdout", event.stdout), ("stderr", event.stderr)):
                if content:
                    console.print(f"{label} (last 4,000 characters)", style="dim")
                    console.print(content[-4000:], markup=False, highlight=False)


@app.command()
def investigations(limit: int = typer.Option(20, min=1, max=1000),
                   json_output: bool = typer.Option(False, "--json", help="Emit full saved investigation records as JSON"),
                   session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Browse a session's saved investigations, newest start time first."""
    import json
    _, db = context()
    session = selected_session(db, session_id)
    items = db.investigations(session.id, limit) if session else []
    if json_output:
        typer.echo(json.dumps([item.model_dump(mode="json") for item in items], indent=2))
    else:
        show_investigations(items, target=console)


@app.command()
def report(json_output: bool = typer.Option(False, "--json", help="Emit the saved investigation as JSON"),
           investigation_id: str | None = typer.Option(None, "--id", help="Investigation ID or unique prefix; searches all sessions unless --session is provided"),
           session_id: str | None = typer.Option(None, "--session", "-s", help="Saved session ID or unique prefix; defaults to latest")):
    """Read saved evidence by ID, or the latest investigation in a session."""
    _, db = context()
    session = selected_session(db, session_id)
    if investigation_id is not None:
        try:
            result = db.resolve_investigation(investigation_id, session.id if session_id is not None and session else None)
        except ValueError as exc:
            console.print(str(exc), style="red", markup=False)
            raise typer.Exit(2) from exc
    else:
        result = db.latest_investigation(session.id) if session else None
    if not result:
        if json_output:
            typer.echo("null")
        else:
            console.print("No investigation saved for this session. Use ghost sessions to browse others; ghost debug investigates the current session.")
        return
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_report(result)


@app.command()
def diff():
    """Inspect tracked changes against HEAD, including staged changes."""
    repo, _ = context()
    changes = git(repo, "diff", "HEAD", "--no-ext-diff", "--no-textconv", "--", ".", ":(exclude).ghost")
    if changes:
        console.print(Syntax(changes, "diff", theme=appearance.current().code_theme, word_wrap=True))
    else:
        console.print("No tracked changes against HEAD.")
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "--", ".", ":(exclude).ghost").strip()
    if untracked:
        console.print("\nUntracked files (not included in the diff):", style="dim")
        console.print(untracked, markup=False)


@app.command()
def doctor(json_output: bool = typer.Option(False, "--json", help="Emit machine-readable environment checks"),
           strict: bool = typer.Option(False, "--strict", help="Exit nonzero for warnings as well as failed checks")):
    """Check prerequisites and storage paths; execute a sandbox write/network probe."""
    import json
    from surfaces.cli.commands.doctor import diagnose, show_doctor
    checks = diagnose(Path.cwd())
    blocked = any(check.status == 'fail' or (strict and check.status == 'warn') for check in checks)
    exit_code = int(blocked)
    if json_output:
        typer.echo(json.dumps({"checks": [check.model_dump() for check in checks],
                               "strict": strict, "exit_code": exit_code}, indent=2))
    else:
        show_doctor(console, checks, strict=strict)
    if blocked:
        raise typer.Exit(exit_code)


@app.command()
def demo(keep: bool = typer.Option(False, "--keep", help="Keep the generated sample repository and investigation report"),
         security: bool = typer.Option(False, "--security", help="Show real Python + TypeScript findings and a verified Python repair")):
    """Watch Ghost find and fix a real bug in a temporary sample project."""
    from surfaces.cli.commands.demo import run_demo
    try:
        if security:
            from surfaces.cli.commands.security_demo import run_security_demo
            run_security_demo(console, keep=keep)
        else:
            asyncio.run(run_demo(console, keep=keep))
    except Exception as exc:
        console.print(f"Demo stopped: {exc}", style="red", markup=False)
        raise typer.Exit(1) from exc
