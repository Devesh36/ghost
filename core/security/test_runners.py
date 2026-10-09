"""Bounded repair runners; command selection belongs to the developer, never the model."""
from dataclasses import dataclass
from enum import StrEnum
import hashlib
from pathlib import Path
from typing import Literal
import re
import shlex
import shutil
import sys

from pydantic import BaseModel, Field
from infrastructure.safety.guardrails.commands import CommandResult, parse


class TestRunnerError(ValueError):
    """Host-written diagnostics only: no raw command, source or provider output."""
    __test__ = False


class RunnerKind(StrEnum):
    PYTEST = 'python_pytest'
    UNITTEST = 'python_unittest'
    NODE = 'node_test'


class TestEvidence(BaseModel):
    __test__ = False
    runner: RunnerKind
    complete: bool = False
    passed: int = 0
    failed: int | None = None
    skipped: int | None = None
    cancelled: int | None = None
    todo: int | None = None
    coverage_basis: Literal['count', 'flat_tap_identities'] = 'count'
    case_ids: list[str] = Field(default_factory=list)
    issue: str | None = None


def python_passed_tests(output: str, kind: RunnerKind | None = None) -> int:
    """Preserve the existing Python summary and skip/error policy."""
    unittest = re.search(r'(?m)^Ran (\d+) tests? in .+\n\s*\nOK(?:\s|$)', output)
    pytest = re.search(r'(\d+) passed(?:[,\s]|$)', output)
    if re.search(r'\b(skipped|xfailed|xpassed|deselected|failed|errors?)\b', output, re.I):
        return 0
    match = unittest if kind == RunnerKind.UNITTEST else pytest if kind == RunnerKind.PYTEST else unittest or pytest
    return int(match.group(1)) if match else 0


