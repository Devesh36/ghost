"""Keep command discovery in the same order as the local review workflow."""
from typer.core import TyperGroup


class WorkflowGroup(TyperGroup):
    def list_commands(self, ctx):
        panels = ('Start here', 'Security review', 'Repair', 'Development', 'Saved history', 'Customize')
        flow = ('home', 'chat', 'repl', 'review', 'guide', 'demo', 'doctor', 'scope', 'find', 'brief', 'findings',
                'audits', 'compare', 'auth', 'audit', 'fix', 'solve', 'solution')

        def order(name):
            panel = getattr(self.commands[name], 'rich_help_panel', None)
            return (panels.index(panel) if panel in panels else len(panels),
                    flow.index(name) if name in flow else len(flow), name)

        return sorted(super().list_commands(ctx), key=order)
