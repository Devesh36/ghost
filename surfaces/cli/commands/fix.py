"""One requested application change through existing isolated repair gates."""
from uuid import uuid4

import typer

from bootstrap.providers import load_provider
from core.security.llm_solver import eligible_target, solve_with_llm, apply_tested_proposal
from core.security.models import LLMFinding
from core.security.test_runners import select_runner
from infrastructure.database.locking import investigation_lock
from infrastructure.safety.masking.model_input import validate_model_input
from infrastructure.security.review import find_risks, inventory
from surfaces.cli.commands.security import show_solution
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal
from surfaces.shared.terminal.runtime import interactive_console


def run_fix(repo, db, console, request, *, path, tests, llm, apply, timeout):
    try:
        if not request.strip() or len(request.encode('utf-8')) > 8192:
            raise ValueError('Requested change must be nonempty and at most 8 KB.')
        validate_model_input(request)
        interactive = interactive_console(console)
        if not path:
            if not interactive:
                raise ValueError('Choose one application file with --path and an explicit --tests command. Example: ghost fix "change parser" --path parser.cjs --tests "node --test test/parser.test.cjs" --llm')
            candidates = sorted(p for p in inventory(repo) if eligible_target(p) and p.endswith(('.py', '.js', '.mjs', '.cjs')))
            for candidate in candidates[:30]:
                console.print(literal(candidate))
            if len(candidates) > 30:
                console.print(f'{len(candidates) - 30} more application files; select an exact repository-relative path.')
            path = typer.prompt('Application file to change')
        if not eligible_target(path) or path not in inventory(repo):
            raise ValueError('Select a Git-visible application source file inside this repository; tests and credentials are excluded.')
        if not tests:
            if not interactive:
                raise ValueError('Select tests explicitly with --tests. Commands from the model are never executed.')
            tests = typer.prompt('Test command (Python pytest/unittest, or Node --test with one plain JS test file)')
        # Reject unsupported language/runner/arguments before sharing source or scanning.
        select_runner(tests, path, repo)
        if not llm and not (interactive and typer.confirm('Allow Ghost to send this request and selected source file to your configured LLM?', default=False)):
            console.print('LLM assistance declined. No request sent and no source changed. Use --llm to opt in explicitly.')
            raise typer.Exit(2)
        provider = load_provider(repo)
        console.print('LLM assistance shares the selected application file and request. One replacement is tested; tests do not prove the requested behavior or security.', style='yellow')
        with investigation_lock(repo):
            with activity(console, 'Snapshotting source and testing a requested change in isolation'):
                audit = find_risks(repo, db, timeout=timeout)
                db.save_audit(audit)
                if audit.status != 'completed' or path not in audit.files:
                    raise ValueError('A complete source snapshot is required. Run ghost scope and ghost find to inspect blocked scanning.')
                finding = LLMFinding(id='request-' + uuid4().hex, title='User-requested change', path=path, line=1,
                                     severity='UNDEFINED', explanation='Host-selected target for a user request; not a discovered security finding.',
                                     file_sha256=audit.files[path])
                result = solve_with_llm(repo, db, audit, finding, tests, provider, timeout=timeout, request_text=request)
            show_solution(result, console)
            if result.status != 'tested':
                raise typer.Exit(2)
            approved = apply or (interactive and typer.confirm('Apply this tested change? Review the diff; requested behavior and security are unverified.', default=False))
            if approved:
                apply_tested_proposal(repo, db, result)
                console.print('Patch applied. Review the requested behavior and rerun your checks.', style='green')
            else:
                console.print('Tested proposal saved; working tree unchanged. Use ghost solution to inspect it.')
    except typer.Exit:
        raise
    except (ValueError, RuntimeError) as exc:
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