@dataclass(frozen=True)
class TestRunner:
    __test__ = False
    kind: RunnerKind
    argv: tuple[str, ...]
    selected_command: str
    files: tuple[str, ...] = ()

    @property
    def command(self) -> str:
        return shlex.join(self.argv)

    @property
    def version_command(self) -> str | None:
        return shlex.join([self.argv[0], '--version']) if self.kind == RunnerKind.NODE else None

    def node_version(self, outcome: CommandResult) -> str:
        match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)\s*', outcome.stdout)
        if (outcome.argv != [self.argv[0], '--version'] or outcome.exit_code or outcome.timed_out
                or outcome.output_truncated or not outcome.sandboxed or not match):
            raise TestRunnerError('Could not establish the installed Node version in confinement. No repair was prepared.')
        if tuple(int(value) for value in match.groups()) < (20, 10, 0):
            raise TestRunnerError('Node repair tests require Node 20.10 or newer. Install a supported runtime explicitly; Ghost will not install it.')
        return match.group(0).strip()

    def evidence(self, outcome: CommandResult) -> TestEvidence:
        if self.kind == RunnerKind.NODE:
            evidence = self._tap(outcome.stdout)
        else:
            count = python_passed_tests(outcome.stdout + '\n' + outcome.stderr, self.kind)
            evidence = TestEvidence(runner=self.kind, complete=count > 0, passed=count,
                                    **({'failed': 0, 'skipped': 0, 'cancelled': 0, 'todo': 0} if count else {}),
                                    issue=None if count else 'Python tests need the selected runner\'s passing summary, at least one test, and no skips, deselections or failures.')
        if outcome.argv != list(self.argv):
            evidence.issue = 'Executed command did not match the user-selected test runner.'
            evidence.complete = False
        elif outcome.timed_out:
            evidence.issue = 'Test command timed out; its evidence is incomplete.'
            evidence.complete = False
        elif outcome.output_truncated:
            evidence.issue = 'Test output was truncated; its evidence is incomplete.'
            evidence.complete = False
        elif not outcome.sandboxed:
            evidence.issue = 'Test command did not establish OS confinement.'
            evidence.complete = False
        elif outcome.exit_code:
            evidence.issue = 'Test command failed; no applicable repair is available.'
        return evidence

    def _tap(self, output: str) -> TestEvidence:
        evidence = TestEvidence(runner=self.kind, coverage_basis='flat_tap_identities')
        summary, names, pending, plan = {}, [], None, None
        outcomes, directives, finished = [], [], False
        try:
            lines = output.splitlines()
            if not lines or lines[0] != 'TAP version 13':
                raise TestRunnerError('Node tests require a complete TAP 13 report from the built-in runner.')
            for line in lines[1:]:
                if finished and line.strip():
                    raise TestRunnerError('Unexpected output followed the final Node TAP summary.')
                if re.match(r'\s+(?:# Subtest:|(?:not )?ok\s|\d+\.\.\d+)', line):
                    raise TestRunnerError('Nested Node tests and suites are not supported yet; use flat, uniquely named tests.')
                if line.startswith('# Subtest: '):
                    if pending is not None or plan is not None:
                        raise TestRunnerError('Node TAP case ordering was incomplete or malformed.')
                    pending = line.removeprefix('# Subtest: ')
                    if not pending or len(pending) > 300 or pending in names:
                        raise TestRunnerError('Node test names must be bounded and unique.')
                elif match := re.fullmatch(r'(ok|not ok) ([1-9][0-9]*) - (.+)', line):
                    raw_name = match.group(3)
                    directive = re.search(r'\s+#\s*(?:SKIP|TODO)\b', raw_name, re.I)
                    name = raw_name[:directive.start()] if directive else raw_name
                    if pending != name or int(match.group(2)) != len(names) + 1 or len(names) >= 1000:
                        raise TestRunnerError('Node TAP case identities or numbering were incomplete or malformed.')
                    if Path(name).name == Path(self.files[0]).name:
                        raise TestRunnerError('Node reported a file-level result without registered tests; zero-test scripts cannot qualify a repair.')
                    names.append(name)
                    outcomes.append(match.group(1))
                    directives.append(bool(directive))
                    pending = None
                elif match := re.fullmatch(r'1\.\.(\d+)', line):
                    if plan is not None or pending is not None:
                        raise TestRunnerError('Node TAP needs exactly one complete test plan.')
                    plan = int(match.group(1))
                elif match := re.fullmatch(r'# (tests|suites|pass|fail|cancelled|skipped|todo) (\d+)', line):
                    if match.group(1) in summary or plan is None:
                        raise TestRunnerError('Node TAP summary was duplicated or out of order.')
                    summary[match.group(1)] = int(match.group(2))
                elif re.fullmatch(r'# duration_ms [0-9]+(?:\.[0-9]+)?', line):
                    if set(summary) != {'tests', 'suites', 'pass', 'fail', 'cancelled', 'skipped', 'todo'}:
                        raise TestRunnerError('Node TAP ended without a complete summary.')
                    finished = True
                elif re.match(r'(?:TAP version|Bail out!|(?:not )?ok\b|\d+\.\.|# (?:tests|suites|pass|fail|cancelled|skipped|todo)\b)', line):
                    raise TestRunnerError('Node TAP contained an unsupported or incomplete result.')
                elif line and not line.startswith(('#', ' ')):
                    raise TestRunnerError('Node TAP contained unrecognized result output.')
            required = {'tests', 'suites', 'pass', 'fail', 'cancelled', 'skipped', 'todo'}
            if not finished or set(summary) != required or plan != len(names) or summary['tests'] != len(names) or pending is not None:
                raise TestRunnerError('Node TAP plan, case identities and summary did not account for all tests.')
            if summary['suites']:
                raise TestRunnerError('Nested Node tests and suites are not supported yet; use flat, uniquely named tests.')
            if not names:
                raise TestRunnerError('Node collected zero tests. Select a JavaScript file registering node:test cases.')
            if sum(summary[key] for key in ('pass', 'fail', 'cancelled', 'skipped', 'todo')) != summary['tests']:
                raise TestRunnerError('Node TAP summary counters did not account for the complete case inventory.')
            evidence.complete = True
            evidence.case_ids = [hashlib.sha256((self.files[0] + '\0' + name).encode()).hexdigest() for name in names]
            if summary['fail'] or summary['cancelled'] or summary['skipped'] or summary['todo'] or any(directives) or 'not ok' in outcomes:
                raise TestRunnerError('Node tests failed, were cancelled, skipped or marked TODO; repair application is blocked.')
            if summary['pass'] != len(names):
                raise TestRunnerError('Node passing count did not match the complete case inventory.')
        except TestRunnerError as exc:
            evidence.issue = str(exc)
        except ValueError:
            evidence.issue = 'Node TAP contained an invalid numeric result.'
        evidence.passed = summary.get('pass', 0)
        evidence.failed = summary.get('fail')
        evidence.skipped = summary.get('skipped')
        evidence.cancelled = summary.get('cancelled')
        evidence.todo = summary.get('todo')
        return evidence

    def compare(self, before: TestEvidence, after: TestEvidence) -> None:
        if before.issue or after.issue or not before.complete or not after.complete or before.runner != self.kind or after.runner != self.kind:
            raise TestRunnerError('Baseline and patched evidence must be complete and use the same selected runner.')
        if before.passed != after.passed:
            raise TestRunnerError('Patched test count did not match the passing baseline; coverage changes block application.')
        if self.kind == RunnerKind.NODE and before.case_ids != after.case_ids:
            raise TestRunnerError('Node test identities changed after the patch; missing, renamed or reordered cases block application.')


