"""Discover workspace context without creating a session or starting a scan."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sqlite3
import os

from infrastructure.database.repository import Database
from infrastructure.database.storage import StorageError
from infrastructure.repository.git import git, root, GitError
from surfaces.shared.terminal.home import show_home


def run_home(console) -> None:
    repo, branch, audit, notice = None, '', None, None
    try:
        candidate = root(Path.cwd())
        git(candidate, 'rev-parse', '--verify', 'HEAD')
        repo = candidate
        branch = git(repo, 'branch', '--show-current').strip()
    except GitError:
        notice = 'Open a Git repository with an initial commit to review your own project.'
    if repo is not None and os.path.lexists(repo / '.ghost' / 'ghost.db'):
        try:
            audit = Database(repo).latest_audit()
        except (StorageError, sqlite3.Error, ValueError):
            notice = 'Saved review could not be read. Run ghost doctor; preserve .ghost before recovery.'
    try:
        release = version('ghost-debugger')
    except PackageNotFoundError:
        release = 'dev'
    show_home(console, repo, branch=branch, audit=audit, notice=notice, release=release)
