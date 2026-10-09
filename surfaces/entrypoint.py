"""Compose the CLI and interactive shell without coupling the two surfaces."""
from typer.main import get_command
from bootstrap.runtime import session_for
from surfaces.cli import app as cli
from surfaces.interactive_shell.shell import GhostREPL

app = cli.app


@app.command(rich_help_panel="Start here")
def repl():
    """Open an interactive Ghost session with background file watching."""
    repo, db = cli.context()
    session = session_for(db, repo)
    GhostREPL(repo, db, session, get_command(app), cli.console).run()


def main():
    app()


if __name__ == "__main__":
    main()
