"""Local command picker; selecting a completion only edits the input buffer."""
import os
import shlex
import sys

from typer.core import TyperArgument, TyperOption
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import has_completions
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style, DynamicStyle

from config.providers import CONNECTION_CHOICES
from surfaces.shared.terminal.brand import compact_label, prompt, unicode_terminal
from config import theme


class CommandCompleter(Completer):
    def __init__(self, commands, command=None):
        self.commands = commands
        self.command = command

    def argument_completions(self, text, requested):
        """Read CLI declarations only; never inspect files or invoke callbacks."""
        prefix, separator, fragment = text.rpartition(' ')
        if not separator or self.command is None:
            return
        try:
            tokens = shlex.split(prefix)
        except ValueError:
            return
        if tokens and tokens[0] == 'ghost':
            tokens = tokens[1:]
        if not tokens:
            return
        name = tokens[0].lstrip('/')
        target = self.command.commands.get(name)
        # Shell commands and conversational prose have their own argument syntax.
        if target is None or name in {'run', 'ask', 'chat', 'fix'}:
            return
        options = {flag: param for param in target.params if isinstance(param, TyperOption)
                   for flag in [*param.opts, *param.secondary_opts]}
        used, positional = set(), []
        pending = None
        index = 1
        while index < len(tokens):
            token = tokens[index]
            if token == '--':
                return
            flag, equal, _ = token.partition('=')
            option = options.get(flag)
            if option is not None:
                used.add(option.name)
                if not option.is_flag and not option.count and not equal:
                    # Skip values without interpreting them as option names.
                    if index + option.nargs >= len(tokens):
                        if option.nargs == 1:
                            pending = option
                        else:
                            return
                        break
                    index += option.nargs
            elif token.startswith('-'):
                return
            else:
                positional.append(token)
            index += 1
        if pending is not None:
            if getattr(pending.type, 'choices', None):
                for choice in pending.type.choices:
                    if str(choice).startswith(fragment):
                        yield Completion(str(choice) + ' ', start_position=-len(fragment),
                                         display_meta=f'Value for {pending.opts[0]}')
            return
        if fragment.startswith('-') or (requested and not fragment):
            for flag, option in options.items():
                if flag.startswith(fragment) and option.name not in used:
                    yield Completion(flag + ' ', start_position=-len(fragment),
                                     display_meta=option.help or 'Command option')
            if '--help'.startswith(fragment) and '--help' not in tokens:
                yield Completion('--help ', start_position=-len(fragment),
                                 display_meta='Show command usage and options')
            return
        arguments = [param for param in target.params if isinstance(param, TyperArgument)]
        if len(positional) < len(arguments):
            argument = arguments[len(positional)]
            if getattr(argument.type, 'choices', None):
                for choice in argument.type.choices:
                    if str(choice).startswith(fragment):
                        yield Completion(str(choice) + ' ', start_position=-len(fragment),
                                         display_meta=getattr(argument, 'help', None) or 'Workflow')

    def get_completions(self, document, complete_event):
        text = document.text
        if document.cursor_position != len(text):
            return
        # A provider menu follows either a slash command or its inserted plain form.
        head, separator, tail = text.partition(' ')
        if head in {'/help', 'help', '/?', '?'} and separator and not any(char.isspace() for char in tail):
            for name, description in self.commands.items():
                if name.startswith(tail):
                    yield Completion(name + ' ', start_position=-len(tail), display_meta=description)
            return
        if (head in {'/connect', 'connect', '/theme', 'theme'}
                and not any(char.isspace() for char in tail) and not tail.startswith('-')):
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
            yield from self.argument_completions(text, complete_event.completion_requested)
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
        'workspace': palette.muted,
        'hint': palette.text,
        'keys': palette.muted,
        'completion-menu.completion': palette.text + ' bg:' + palette.surface,
        'completion-menu.completion.current': palette.background + ' bg:' + palette.accent + ' noreverse',
        'completion-menu.meta.completion': palette.muted + ' bg:' + palette.surface,
        'completion-menu.meta.completion.current': palette.text + ' bg:' + palette.border + ' noreverse',
        'bottom-toolbar': palette.muted + ' bg:' + palette.surface + ' noreverse',
    })


def picker_session(commands, *, command=None, input=None, output=None):
    session = PromptSession(
        completer=CommandCompleter(commands, command), complete_while_typing=True,
        complete_style=CompleteStyle.COLUMN, reserve_space_for_menu=8,
        key_bindings=picker_bindings(), history=InMemoryHistory(),
        enable_system_prompt=False, enable_open_in_editor=False, enable_suspend=False,
        style=DynamicStyle(picker_style), input=input, output=output,
        color_depth=(ColorDepth.TRUE_COLOR if os.getenv('COLORTERM') in {'truecolor', '24bit'}
                     and not os.getenv('PROMPT_TOOLKIT_COLOR_DEPTH') else None),
    )
    session.app.ttimeoutlen = 0.05
    return session


def input_toolbar(session, commands, *, workspace='', branch='', watching=False):
    """Context and discoverable controls, bounded to the current terminal width."""
    width = session.output.get_size().columns
    state = session.default_buffer.complete_state
    if state is not None:
        description = (state.current_completion or state.completions[0]).display_meta_text
        controls = 'Up/Down  Enter insert  Esc close' if width >= 40 else 'Up/Down  Enter  Esc'
    else:
        head = session.default_buffer.text.lstrip('/').split(maxsplit=1)
        description = commands.get(head[0], '') if head else ''
        controls = ('/ commands  Tab options  Ctrl-C cancel  Ctrl-D exit' if width >= 64
                    else '/ commands  Tab  Ctrl-D exit' if width >= 32
                    else '/ cmds  Ctrl-D exit')
    context = workspace + (f' / {branch}' if branch else '')
    if watching:
        context = ('Watching / ' + context) if context else 'Watching source changes'
    top = description or context
    result = []
    if top:
        result.extend([('class:hint' if description else 'class:workspace',
                        ' ' + compact_label(top, max(4, width - 2))), ('', '\n')])
    result.append(('class:keys', ' ' + compact_label(controls, max(4, width - 2))))
    return result


class CommandInput:
    def __init__(self, console, commands, *, command=None, workspace='', branch=''):
        self.console = console
        self.commands, self.workspace, self.branch = commands, workspace, branch
        # NO_COLOR has historically promised completely plain output in Ghost.
        # Pipes and basic terminals keep Python input() and never create a UI app.
        interactive = (sys.stdin.isatty() and getattr(console.file, 'isatty', lambda: False)()
                       and os.getenv('TERM') != 'dumb' and 'NO_COLOR' not in os.environ)
        self.session = picker_session(commands, command=command) if interactive else None

    def read(self, *, watching=False):
        if self.session is None:
            return input(prompt(self.console, watching=watching))
        state = ' [watching]' if watching else ''
        arrow = '❯' if unicode_terminal(self.console) else '>'
        def toolbar():
            return input_toolbar(self.session, self.commands, workspace=self.workspace,
                                 branch=self.branch, watching=watching)
        return self.session.prompt([('class:prompt', f'  ghost{state}'), ('', f' {arrow} ')],
                                   bottom_toolbar=toolbar)
