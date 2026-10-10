"""Exercise real input events: menu selection must never accept a command line."""
import asyncio
import io

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from typer.main import get_command

from core.domain.types import Session
from infrastructure.database.repository import Database
from surfaces.entrypoint import app
from surfaces.interactive_shell.input import CommandCompleter, CommandInput, input_toolbar, picker_session
from surfaces.interactive_shell.shell import COMMANDS, GhostREPL


def completions(text, *, requested=False, cursor=None):
    return list(CommandCompleter(COMMANDS).get_completions(
        Document(text, cursor_position=cursor), CompleteEvent(completion_requested=requested)))


def test_slash_lists_every_command_with_description_and_filters():
    items = completions('/')
    assert [item.text.strip() for item in items] == list(COMMANDS)
    assert all(item.start_position == -1 and item.display_meta_text == COMMANDS[item.text.strip()]
               for item in items)
    assert [item.text for item in completions('/sol')] == ['solve ', 'solution ']
    assert completions('/not-a-command') == []
    assert [item.text for item in completions('gu', requested=True)] == ['guide ']


@pytest.mark.parametrize('text,cursor', [('hello', None), ('what can you do?', None),
                                        ('run python /tmp/file.py', None),
                                        ('/run --timeout 10', None), ('/find', 2)])
def test_menu_never_completes_prose_arguments_or_inside_a_token(text, cursor):
    assert completions(text, cursor=cursor) == []


async def until(check):
    async with asyncio.timeout(3):
        while not check():
            await asyncio.sleep(.01)


