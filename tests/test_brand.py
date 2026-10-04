import io
import os
import select
import subprocess
import sys
import time
import pytest

from rich.console import Console

from core.domain.types import Session
from surfaces.shared.terminal.brand import activity, motion_enabled, prompt, welcome


@pytest.mark.parametrize('width', [24, 40, 80])
def test_watch_and_history_escape_untrusted_paths_commands_and_branch(tmp_path, monkeypatch, width):
    from core.domain.types import Event, EventType
    import surfaces.shared.terminal.console as ui

    monkeypatch.setenv('NO_COLOR', '1')
    output = io.StringIO()
    target = Console(file=output, width=width, no_color=True)
    monkeypatch.setattr(ui, 'console', target)
    branch = '[red]branch\x1b]52;c;payload\x07\u202e'
    path = 'bad[bold]\x1b[2J\u202e.py'
    command = 'pytest\x1b]8;;https://example.invalid\x07click\x1b]8;;\x07'
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch=branch)
    event = Event(session_id=session.id, event_type=EventType.FILE_CHANGED, file_path=path)
    ui.show_watch_start(tmp_path, session, target=target)
    ui.show_watch_event(event, target=target)
    ui.show_status(session, [event])
    ui.show_timeline([event, Event(session_id=session.id, event_type=EventType.COMMAND_STARTED,
                                   command=command)])
    shown = output.getvalue()
    assert 'Ghost is watching' in shown and '[red]branch' in shown
    assert 'bad[bold]' in shown and 'pytest' in shown
    packed = ''.join(shown.split())
    assert '\\u001b' in packed and '\\u202e' in packed
    assert '\x1b' not in shown and '\x07' not in shown and '\u202e' not in shown
    assert all(len(line) <= width for line in shown.splitlines())


def test_piped_welcome_never_animates_or_emits_terminal_controls(tmp_path, monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    def unexpected_sleep(_):
        raise AssertionError("Redirected output must never wait for animation")
    monkeypatch.setattr("surfaces.shared.terminal.brand.time.sleep", unexpected_sleep)
    output = io.StringIO()
    console = Console(file=output, width=80)
    session = Session(repository_path=str(tmp_path), starting_commit="abc123", branch="[red]branch")
    welcome(console, tmp_path, session)
    with activity(console, "Testing the actual command"):
        pass
    text = output.getvalue()
    assert "\x1b" not in text
    assert "[red]branch" in text  # Repository metadata is literal, never Rich markup.
    assert "run <command>" in text
    assert "Testing the actual command" in text


def test_motion_respects_terminal_and_accessibility_preferences(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("GHOST_NO_ANIMATION", raising=False)
    console = Console(file=io.StringIO(), force_terminal=True, no_color=False)
    assert motion_enabled(console)
    monkeypatch.setenv("GHOST_NO_ANIMATION", "1")
    assert not motion_enabled(console)
    monkeypatch.delenv("GHOST_NO_ANIMATION")
    monkeypatch.setenv("NO_COLOR", "")
    assert not motion_enabled(console)


@pytest.mark.parametrize('width', [24, 40, 96])
def test_formatted_replies_keep_controls_inert_and_commands_readable(monkeypatch, width):
    from surfaces.shared.terminal.assistant import show_answer
    from surfaces.shared.terminal.runtime import TERMINAL_THEME

    monkeypatch.setenv('TERM', 'xterm-256color')
    output = io.StringIO()
    console = Console(file=output, width=width, height=200, no_color=True, theme=TERMINAL_THEME)
    reply = ('## Start here\n\nReview **scope**, then run:\n\n'
             '```bash\nghost findings --severity HIGH --limit 10\n```\n\n'
             '[Documentation](https://example.invalid/review)\n\n'
             'Untrusted output: \x1b]52;c;payload\x07\u202e\n')
    show_answer(console, reply)
    shown = output.getvalue()
    packed = ''.join(shown.split()).replace('│', '')
    assert 'ghostfindings--severityHIGH--limit10' in packed
    assert 'https://example.invalid/review' in packed
    assert '\\u001b' in packed and '\\u0007' in packed and '\\u202e' in packed
    assert '\x1b' not in shown and '\x07' not in shown and '\u202e' not in shown
    assert '**scope**' not in shown and '```' not in shown
    assert all(len(line) <= width for line in shown.splitlines())
    assert 'Chat does not run it.' in ' '.join(shown.split())


def test_formatted_reply_never_emits_clickable_terminal_links(monkeypatch):
    from surfaces.shared.terminal.assistant import show_answer

    monkeypatch.setenv('TERM', 'xterm-256color')
    output = io.StringIO()
    console = Console(file=output, force_terminal=True, width=96, height=100)
    show_answer(console, '[Click here](https://example.invalid)')
    assert '\x1b]8;' not in output.getvalue()


def test_basic_terminal_uses_readable_ascii(tmp_path, monkeypatch):
    monkeypatch.setenv("TERM", "dumb")
    output = io.StringIO()
    console = Console(file=output, width=32)
    session = Session(repository_path=str(tmp_path), starting_commit="abc123", branch="main")
    welcome(console, tmp_path, session)
    text = output.getvalue()
    text.encode("ascii")
    assert "G H O S T" in text
    assert prompt(console, watching=True) == "  ghost [watching] > "


@pytest.mark.parametrize('width', [24, 40, 80])
def test_welcome_and_help_are_compact_at_terminal_width(tmp_path, monkeypatch, width):
    from infrastructure.database.repository import Database
    from surfaces.entrypoint import app
    from surfaces.interactive_shell.shell import GhostREPL
    from typer.main import get_command

    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch='feature/auth')
    welcome(console, tmp_path, session)
    welcome_lines = output.getvalue().splitlines()
    assert len(welcome_lines) <= (20 if width < 52 else 23)
    assert 'find' in output.getvalue() and 'auth' in output.getvalue()

    shell = GhostREPL(tmp_path, Database(tmp_path), session, get_command(app), console)
    shell.help()
    full = output.getvalue()
    assert all(len(line) <= width for line in full.splitlines())
    assert '\x1b' not in full
    for name in ('find', 'auth', 'solve', 'timeline', 'investigations', 'doctor'):
        assert name in full
    if width < 56:
        from surfaces.interactive_shell.shell import COMMANDS
        assert len(full.splitlines()) < 50
        assert 'Scan Python and JavaScript/TypeScript' not in full
        assert all(name in full for name in COMMANDS)


def test_repl_unknown_command_suggests_name_without_echoing_arguments(tmp_path):
    from infrastructure.database.repository import Database
    from surfaces.entrypoint import app
    from surfaces.interactive_shell.shell import GhostREPL
    from typer.main import get_command

    output = io.StringIO()
    console = Console(file=output, width=40, no_color=True)
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch='main')
    shell = GhostREPL(tmp_path, Database(tmp_path), session, get_command(app), console)
    assert shell.dispatch('fnd --token private-value')
    assert 'Did you mean find?' in output.getvalue()
    assert 'private-value' not in output.getvalue()
    assert shell.dispatch('watch extra')
    assert 'watch takes no arguments' in output.getvalue()
    assert shell.dispatch('help watch')
    assert 'Usage: watch' in output.getvalue()


