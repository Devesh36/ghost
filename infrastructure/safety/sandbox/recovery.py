"""Bounded recovery observations; no cleanup, evidence updates or liveness inference."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from infrastructure.database.inspection import inspection_folder, readonly_history
from infrastructure.database.migrations import check_schema, check_version
from infrastructure.database.recovery_lock import recovery_guard
from infrastructure.database.storage import StorageError
from infrastructure.safety.sandbox.inventory import inventory

MAX_ROWS = 1000
MAX_PAYLOAD = 2_000_000
MAX_HISTORY_BYTES = 16_000_000
ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
STATUSES = {'running', 'completed', 'stopped', 'cancelled', 'failed'}


def _rows(db, table, *, where=''):
    # Table/where are fixed caller constants. Bound each payload before Python
    # receives it and bound the total history; partial reads never become clean.
    query = (f'SELECT substr(id, 1, 129), substr(session_id, 1, 129), length(CAST(payload AS BLOB)), '
             f'CASE WHEN length(CAST(payload AS BLOB)) <= ? THEN payload END '
             f'FROM {table} {where} LIMIT ?')
    total = 0
    for index, (key, session, size, payload) in enumerate(db.execute(query, (MAX_PAYLOAD, MAX_ROWS + 1))):
        if not isinstance(size, int):
            raise ValueError('Invalid saved payload')
        total += size
        if index == MAX_ROWS or size > MAX_PAYLOAD or total > MAX_HISTORY_BYTES:
            raise ValueError('History budget exceeded')
        if not isinstance(payload, str):
            raise ValueError('Invalid saved payload')
        item = json.loads(payload)
        if not isinstance(item, dict):
            raise ValueError('Invalid saved record')
        if item.get('session_id') != session or (table == 'investigations' and item.get('id') != key):
            raise ValueError('Saved identities differ')
        yield item


def _id(value):
    if not isinstance(value, str) or ID.fullmatch(value) is None:
        raise ValueError('Invalid saved identity')
    return value


def _history(repo):
    runs, references = {}, {}
    with readonly_history(repo) as db:
        if db is None:
            return runs, references, None
        version = check_version(db)
        check_schema(db, version=version)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'sessions', 'investigations', 'events'} <= tables:
            raise ValueError('History schema is incomplete')
        sessions = {}
        for index, (session, path) in enumerate(db.execute(
                'SELECT substr(id, 1, 129), substr(repository_path, 1, 8193) FROM sessions LIMIT ?', (MAX_ROWS + 1,))):
            if index == MAX_ROWS or path != str(repo):
                raise ValueError('Session scope is incomplete or different')
            sessions[_id(session)] = True
        for item in _rows(db, 'investigations'):
            run, session = _id(item.get('id')), _id(item.get('session_id'))
            status = item.get('status', 'running')
            if session not in sessions or run in runs or not isinstance(status, str) or status not in STATUSES:
                raise ValueError('Investigation provenance is inconsistent')
            finished = item.get('finished_at')
            if finished is not None and (not isinstance(finished, str) or not 1 <= len(finished) <= 80
                                         or any(ord(char) < 32 or ord(char) == 127 for char in finished)):
                raise ValueError('Invalid completion metadata')
            runs[run] = {'id': run, 'session_id': session, 'recorded_status': status,
                         'has_finish_time': finished is not None,
                         'needs_review': status == 'running' or finished is None}
        # Insertion order is the event order; timestamps do not determine whether
        # a snapshot reference was subsequently removed.
        for item in _rows(db, 'events', where="WHERE event_type='agent_action' ORDER BY id"):
            metadata = item.get('metadata', {})
            if not isinstance(metadata, dict):
                raise ValueError('Invalid action metadata')
            action = metadata.get('action')
            if not isinstance(action, str) or action not in {'snapshot_created', 'snapshot_removed'}:
                continue
            session = _id(item.get('session_id'))
            path = metadata.get('path')
            if session not in sessions or not isinstance(path, str) or len(path) > 8192:
                raise ValueError('Invalid snapshot provenance')
            candidate = Path(path)
            if not candidate.is_absolute() or candidate.parent != repo / '.ghost/worktrees' or '..' in candidate.parts:
                # Do not export outside paths recorded in old or hostile metadata.
                raise ValueError('Snapshot scope differs')
            run = metadata.get('investigation_id')
            if run is not None:
                run = _id(run)
                if run not in runs or runs[run]['session_id'] != session:
                    raise ValueError('Snapshot association differs')
            references[candidate.name] = {'investigation_id': run,
                                          'last_action': action, 'session_id': session}
    return runs, references, version


def _check_ownership(repo, entries):
    with inspection_folder(repo) as handles:
        if handles is None:
            return
        stack, folder = handles
        try:
            directory = os.open('worktrees', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
        except FileNotFoundError:
            return
        stack.callback(os.close, directory)
        if os.fstat(directory).st_uid != os.geteuid():
            raise StorageError('Worktree storage is not owned by this user')
        for entry in entries:
            try:
                info = os.stat(Path(entry['path']).name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                if entry['status'] != 'missing':
                    raise ValueError('Worktree inventory changed')
            else:
                if entry['status'] == 'missing':
                    raise ValueError('Worktree inventory changed')
                if info.st_uid != os.geteuid() or not stat.S_ISDIR(info.st_mode):
                    entry['status'] = 'unsafe'


def recovery_plan(repo: Path) -> dict:
    result = {'version': 1, 'repository': str(repo), 'complete': False,
              'lock': 'unknown', 'database_version': None, 'investigations': [],
              'worktrees': [], 'other_worktrees': 0, 'error': None, 'exit_code': 2,
              'cleanup_permitted': False}
    try:
        repo = repo.resolve(strict=True)
        result['repository'] = str(repo)
        with recovery_guard(repo) as lock:
            result['lock'] = lock
            if lock == 'held':
                result['error'] = 'An investigation holds the checkout lock. Stop it or wait, then rerun ghost recover.'
                return result
            sandboxes = inventory(repo)
            if not sandboxes['complete']:
                result['error'] = sandboxes['error']
                return result
            _check_ownership(repo, sandboxes['entries'])
            runs, references, version = _history(repo)
            result['database_version'] = version
            result['investigations'] = sorted(runs.values(), key=lambda item: item['id'])
            result['other_worktrees'] = sandboxes['other_worktrees']
            for entry in sandboxes['entries']:
                reference = references.get(Path(entry['path']).name)
                result['worktrees'].append({**entry, 'recorded_snapshot': reference,
                                             'recommendation': 'retain_and_review'})
            result['complete'] = True
            unsafe = any(item['status'] == 'unsafe' for item in result['worktrees'])
            needs_review = bool(result['worktrees']) or any(item['needs_review'] for item in runs.values())
            result['exit_code'] = 2 if unsafe else 1 if needs_review else 0
            return result
    except (OSError, StorageError, sqlite3.Error, ValueError, RecursionError):
        result['error'] = ('Recovery history could not be inspected completely and safely. Stop Ghost, back up .ghost '
                           'including SQLite sidecars, and inspect storage, database compatibility and history bounds. '
                           'No recovery action was performed.')
        return result
