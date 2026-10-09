import asyncio
import io
from pathlib import Path

import pytest
from rich.console import Console
from surfaces.shared.terminal.investigation import TerminalReporter

from core.agent_harness import orchestrator
from infrastructure.database.repository import Database
from core.domain.types import Session


def session(repo):
    db = Database(repo)
    item = Session(repository_path=str(repo), starting_commit='abc123', branch='main')
    db.start(item)
    return db, item


def test_second_investigation_is_rejected_before_persistence(tmp_path, monkeypatch):
    db, item = session(tmp_path)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0
        async def held_snapshot(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                await release.wait()
        monkeypatch.setattr(orchestrator, '_snapshot_debug', held_snapshot)
        first = asyncio.create_task(orchestrator.debug(tmp_path, db, item.id, None, TerminalReporter(Console(file=io.StringIO()))))
        await entered.wait()
        try:
            with pytest.raises(RuntimeError, match='in progress'):
                await orchestrator.debug(tmp_path, db, item.id, None, TerminalReporter(Console(file=io.StringIO())))
            assert len(db.investigations(item.id)) == 1
            assert calls == 1
        finally:
            release.set()
            await first
    asyncio.run(scenario())


def test_exception_releases_lock_and_preserves_lock_inode(tmp_path):
    from infrastructure.database.locking import investigation_lock, InvestigationBusy
    with pytest.raises(ValueError, match='test failure'):
        with investigation_lock(tmp_path):
            path = tmp_path / '.ghost/investigation.lock'
            inode = path.stat().st_ino
            with pytest.raises(InvestigationBusy):
                with investigation_lock(tmp_path):
                    pass
            raise ValueError('test failure')
    with investigation_lock(tmp_path):
        assert path.stat().st_ino == inode
    assert path.exists()  # Do not unlink a lock file: competing opens must use one inode.


def test_different_checkouts_can_investigate_independently(tmp_path):
    from infrastructure.database.locking import investigation_lock
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    with investigation_lock(first), investigation_lock(second):
        pass


@pytest.mark.parametrize('kind', ['file_symlink', 'directory_symlink', 'hardlink', 'fifo'])
def test_unsafe_lock_paths_are_rejected(tmp_path, kind):
    import os
    from infrastructure.database.locking import investigation_lock
    outside = tmp_path / 'outside'
    outside.mkdir()
    original = outside / 'untouched'
    original.write_text('unchanged')
    repo = tmp_path / 'repo'
    repo.mkdir()
    ghost = repo / '.ghost'
    if kind == 'directory_symlink':
        ghost.symlink_to(outside, target_is_directory=True)
    else:
        ghost.mkdir()
        lock = ghost / 'investigation.lock'
        if kind == 'file_symlink':
            lock.symlink_to(original)
        elif kind == 'hardlink':
            lock.hardlink_to(original)
        else:
            os.mkfifo(lock)
    with pytest.raises((OSError, ValueError)):
        with investigation_lock(repo):
            pytest.fail('Unsafe lock was acquired')
    assert original.read_text() == 'unchanged'
    assert not (outside / 'investigation.lock').exists()


def test_cross_process_exclusion_and_crash_release(tmp_path):
    import select
    import subprocess
    import sys
    from infrastructure.database.locking import investigation_lock, InvestigationBusy
    script = ('import sys\nfrom pathlib import Path\nfrom infrastructure.database.locking import investigation_lock\n'
              'with investigation_lock(Path(sys.argv[1])):\n'
              ' print("locked", flush=True)\n'
              ' sys.stdin.read()\n')
    process = subprocess.Popen([sys.executable, '-c', script, str(tmp_path)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 5)[0], 'Child did not acquire the lock'
        assert process.stdout.readline().strip() == 'locked'
        with pytest.raises(InvestigationBusy):
            with investigation_lock(tmp_path):
                pass
        process.kill()
        process.wait(timeout=5)
        with investigation_lock(tmp_path):
            pass  # A leftover lock file after a crash must never require manual deletion.
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_cancellation_holds_lock_until_worker_cleanup(tmp_path, monkeypatch):
    import threading
    import time
    from infrastructure.database.locking import investigation_lock, InvestigationBusy
    db, item = session(tmp_path)
    entered, cleaning, finish_cleanup = threading.Event(), threading.Event(), threading.Event()
    async def held_snapshot(repo, db, session_id, provider, console, result, harness, **kwargs):
        def worker():
            entered.set()
            try:
                while True:
                    harness.check()
                    time.sleep(0.005)
            finally:
                cleaning.set()
                assert finish_cleanup.wait(timeout=5)
        await harness.worker(worker)
    monkeypatch.setattr(orchestrator, '_snapshot_debug', held_snapshot)
    async def scenario():
        task = asyncio.create_task(orchestrator.debug(tmp_path, db, item.id, None, TerminalReporter(Console(file=io.StringIO()))))
        async def until(event):
            async with asyncio.timeout(5):
                while not event.is_set():
                    await asyncio.sleep(0.005)
        try:
            await until(entered)
            task.cancel()
            await until(cleaning)
            with pytest.raises(InvestigationBusy):
                with investigation_lock(tmp_path):
                    pass
        finally:
            finish_cleanup.set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        with investigation_lock(tmp_path):
            assert db.latest_investigation(item.id).status == 'cancelled'
    asyncio.run(scenario())


def test_final_persistence_failure_releases_lock(tmp_path, monkeypatch):
    from infrastructure.database.locking import investigation_lock
    db, item = session(tmp_path)
    async def snapshot(*args, **kwargs):
        pass
    monkeypatch.setattr(orchestrator, '_snapshot_debug', snapshot)
    original = db.save_investigation
    def save(result):
        if result.finished_at:
            raise OSError('storage failed')
        original(result)
    monkeypatch.setattr(db, 'save_investigation', save)
    with pytest.raises(OSError, match='storage failed'):
        asyncio.run(orchestrator.debug(tmp_path, db, item.id, None, TerminalReporter(Console(file=io.StringIO()))))
    with investigation_lock(tmp_path):
        pass


def test_cli_and_repl_report_busy_without_new_investigation(tmp_path, monkeypatch):
    from typer.main import get_command
    from typer.testing import CliRunner
    import surfaces.cli.app
    from infrastructure.database.locking import investigation_lock
    from surfaces.interactive_shell.shell import GhostREPL
    db, item = session(tmp_path)
    monkeypatch.setattr(surfaces.cli.app, 'context', lambda: (tmp_path, db))
    output = io.StringIO()
    with investigation_lock(tmp_path):
        response = CliRunner().invoke(surfaces.cli.app.app, ['debug'])
        assert response.exit_code == 2 and 'in progress' in response.output
        assert 'ghost investigations' in ' '.join(response.output.split())
        console = Console(file=output)
        monkeypatch.setattr(surfaces.cli.app, 'console', console)
        repl = GhostREPL(tmp_path, db, item, get_command(surfaces.cli.app.app), console)
        assert repl.dispatch('debug')
        assert repl.dispatch('status')
    assert db.investigations(item.id) == []
    assert 'in progress' in output.getvalue()