def test_welcome_escapes_control_characters_in_branch(tmp_path, monkeypatch):
    monkeypatch.setenv('TERM', 'dumb')
    output = io.StringIO()
    console = Console(file=output, width=24, no_color=True)
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch='\x1b[red]')
    welcome(console, tmp_path, session)
    assert '\x1b' not in output.getvalue()
    assert '\\u001b' in output.getvalue()


def test_explicit_clear_works_on_no_color_tty(tmp_path, monkeypatch):
    from infrastructure.database.repository import Database
    from surfaces.entrypoint import app
    from surfaces.interactive_shell.shell import GhostREPL
    from typer.main import get_command

    class TTYOutput(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setenv('TERM', 'xterm-256color')
    output = TTYOutput()
    console = Console(file=output, force_terminal=False, width=40)
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch='main')
    shell = GhostREPL(tmp_path, Database(tmp_path), session, get_command(app), console)
    assert shell.dispatch('clear')
    assert output.getvalue().startswith('\x1b[2J\x1b[H')
    assert 'START' in output.getvalue()


@pytest.mark.skipif(os.name != 'posix', reason='PTY support is needed')
def test_no_color_console_uses_real_tty_width_without_escape_codes():
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 40, 0, 0))
        env = {**os.environ, 'NO_COLOR': '1', 'TERM': 'xterm-256color'}
        child = subprocess.Popen(
            [sys.executable, '-c',
             'from surfaces.shared.terminal.runtime import terminal_console; '
             'c=terminal_console(); print(f"width={c.width}"); c.print("[bold red]PLAIN[/]"); '
             'import sys; sys.argv=["ghost", "--help"]; '
             'from surfaces.entrypoint import main; main()'],
            stdin=slave, stdout=slave, stderr=slave, env=env,
        )
        os.close(slave)
        slave = -1
        chunks = []
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    break
                if data:
                    chunks.append(data)
            if child.poll() is not None and not ready:
                break
        if child.poll() is None:
            child.kill()
        assert child.wait(timeout=5) == 0
        output = b''.join(chunks).decode(errors='replace')
        assert 'width=40' in output and 'PLAIN' in output and 'Usage: ghost' in output
        assert '\x1b' not in output
    finally:
        if slave >= 0:
            os.close(slave)
        os.close(master)