def test_arrow_navigation_enter_inserts_then_requires_explicit_submission():
    async def scenario():
        with create_pipe_input() as pipe:
            session = picker_session(COMMANDS, input=pipe, output=DummyOutput())
            task = asyncio.create_task(session.prompt_async('ghost > '))
            try:
                await until(lambda: session.app.is_running)
                pipe.send_text('/')
                await until(lambda: session.default_buffer.complete_state is not None)
                pipe.send_text('\x1b[B')  # Home leads the local workflow menu.
                await until(lambda: session.default_buffer.text == 'home ')
                pipe.send_text('\x1b[B')
                await until(lambda: session.default_buffer.text == 'guide ')
                pipe.send_text('\x1b[A')
                await until(lambda: session.default_buffer.text == 'home ')
                pipe.send_text('\x1b[B')
                await until(lambda: session.default_buffer.text == 'guide ')
                pipe.send_text('\r')
                await until(lambda: session.default_buffer.complete_state is None)
                assert not task.done()  # Selection edits input; no command can dispatch.
                pipe.send_text('review\r')
                assert await asyncio.wait_for(task, 3) == 'guide review'
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_escape_reverts_selection_and_menu_can_reopen_before_eof():
    async def scenario():
        with create_pipe_input() as pipe:
            session = picker_session(COMMANDS, input=pipe, output=DummyOutput())
            task = asyncio.create_task(session.prompt_async('ghost > '))
            try:
                await until(lambda: session.app.is_running)
                pipe.send_text('/sol')
                await until(lambda: session.default_buffer.complete_state is not None)
                pipe.send_text('\x1b[B')
                await until(lambda: session.default_buffer.text == 'solve ')
                pipe.send_text('\x1b')
                await until(lambda: session.default_buffer.complete_state is None)
                assert session.default_buffer.text == '/sol' and not task.done()
                await asyncio.sleep(.1)
                assert session.default_buffer.complete_state is None
                pipe.send_text('\x15/')  # Ctrl-U clears, slash reopens.
                await until(lambda: session.default_buffer.complete_state is not None)
                assert len(session.default_buffer.complete_state.completions) == len(COMMANDS)
                pipe.send_text('\x1b')
                await until(lambda: session.default_buffer.complete_state is None)
                pipe.send_text('\x15')
                await until(lambda: not session.default_buffer.text)
                pipe.send_text('\x04')
                with pytest.raises(EOFError):
                    await task
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_no_color_and_piped_input_use_plain_reader(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')
    monkeypatch.setattr('builtins.input', lambda label: '/guide review')
    reader = CommandInput(Console(file=io.StringIO()), COMMANDS)
    assert reader.session is None and reader.read() == '/guide review'


def test_slash_dispatch_keeps_command_guards_and_does_not_send_unknowns_to_ai(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('Slash commands must not become model questions')
    monkeypatch.setattr('surfaces.interactive_shell.shell.run_ask', unexpected)
    out = io.StringIO()
    session = Session(repository_path=str(tmp_path), starting_commit='abc123', branch='main')
    shell = GhostREPL(tmp_path, Database(tmp_path), session, get_command(app),
                      Console(file=out, width=96, no_color=True))
    assert shell.dispatch('/guide review')
    assert 'Before you ship' in out.getvalue()
    assert shell.dispatch('/unknown --token private-value')
    assert 'Unknown slash command.' in out.getvalue() and 'private-value' not in out.getvalue()
    assert shell.dispatch('/')
    assert 'Ghost / Commands' in out.getvalue()
    assert not shell.dispatch('/exit')


@pytest.mark.parametrize('text', ['/connect', '/connect ', 'connect', 'connect '])
def test_connect_menu_lists_providers_with_setup_description(text):
    from config.providers import CONNECTION_CHOICES
    items = completions(text)
    assert [item.display_text for item in items] == list(CONNECTION_CHOICES)
    assert all(item.display_meta_text == CONNECTION_CHOICES[item.display_text] for item in items)
    for item in items:
        assert text[:len(text) + item.start_position] + item.text in {
            'connect ' + item.display_text + ' ', '/connect ' + item.display_text + ' '}
    assert [item.display_text for item in completions('/connect claude')] == ['claude', 'claude-code']
    assert not completions('/connect claude --model chosen')
    assert not completions('ask /connect')


def test_command_selection_opens_provider_menu_and_provider_insertion_requires_submission():
    async def scenario():
        with create_pipe_input() as pipe:
            session = picker_session(COMMANDS, input=pipe, output=DummyOutput())
            task = asyncio.create_task(session.prompt_async('ghost > '))
            try:
                await until(lambda: session.app.is_running)
                pipe.send_text('/con')
                await until(lambda: session.default_buffer.complete_state is not None)
                pipe.send_text('\r')
                await until(lambda: session.default_buffer.text == 'connect ' and
                            session.default_buffer.complete_state is not None)
                state = session.default_buffer.complete_state
                assert [c.display_text for c in state.completions][:3] == ['codex', 'claude-code', 'claude']
                pipe.send_text('\x1b[B\x1b[B')
                await until(lambda: session.default_buffer.text == 'connect claude-code ')
                pipe.send_text('\r')
                await until(lambda: session.default_buffer.complete_state is None)
                assert not task.done()
                pipe.send_text('\r')
                assert await asyncio.wait_for(task, 3) == 'connect claude-code '
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def cli_completions(text, *, requested=False):
    command = get_command(app)
    def unexpected(*args, **kwargs):
        pytest.fail('Completion must not execute a CLI command')
    for target in command.commands.values():
        target.callback = unexpected
    return list(CommandCompleter(COMMANDS, command).get_completions(
        Document(text), CompleteEvent(completion_requested=requested)))


def test_options_follow_cli_declarations_and_skip_used_options_and_values():
    assert [item.text for item in cli_completions('/find --t')] == ['--timeout ']
    assert [item.text for item in cli_completions('ghost find --t')] == ['--timeout ']
    assert '--json ' not in [item.text for item in cli_completions('/find --json --')]
    assert '--timeout ' not in [item.text for item in cli_completions('/find --timeout=10 --')]
    assert '--timeout ' not in [item.text for item in cli_completions('/find --timeout 10 --')]
    assert '--help ' in [item.text for item in cli_completions('find ', requested=True)]
    assert cli_completions('/find ') == []
    for text in ('find --timeout ', 'findings --path --', 'findings --path "unfinished',
                 'run python --', 'ask explain --', 'chat how --', 'fix update --', 'find -- --'):
        assert cli_completions(text) == []


def test_workflow_help_and_finite_option_values_are_discoverable():
    assert [item.text for item in cli_completions('/guide ')] == ['daily ', 'review ', 'repair ']
    assert [item.text for item in cli_completions('guide rep')] == ['repair ']
    assert cli_completions('guide review ') == []
    assert [item.text for item in cli_completions('/findings --group-by ')] == ['file ', 'rule ']
    assert [item.text for item in cli_completions('/findings --group-by r')] == ['rule ']
    assert [item.text for item in cli_completions('/help sol')] == ['solve ', 'solution ']


def test_option_and_choice_insertion_never_submits_the_command():
    async def scenario():
        with create_pipe_input() as pipe:
            session = picker_session(COMMANDS, command=get_command(app), input=pipe, output=DummyOutput())
            task = asyncio.create_task(session.prompt_async('ghost > '))
            try:
                await until(lambda: session.app.is_running)
                pipe.send_text('/findings --group')
                await until(lambda: session.default_buffer.complete_state is not None)
                pipe.send_text('\r')
                await until(lambda: session.default_buffer.text == '/findings --group-by ' and
                            session.default_buffer.complete_state is not None)
                assert not task.done()
                pipe.send_text('\x1b[B\x1b[B')
                await until(lambda: session.default_buffer.text == '/findings --group-by rule ')
                pipe.send_text('\r')
                await until(lambda: session.default_buffer.complete_state is None)
                assert not task.done()
                pipe.send_text('\r')
                assert await asyncio.wait_for(task, 3) == '/findings --group-by rule '
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize('width', [24, 40, 80])
def test_toolbar_is_responsive_and_repository_labels_are_literal(width):
    from types import SimpleNamespace
    from rich.cells import cell_len
    from prompt_toolkit.data_structures import Size
    class SizedOutput(DummyOutput):
        def get_size(self):
            return Size(rows=24, columns=width)
    session = SimpleNamespace(output=SizedOutput(), default_buffer=SimpleNamespace(complete_state=None, text=''))
    pieces = input_toolbar(session, COMMANDS, workspace='project\x1b[2J', branch='main\u202e', watching=True)
    text = ''.join(value for _, value in pieces)
    assert '\x1b' not in text and '\u202e' not in text
    assert 'Watching' in text
    assert 'Ctrl-D exit' in text
    assert all(cell_len(line) <= width for line in text.splitlines())
    if width >= 40:
        assert '\\u001b' in text
    session.default_buffer.text = 'find'
    text = ''.join(value for _, value in input_toolbar(session, COMMANDS))
    assert 'Scan Python' in text
    assert all(cell_len(line) <= width for line in text.splitlines())
