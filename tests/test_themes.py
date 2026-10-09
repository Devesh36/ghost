"""Appearance changes must be live, persistent, reversible and independent of Git."""
import asyncio
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from prompt_toolkit.document import Document
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
import pytest
from rich.console import Console
from typer.testing import CliRunner

from config import theme
from infrastructure.preferences.theme import PreferenceError, directory, read_saved, save, startup
from surfaces.entrypoint import app
from surfaces.cli.commands.theme import run_theme, preview_theme
from surfaces.shared.terminal.runtime import apply_theme
from surfaces.shared.terminal.brand import welcome
from surfaces.interactive_shell.input import CommandCompleter, picker_session
from surfaces.interactive_shell.shell import COMMANDS
from core.domain.types import Session


@pytest.fixture(autouse=True)
def isolated_preferences(tmp_path, monkeypatch):
    previous = theme.ACTIVE_NAME
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'preferences'))
    monkeypatch.delenv('GHOST_THEME', raising=False)
    monkeypatch.chdir(tmp_path)
    apply_theme('ghost')
    yield
    apply_theme(previous)


@pytest.mark.parametrize('name', theme.THEMES)
def test_save_and_fresh_process_load_without_git_repo(name):
    result = CliRunner().invoke(app, ['theme', name, '--json'])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data['active'] == data['saved'] == name
    assert set(json.loads((directory() / 'theme.json').read_text())) == {'theme'}
    assert (directory() / 'theme.json').stat().st_mode & 0o777 == 0o600
    process = subprocess.run([sys.executable, '-m', 'surfaces.entrypoint', 'theme', '--json'],
                             env=os.environ.copy(), capture_output=True, text=True, timeout=5)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)['active'] == name


@pytest.mark.parametrize('name', theme.THEMES)
@pytest.mark.parametrize('width', [24, 40, 96])
def test_preview_restores_state_does_not_save_and_fits_terminal(name, width):
    apply_theme('nord')
    output = io.StringIO()
    console = Console(file=output, width=width, no_color=True)
    run_theme(console, preview=name)
    shown = output.getvalue()
    assert theme.ACTIVE_NAME == 'nord' and read_saved() is None
    assert 'Preview only' in shown and '\x1b' not in shown
    assert all(len(line) <= width for line in shown.splitlines())
    assert console.get_style('cyan').color.triplet == tuple(int(theme.MINT[i:i+2],16) for i in (1,3,5))


def test_invalid_choices_flags_and_failed_writes_preserve_current_theme(monkeypatch):
    save('nord')
    apply_theme('nord')
    for args in [['theme', 'injected\x1b'], ['theme', 'missing'],
                 ['theme', 'paper', '--preview', 'nord'], ['theme', '--preview', 'paper', '--json']]:
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 2 and theme.ACTIVE_NAME == 'nord'
        assert read_saved() == 'nord' and '\x1b' not in result.output
    def blocked(name):
        raise PreferenceError('Could not safely save the theme.')
    monkeypatch.setattr('surfaces.cli.commands.theme.save', blocked)
    result = CliRunner().invoke(app, ['theme', 'paper', '--json'])
    assert result.exit_code == 2 and 'error' in json.loads(result.output)
    assert theme.ACTIVE_NAME == 'nord' and read_saved() == 'nord'


@pytest.mark.parametrize('link', ['symlink', 'hardlink', 'directory', 'fifo'])
def test_preferences_reject_links_and_special_files_without_touching_target(tmp_path, link):
    directory().mkdir(parents=True)
    target = tmp_path / 'private.json'
    target.write_text('{"theme":"dracula"}')
    settings = directory() / 'theme.json'
    if link == 'symlink': settings.symlink_to(target)
    elif link == 'hardlink': os.link(target, settings)
    elif link == 'directory': settings.mkdir()
    else: os.mkfifo(settings)
    with pytest.raises(PreferenceError): read_saved()
    with pytest.raises(PreferenceError): save('paper')
    assert target.read_text() == '{"theme":"dracula"}'
    assert startup()[0] == 'ghost' and startup()[1]


