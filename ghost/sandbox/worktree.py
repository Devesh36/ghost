from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4
from ghost.tools.git import git
from ghost.tools.filesystem import scoped


class Worktree:
    def __init__(self, repo: Path, name: str | None = None):
        self.repo = repo.resolve()
        self.path = self.repo / ".ghost" / "worktrees" / (name or uuid4().hex)
        self.created = False

    def __enter__(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        git(self.repo, "worktree", "add", "--detach", str(self.path), "HEAD", timeout=30)
        self.created = True
        try:
            self._copy_working_state()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self.path

    def _copy_working_state(self) -> None:
        tracked = set(git(self.repo, "ls-files", "--cached", "-z").split("\0")) - {""}
        present = set(git(self.repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")) - {""}
        for relative in tracked | present:
            if relative.startswith(".ghost/") or relative == ".ghost":
                continue
            if Path(relative).is_absolute() or ".." in Path(relative).parts or ".git" in Path(relative).parts:
                continue
            source = self.repo / relative
            target = self.path / relative
            if source.is_symlink():
                # Never carry a link from the developer checkout into experiments.
                if target.is_symlink():
                    target.unlink()
                continue
            if source.is_file():
                scoped(self.repo, relative)
                scoped(self.path, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif relative in tracked and target.exists():
                target.unlink()
        # Committed links are present before the copy loop. Remove any that
        # could take an experiment outside its worktree.
        for candidate in self.path.rglob("*"):
            if candidate.is_symlink() and not candidate.resolve().is_relative_to(self.path):
                candidate.unlink()

    def __exit__(self, *args):
        if self.created:
            git(self.repo, "worktree", "remove", "--force", str(self.path), timeout=30)
        return False
