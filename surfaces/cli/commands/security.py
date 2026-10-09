"""Security-first command flow, shared by CLI and REPL."""
import difflib
import shlex
import typer
from rich.panel import Panel
from infrastructure.database.locking import investigation_lock
from infrastructure.security.review import find_risks
from core.security.solver import solve, apply_solution
from surfaces.shared.terminal.brand import activity
from surfaces.shared.terminal.console import literal
from surfaces.shared.terminal.brief import show_brief
from surfaces.shared.terminal.runtime import interactive_console


def scan_review(repo, db, console, *, timeout, llm=False, json_output=False, **options):
    # Resolve a requested provider before doing expensive work; offline is default.
    provider = None
    if llm:
        from bootstrap.providers import load_provider
        provider = load_provider(repo)
        if not json_output:
            console.print('LLM assist enabled: eligible source will be sent to your configured provider.', style='yellow')
    if json_output:
        result = find_risks(repo, db, timeout=timeout, **options)
    else:
        with activity(console, 'Checking source snapshots and local contracts' if options.get('auth') else 'Checking Python and JavaScript/TypeScript source snapshots'):
            result = find_risks(repo, db, timeout=timeout, **options)
    if provider is not None:
        from core.security.assistance import assist_find
        result.llm_review = assist_find(repo, result, provider)
    db.save_audit(result)
    return result


def run_find(repo, db, console, *, timeout, json_output, auth=False, auth_python=None, candidate=False, llm=False):
    try:
        result = scan_review(repo, db, console, timeout=timeout, json_output=json_output, auth=auth, auth_python=auth_python, candidate=candidate, llm=llm)
    except ValueError as exc:
        if json_output:
            typer.echo('LLM connection unavailable. Configure ghost connect before using --llm.', err=True)
        else:
            console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from None
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
    else:
        show_brief(result, console, fresh=True)
    raise typer.Exit(result.exit_code)


def show_solution(result, console):
    kind = 'LLM PROPOSAL' if result.method == 'llm' else 'SECURITY REPAIR'
    console.print(Panel(literal(f'{kind} / {result.status.upper()}\nSolution: {result.id}\nFinding: {result.finding_id}', multiline=True), border_style='cyan'))
    if result.test_runner:
        console.print(literal(f'Runner: {result.test_runner} / version {result.test_runner_version or "not established"}'))
    if result.selected_test_command is not None:
        console.print(literal('Selected tests: ' + result.selected_test_command))
    if result.test_command:
        console.print(literal('Executed tests: ' + shlex.join(result.test_command)))
    for check in result.checks:
        label = check['label']
        detail = f"exit {check['exit_code']} / {check['duration']:.2f}s" if 'exit_code' in check else check['status']
        evidence = check.get('test_evidence')
        if 'passed_tests' in check and (not evidence or evidence['complete']):
            detail += f" / {check['passed_tests']} tests passed"
        console.print(literal(f'{label}: {detail}'))
        if evidence:
            console.print(literal(f"  {evidence['runner']} / evidence {'complete' if evidence['complete'] else 'incomplete'}"))
            if evidence['complete']:
                console.print(literal(f"  Failed {evidence['failed']} / skipped {evidence['skipped']}"
                                     f" / cancelled {evidence['cancelled']} / TODO {evidence['todo']}"))
            else:
                console.print('  Complete passing test inventory was not established.', style='yellow')
            if evidence['coverage_basis'] == 'flat_tap_identities':
                console.print(literal(f"  {len(evidence['case_ids'])} flat case identities recorded; assertions and reachability are not measured."))
            else:
                console.print('  Passing counts only; individual cases and assertion coverage are not measured.', style='dim')
            if evidence.get('issue'):
                console.print(literal('  Blocked: ' + evidence['issue'], style='yellow'))
        if check.get('snapshot_unchanged') is False:
            console.print('  Reviewed project files changed; repair not verified.', style='yellow')
        if 'target_rule_absent' in check:
            absent = check['target_rule_absent']
            console.print('  No scanner rule independently confirms this LLM advisory.' if absent is None else
                          '  Target scanner rule absent: ' + ('yes' if absent else 'no'), style='dim')
        if 'facts' in check:
            facts = check['facts']
            action = 'rejected' if facts['function_call_rejected'] else 'executed'
            console.print(f"  Function call {action}; {facts['literal_cases']} literal cases preserved: {facts['literals_preserved']}", style='dim')
    for edit in result.patch:
        patch = ''.join(difflib.unified_diff(edit.old.splitlines(True), edit.new.splitlines(True),
                                           fromfile=edit.path, tofile=edit.path))
        console.print(literal(patch, multiline=True))
    for note in result.notes:
        console.print(literal(note, style='yellow'))


def run_solve(repo, db, console, selector, *, tests, timeout, apply, llm=False):
    audit = db.latest_audit()
    items = audit.findings + (audit.llm_review.findings if audit.llm_review else []) if audit else []
    matches = ([f for f in items if f.id == selector] or [f for f in items if f.id.startswith(selector)]) if selector else []
    if len(matches) != 1:
        console.print('Finding missing or ambiguous. Run ghost find, then ghost findings --json.', style='yellow')
        raise typer.Exit(2)
    try:
        with investigation_lock(repo):
            if llm:
                from bootstrap.providers import load_provider
                from core.security.llm_solver import solve_with_llm
                provider = load_provider(repo)
                console.print('LLM assist sends the selected source file to your configured provider. Patches are tested proposals, not verified security fixes.', style='yellow')
                with activity(console, 'Testing an LLM repair proposal in an isolated worktree'):
                    result = solve_with_llm(repo, db, audit, matches[0], tests, provider, timeout=timeout)
            else:
                if not hasattr(matches[0], 'rule'):
                    console.print('LLM advisories require ghost solve <id> --llm --tests COMMAND. Select Python pytest/unittest or, for plain JavaScript, node --test with one JS test file. TypeScript is unsupported.', style='yellow')
                    raise typer.Exit(2)
                with activity(console, 'Reproducing and testing a Python repair in an isolated worktree'):
                    result = solve(repo, db, audit, matches[0], tests, timeout=timeout)
            show_solution(result, console)
            if result.status not in {'verified', 'tested'}:
                raise typer.Exit(2)
            prompt = 'Apply this tested LLM proposal? Security behavior is unverified.' if result.status == 'tested' else 'Apply this verified patch to the working tree?'
            approved = apply or (interactive_console(console) and typer.confirm(prompt, default=False))
            if approved:
                if result.status == 'tested':
                    from core.security.llm_solver import apply_tested_proposal
                    apply_tested_proposal(repo, db, result)
                else:
                    apply_solution(repo, db, result)
                console.print('Patch applied. Rerun ghost find before shipping.', style='green')
            else:
                console.print(('Tested proposal saved' if result.status == 'tested' else 'Verified patch saved') + '; working tree unchanged. Use ghost solution to inspect it.')
    except typer.Exit:
        raise
    except (ValueError, RuntimeError) as exc:
        console.print(literal(str(exc), style='yellow'))
        raise typer.Exit(2) from exc