def test_symlinked_settings_directory_is_refused(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    directory().parent.mkdir(parents=True)
    directory().symlink_to(outside, target_is_directory=True)
    with pytest.raises(PreferenceError): save('paper')
    with pytest.raises(PreferenceError): read_saved()
    assert not list(outside.iterdir())


@pytest.mark.parametrize('body', ['[]', '{"theme":[]}', '{"theme":"unknown"}',
                                   '{"theme":"nord","api_key":"private-value"}',
                                   'x' * 2048, '[' * 1001])
def test_malformed_preferences_fall_back_and_can_be_reset(body):
    directory().mkdir(parents=True)
    (directory() / 'theme.json').write_text(body)
    name, warning = startup()
    assert name == 'ghost' and warning and 'private-value' not in warning
    result = CliRunner().invoke(app, ['theme', 'catppuccin', '--json'])
    assert result.exit_code == 0 and read_saved() == 'catppuccin'


def test_env_overrides_startup_but_explicit_selection_applies_now(monkeypatch):
    save('nord')
    monkeypatch.setenv('GHOST_THEME', 'dracula')
    assert startup() == ('dracula', None)
    result = CliRunner().invoke(app, ['theme', 'paper'])
    assert result.exit_code == 0 and theme.ACTIVE_NAME == 'paper' and read_saved() == 'paper'
    assert 'next launch' in result.output
    monkeypatch.setenv('GHOST_THEME', 'private-invalid-value')
    name, notice = startup()
    assert name == 'ghost' and 'private-invalid-value' not in notice
    monkeypatch.setenv('XDG_CONFIG_HOME', 'relative')
    with pytest.raises(PreferenceError): save('ghost')


def test_preview_restores_even_if_renderer_fails(monkeypatch):
    console = Console(file=io.StringIO())
    def broken(*args, **kwargs): raise RuntimeError('render failed')
    monkeypatch.setattr(console, 'print', broken)
    with pytest.raises(RuntimeError): preview_theme(console, 'paper')
    assert theme.ACTIVE_NAME == 'ghost'


def test_live_theme_updates_existing_prompt_console_and_brand(tmp_path, monkeypatch):
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('TERM', 'xterm-256color')
    console = Console(file=io.StringIO(), width=96, force_terminal=True, color_system='truecolor')
    session = picker_session(COMMANDS, output=DummyOutput())
    for name, palette in theme.THEMES.items():
        apply_theme(name, target=console)
        assert session.style.get_attrs_for_style_str('class:prompt').color == palette.accent[1:]
        assert session.style.get_attrs_for_style_str('').bgcolor == palette.background[1:]
        assert str(console.style.color) and console.style.bgcolor.triplet == tuple(int(palette.background[i:i+2],16) for i in (1,3,5))
        welcome(console, tmp_path, Session(repository_path=str(tmp_path), starting_commit='abc123', branch='main'), animate=False)
    # The compact brand heading now uses a bold accent; color must still update.
    assert '\x1b[1;38;2;0;105;92' in console.file.getvalue()  # Paper's teal accent rendered.
    assert read_saved() is None


@pytest.mark.parametrize('text', ['/theme', '/theme ', 'theme', 'theme '])
def test_theme_completion_names_and_descriptions(text):
    items = list(CommandCompleter(COMMANDS).get_completions(Document(text), CompleteEvent()))
    assert [c.display_text for c in items] == list(theme.THEMES)
    assert all(c.display_meta_text == theme.THEMES[c.display_text].description for c in items)
    assert not list(CommandCompleter(COMMANDS).get_completions(Document('/theme --preview nord'), CompleteEvent()))


def test_theme_selection_is_inserted_before_submission():
    async def scenario():
        async def until(check):
            async with asyncio.timeout(3):
                while not check(): await asyncio.sleep(.01)
        with create_pipe_input() as pipe:
            session = picker_session(COMMANDS, input=pipe, output=DummyOutput())
            task = asyncio.create_task(session.prompt_async('ghost > '))
            try:
                await until(lambda: session.app.is_running)
                pipe.send_text('/theme')
                await until(lambda: session.default_buffer.complete_state is not None)
                pipe.send_text('\x1b[B\x1b[B')
                await until(lambda: session.default_buffer.text == 'theme dracula ')
                pipe.send_text('\r')
                await until(lambda: session.default_buffer.complete_state is None)
                assert not task.done() and theme.ACTIVE_NAME == 'ghost' and read_saved() is None
                pipe.send_text('\r')
                assert await asyncio.wait_for(task,3) == 'theme dracula '
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task,return_exceptions=True)
    asyncio.run(scenario())


def test_all_palettes_have_valid_bounded_colors_and_syntax_themes():
    from pygments.styles import get_style_by_name
    for palette in theme.THEMES.values():
        for key,value in vars(palette).items():
            if key not in {'description','code_theme'}: assert re.fullmatch(r'#[0-9a-f]{6}',value)
        get_style_by_name(palette.code_theme)
