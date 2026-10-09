"""Local command picker; selecting a completion only edits the input buffer."""
import os
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import has_completions
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style, DynamicStyle

from config.providers import CONNECTION_CHOICES
from surfaces.shared.terminal.brand import prompt, unicode_terminal
from config import theme


class CommandCompleter(Completer):
    def __init__(self, commands):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text
        if document.cursor_position != len(text):
            return
        # A provider menu follows either a slash command or its inserted plain form.
        head, separator, tail = text.partition(' ')
        if head in {'/connect', 'connect', '/theme', 'theme'}:
            if any(char.isspace() for char in tail):
                return
            choices = CONNECTION_CHOICES if head.lstrip('/') == 'connect' else {
                name: palette.description for name, palette in theme.THEMES.items()}
            for name in sorted(choices, key=lambda choice: choice != tail):
                description = choices[name]
                if name.startswith(tail):
                    replacement = name + ' ' if separator else head.lstrip('/') + ' ' + name + ' '
                    yield Completion(replacement, start_position=-len(tail) if separator else -len(head),
                                     display=name, display_meta=description)
            return
        if any(char.isspace() for char in text):
            return
        slash = text.startswith('/')
        if not slash and not complete_event.completion_requested:
            return
        query = text[1:] if slash else text
        for name, description in self.commands.items():
            if name.startswith(query):
                yield Completion(name + ' ', start_position=-len(text),
                                 display='/' + name if slash else name, display_meta=description)


def picker_bindings():
    keys = KeyBindings()

    @keys.add('enter', filter=has_completions)
    def insert_selection(event):
        buffer = event.current_buffer
        state = buffer.complete_state
        buffer.apply_completion(state.current_completion or state.completions[0])

    @keys.add('escape', filter=has_completions, eager=True)
    def dismiss(event):
        event.current_buffer.cancel_completion()

    return keys


def picker_style():
    palette = theme.current()
    return Style.from_dict({
        '': palette.text + ' bg:' + palette.background,
        'prompt': palette.accent,
        'completion-menu.completion': palette.text + ' bg:' + palette.surface,
        'completion-menu.completion.current': palette.background + ' bg:' + palette.accent + ' noreverse',
        'completion-menu.meta.completion': palette.muted + ' bg:' + palette.surface,
        'completion-menu.meta.completion.current': palette.text + ' bg:' + palette.border + ' noreverse',
        'bottom-toolbar': palette.muted + ' bg:' + palette.surface + ' noreverse',
    })


def picker_session(commands, *, input=None, output=None):
    session = PromptSession(
        completer=CommandCompleter(commands), complete_while_typing=True,
        complete_style=CompleteStyle.COLUMN, reserve_space_for_menu=8,
        key_bindings=picker_bindings(), history=InMemoryHistory(),
        enable_system_prompt=False, enable_open_in_editor=False, enable_suspend=False,
        style=DynamicStyle(picker_style), input=input, output=output,
        color_depth=(ColorDepth.TRUE_COLOR if os.getenv('COLORTERM') in {'truecolor', '24bit'}
                     and not os.getenv('PROMPT_TOOLKIT_COLOR_DEPTH') else None),
    )
    session.app.ttimeoutlen = 0.05
    return session


class CommandInput:
    def __init__(self, console, commands):
        self.console = console
        # NO_COLOR has historically promised completely plain output in Ghost.
        # Pipes and basic terminals keep Python input() and never create a UI app.
        interactive = (sys.stdin.isatty() and getattr(console.file, 'isatty', lambda: False)()
                       and os.getenv('TERM') != 'dumb' and 'NO_COLOR' not in os.environ)
        self.session = picker_session(commands) if interactive else None

    def read(self, *, watching=False):
        if self.session is None:
            return input(prompt(self.console, watching=watching))
        state = ' [watching]' if watching else ''
        arrow = '❯' if unicode_terminal(self.console) else '>'
        def toolbar():
            if self.session.default_buffer.complete_state:
                if self.session.output.get_size().columns < 30:
                    return 'Up/Down  Enter  Esc'
                if self.session.output.get_size().columns < 52:
                    return '/  Up/Down  Enter  Esc'
                return 'Up/Down browse  ·  Enter insert  ·  Esc close'
            if self.session.output.get_size().columns < 52:
                return '/ commands  Ctrl-D exit'
            return '/ commands  ·  home workspace  ·  Ctrl-D exit'
        return self.session.prompt([('class:prompt', f'  ghost{state}'), ('', f' {arrow} ')],
                                   bottom_toolbar=toolbar)
