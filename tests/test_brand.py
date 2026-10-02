import io

from rich.console import Console

from core.domain.types import Session
from surfaces.shared.terminal.brand import activity, motion_enabled, prompt, welcome


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
