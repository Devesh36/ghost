"""Opt-in owner/other-user requests, confined to a disposable checkout."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import sys

from core.security.models import AuthorizationContract, AuthorizationResult
from core.domain.types import PatchEdit
from infrastructure.repository.git import git
from infrastructure.repository.patches import apply_edits
from infrastructure.safety.guardrails.commands import run
from infrastructure.safety.sandbox.worktree import Worktree, source_signature
from infrastructure.security.bandit import source_bytes

MAX_CONTRACT_BYTES = 32_000
TEMPLATE = {
    'version': 1, 'runtime': 'python_asgi', 'app': 'app:app',
    'cases': [{'name': 'Private record', 'path': '/records/1',
               'protected_marker': 'alice-private-example',
               'owner_headers': {'x-test-user': 'alice'},
               'other_headers': {'x-test-user': 'bob'},
               'owner_status': 200, 'denied_statuses': [401, 403, 404]}],
}


def _private_bytes(repo: Path, name: str, limit: int) -> bytes:
    """Read only a named .ghost file; never follow a link or block on a FIFO."""
    root = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        folder = os.open('.ghost', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                        info.st_size > limit or info.st_mode & 0o077):
                    raise ValueError('Private Ghost input must be a bounded regular owner-only file with one link.')
                data = os.read(fd, limit + 1)
                if len(data) > limit:
                    raise ValueError('Private Ghost input exceeds its size limit.')
                return data
            finally:
                os.close(fd)
        finally:
            os.close(folder)
    finally:
        os.close(root)


def contract_bytes(repo: Path) -> bytes:
    return _private_bytes(repo, 'auth.json', MAX_CONTRACT_BYTES)


def init_contract(repo: Path) -> Path:
    directory = repo / '.ghost'
    folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open('auth.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        try:
            payload = (json.dumps(TEMPLATE, indent=2) + '\n').encode()
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(folder)
    return directory / 'auth.json'


def candidate_name(contract: AuthorizationContract) -> str:
    return 'candidate.py' if contract.runtime == 'python_asgi' else 'candidate.cjs'


def prepare_candidate(repo: Path) -> Path:
    contract = parse_contract(contract_bytes(repo))
    content = source_bytes(repo, _app_source(contract))
    directory = repo / '.ghost'
    folder = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        name = candidate_name(contract)
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(content)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(folder)
    return directory / name


def parse_contract(data: bytes) -> AuthorizationContract:
    try:
        contract = AuthorizationContract.model_validate_json(data)
        module = contract.app.split(':', 1)[0]
        if contract.runtime == 'python_asgi':
            if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module, flags=re.ASCII):
                raise ValueError('Invalid Python module')
        elif not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_/-]*\.(?:js|cjs)', module):
            raise ValueError('Invalid local CommonJS module')
        return contract
    except Exception:
        # Pydantic errors can include secret header values; never display them.
        raise ValueError('Invalid .ghost/auth.json. Each case needs a synthetic protected_marker; see ghost auth --init.') from None


def _app_source(contract: AuthorizationContract) -> str:
    module = contract.app.split(':', 1)[0]
    return module.replace('.', '/') + '.py' if contract.runtime == 'python_asgi' else module


def inspect_contract(repo: Path) -> tuple[AuthorizationContract, str]:
    """Validate the private contract and local source without importing project code."""
    try:
        contract = parse_contract(contract_bytes(repo))
    except FileNotFoundError:
        raise ValueError('No .ghost/auth.json. Run ghost auth --init, then set your test actors and protected marker.') from None
    except OSError:
        raise ValueError('Cannot safely read .ghost/auth.json. Check its owner-only permissions and file type.') from None
    source = _app_source(contract)
    try:
        source_bytes(repo, source)
    except (OSError, ValueError):
        raise ValueError('Configured app source is missing or unsafe. Check app in .ghost/auth.json; it must be a bounded local file, not a symlink.') from None
    return contract, source


def _run_snapshot(repo: Path, contract: AuthorizationContract, data: bytes, original_source: bytes,
                  initial_state: str, *, python: str | None, timeout: int,
                  candidate: bytes | None = None) -> list[AuthorizationResult]:
    source = _app_source(contract)
    with Worktree(repo) as sandbox:
        if source_signature(repo) != initial_state or source_bytes(sandbox, source) != original_source:
            raise ValueError('App changed while preparing authorization checks. Retry ghost find --auth.')
        if candidate is not None:
            try:
                edit = PatchEdit(path=source, old=original_source.decode('utf-8'), new=candidate.decode('utf-8'))
            except UnicodeDecodeError:
                raise ValueError('Candidate and app must be UTF-8 source files.') from None
            apply_edits(sandbox, [edit])
            if source_bytes(sandbox, source) != candidate:
                raise ValueError('Candidate bytes were not installed as expected in the worktree.')
        stage = sandbox / '.ghost'
        stage.mkdir(mode=0o700, exist_ok=True)
        staged = stage / 'auth-contract.json'
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(data)
        finally:
            os.close(fd)
        if contract.runtime == 'python_asgi':
            interpreter = Path(python).expanduser() if python else Path(sys.executable)
            if not interpreter.is_absolute():
                interpreter = repo / interpreter
            if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
                raise ValueError('Python interpreter is unavailable. Use --auth-python PATH to the project environment.')
            worker = Path(__file__).with_name('auth_worker.py')
            argv = [str(interpreter), '-I', str(worker), str(staged)]
        else:
            executable = shutil.which('node')
            if not executable:
                raise ValueError('Node.js is needed for the configured JS authorization handler.')
            worker = Path(__file__).with_name('auth_worker.cjs')
            argv = [executable, '--max-old-space-size=128', str(worker), str(staged)]
        outcome = run(shlex.join(argv), sandbox, timeout=timeout, output_limit=16_000, agent=True)
        if not outcome.sandboxed or outcome.timed_out or outcome.output_truncated or outcome.exit_code != 0:
            raise ValueError('Authorization app did not finish safely. Check imports, fixtures and --auth-python; no result was inferred.')
        report = json.loads(outcome.stdout)
        values = report.get('results') if isinstance(report, dict) else None
        if not isinstance(values, list) or len(values) != len(contract.cases):
            raise ValueError('Authorization worker did not account for every case.')
        results = []
        for case, pair in zip(contract.cases, values, strict=True):
            if not isinstance(pair, dict) or set(pair) != {'owner_status', 'other_status',
                                                           'owner_marker_seen', 'other_marker_seen'}:
                raise ValueError('Authorization worker returned an invalid result.')
            owner, other = pair['owner_status'], pair['other_status']
            if not all(type(code) is int and 100 <= code <= 599 for code in (owner, other)):
                raise ValueError('Authorization worker returned invalid HTTP statuses.')
            owner_marker, other_marker = pair['owner_marker_seen'], pair['other_marker_seen']
            if type(owner_marker) is not bool or type(other_marker) is not bool:
                raise ValueError('Authorization worker returned invalid content evidence.')
            verdict = ('inconclusive' if owner != case.owner_status or not owner_marker else
                       'confirmed' if other_marker else
                       'denied' if other in case.denied_statuses else 'inconclusive')
            results.append(AuthorizationResult(name=case.name, path=case.path, runtime=contract.runtime,
                                               owner_status=owner, other_status=other,
                                               protected_content_seen_by_owner=owner_marker,
                                               protected_content_seen_by_other=other_marker,
                                               verdict=verdict))
        return results


def _check(repo: Path, *, python: str | None, timeout: int, candidate: bool):
    try:
        if os.getenv('GHOST_DISABLE_OS_SANDBOX') == '1':
            raise ValueError('Authorization checks require OS confinement. Unset GHOST_DISABLE_OS_SANDBOX.')
        try:
            data = contract_bytes(repo)
        except FileNotFoundError:
            raise ValueError('No .ghost/auth.json. Run ghost auth --init, then configure your local test actors.') from None
        contract = parse_contract(data)
        identity = hashlib.sha256(data).digest()
        source = _app_source(contract)
        original_source = source_bytes(repo, source)
        candidate_data = None
        if candidate:
            name = candidate_name(contract)
            try:
                candidate_data = _private_bytes(repo, name, 512_000)
            except FileNotFoundError:
                raise ValueError(f'No .ghost/{name}. Run ghost auth --prepare-candidate, then edit it.') from None
        starting_head = git(repo, 'rev-parse', 'HEAD').strip()
        starting_state = source_signature(repo)
        baseline = _run_snapshot(repo, contract, data, original_source, starting_state,
                                 python=python, timeout=timeout)
        after = []
        if candidate and all(item.verdict != 'inconclusive' for item in baseline):
            after = _run_snapshot(repo, contract, data, original_source, starting_state,
                                  python=python, timeout=timeout, candidate=candidate_data)
        if (hashlib.sha256(contract_bytes(repo)).digest() != identity or
                (candidate and _private_bytes(repo, candidate_name(contract), 512_000) != candidate_data) or
                source_signature(repo) != starting_state or git(repo, 'rev-parse', 'HEAD').strip() != starting_head):
            raise ValueError('App, candidate or authorization contract changed during the check. Retry ghost find --auth.')
        complete = all(item.verdict != 'inconclusive' for item in [*baseline, *after])
        if candidate and not after:
            complete = False
        digest = hashlib.sha256(candidate_data).hexdigest() if candidate_data is not None and after else None
        return baseline, after, complete, '', digest
    except ValueError as exc:
        return [], [], False, str(exc), None
    except Exception:
        return [], [], False, 'Authorization check stopped safely. Run ghost doctor and inspect git worktree list if cleanup failed.', None


def check_authorization(repo: Path, *, python: str | None = None, timeout: int = 30) -> tuple[list[AuthorizationResult], bool, str]:
    baseline, _, complete, note, _ = _check(repo, python=python, timeout=timeout, candidate=False)
    return baseline, complete, note


def check_candidate(repo: Path, *, python: str | None = None, timeout: int = 30) -> tuple[list[AuthorizationResult], list[AuthorizationResult], bool, str, str | None]:
    return _check(repo, python=python, timeout=timeout, candidate=True)
