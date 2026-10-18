"""Own a disposable native FalkorDB process supplied by the optional Lite wheel."""
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time

from core.security.graph_triage import TriageError


def _binaries():
    try:
        package = distribution('falkordblite')
    except PackageNotFoundError:
        raise TriageError('Install embedded support: uv sync --locked --extra graph-embedded') from None
    server = Path(package.locate_file('redislite/bin/redis-server'))
    module = Path(package.locate_file('redislite/bin/falkordb.so'))
    if not server.is_file() or not module.is_file():
        raise TriageError('FalkorDBLite native binaries are missing. Reinstall the graph-embedded extra.')
    return server, module


@contextmanager
def embedded_falkor():
    """No TCP listener, daemon, persistent data, or connection to another server."""
    server, module = _binaries()
    # macOS has a short Unix socket path limit; its default temp path can be long.
    with TemporaryDirectory(prefix='ghost-falkor-', dir='/tmp') as directory:
        socket = str(Path(directory) / 'db.sock')
        command = [str(server), '--loadmodule', str(module), '--port', '0',
                   '--unixsocket', socket, '--unixsocketperm', '700',
                   '--dir', directory, '--save', '', '--appendonly', 'no',
                   '--daemonize', 'no', '--loglevel', 'warning']
        with (Path(directory) / 'server.log').open('wb') as log:
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                           start_new_session=True)
            except OSError:
                raise TriageError('Cannot launch embedded FalkorDB. Check the native wheel and executable permissions.') from None
            try:
                deadline = time.monotonic() + 10
                while not Path(socket).exists():
                    if process.poll() is not None:
                        raise TriageError('Embedded FalkorDB could not start. On macOS, run brew install libomp; '
                                          'use a supported FalkorDBLite wheel for your OS/Python.')
                    if time.monotonic() >= deadline:
                        raise TriageError('Embedded FalkorDB did not become ready within 10 seconds.')
                    time.sleep(0.05)
                yield socket
            finally:
                try:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=5)
                    except (subprocess.TimeoutExpired, KeyboardInterrupt):
                        process.kill()
                        process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    raise TriageError('Could not stop the embedded FalkorDB process. Check local processes before retrying.') from None