def python_runner(command: str) -> TestRunner:
    argv = parse(command, agent=True)
    if argv[0] == 'pytest':
        tail = ['-m', 'pytest', *argv[1:]]
    elif Path(argv[0]).name in {'python', 'python3', 'python3.12', Path(sys.executable).name} and argv[1:3] in (['-m', 'pytest'], ['-m', 'unittest']):
        tail = argv[1:]
    else:
        raise TestRunnerError('Python repairs require --tests "python -m pytest ..." or "python -m unittest discover -v".')
    return TestRunner(RunnerKind.PYTEST if tail[1] == 'pytest' else RunnerKind.UNITTEST,
                      (sys.executable, *tail), command)


def select_runner(command: str, target: str, repo: Path) -> TestRunner:
    if not isinstance(command, str) or not command.strip() or len(command) > 4096:
        raise TestRunnerError('Select an existing test command explicitly with --tests; Ghost does not guess or install a runner.')
    suffix = Path(target).suffix.lower()
    if suffix == '.py':
        return python_runner(command)
    if suffix not in {'.js', '.mjs', '.cjs'}:
        raise TestRunnerError('TypeScript and JSX repair verification is not implemented. Only Python and plain JavaScript targets are supported.')
    try:
        argv = parse(command, agent=True)
    except ValueError:
        raise TestRunnerError('Malformed test command. Use a direct node --test command without shell operators or inline code.') from None
    if argv[:2] != ['node', '--test']:
        raise TestRunnerError('JavaScript repairs require Node\'s built-in runner: --tests "node --test test/parser.test.cjs". Python, npm, Jest and Vitest cannot qualify this target.')
    flags, files = set(), []
    for argument in argv[2:]:
        if argument in {'--test-reporter=tap', '--test-concurrency=1'} and not files and argument not in flags:
            flags.add(argument)
        elif not argument.startswith('-'):
            files.append(argument)
        else:
            raise TestRunnerError('Unsupported Node test option. Only --test, --test-reporter=tap and --test-concurrency=1 are supported; no loaders, filters or preloads.')
    if len(files) != 1:
        raise TestRunnerError('Select exactly one JavaScript test file. Test discovery, globs and multi-file commands are not supported yet.')
    path = Path(files[0])
    if (path.is_absolute() or any(part.casefold() in {'..', '.git', '.ghost'} for part in path.parts)
            or any(char in files[0] for char in '*?[]{}\\') or path.suffix.lower() not in {'.js', '.mjs', '.cjs'}):
        raise TestRunnerError('Select one repository-relative .js, .mjs or .cjs test file without traversal, TypeScript or globs.')
    if str(path) == str(Path(target)):
        raise TestRunnerError('The selected test file cannot be a repair target; test-file edits are blocked.')
    from infrastructure.security.bandit import source_bytes
    from infrastructure.security.review import inventory
    try:
        if str(path) not in inventory(repo):
            raise ValueError
        source_bytes(repo, str(path))
    except (OSError, ValueError):
        raise TestRunnerError('Selected Node test file must be Git-visible, readable and regular, without symlinks. No packages will be installed.') from None
    binary = shutil.which('node')
    if not binary:
        raise TestRunnerError('Node was not found on PATH. Install Node 20.10+ explicitly, then retry; Ghost will not install packages.')
    return TestRunner(RunnerKind.NODE, (str(Path(binary).resolve()), '--test', '--test-reporter=tap',
                                     '--test-concurrency=1', str(path)), command, (str(path),))
