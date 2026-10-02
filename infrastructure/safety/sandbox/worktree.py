from __future__ import annotations

import shutil
import os
import hashlib
from pathlib import Path
from uuid import uuid4
from infrastructure.repository.git import git
from infrastructure.repository.filesystem import scoped


def source_signature(repo: Path) -> str:
    """Hash observable source state, including untracked files but excluding Ghost data."""
    digest = hashlib.sha256()
    digest.update(git(repo, "diff", "--no-ext-diff", "--binary", "HEAD").encode())
    untracked = git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    for relative in sorted(path for path in untracked.split("\0") if path and not path.startswith(".ghost/")):
        path = repo / relative
        digest.update(relative.encode(errors="surrogateescape"))
        if path.is_symlink():
            digest.update(os.readlink(path).encode(errors="surrogateescape"))
        elif path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    digest.update(chunk)
    return digest.hexdigest()


class Worktree:
    def __init__(self, repo: Path, name: str | None = None, *, snapshot: bool = True,
                 source: Path | None = None, ref: str = "HEAD"):
        self.repo = repo.resolve()
        self.path = self.repo / ".ghost" / "worktrees" / (name or uuid4().hex)
        self.created = False
        self.snapshot = snapshot
        self.source = source.resolve() if source else None
        self.ref = ref

    def __enter__(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        git(self.repo, "worktree", "add", "--detach", str(self.path), self.ref, timeout=30)
        self.created = True
        try:
            if self.snapshot:
                self._copy_working_state()
            self._remove_external_symlinks()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self.path

    def _copy_working_state(self) -> None:
        tracked = set(git(self.repo, "ls-files", "--cached", "-z").split("\0")) - {""}
        if self.source:
            present = set()
            for folder, dirs, files in os.walk(self.source, followlinks=False):
                dirs[:] = [name for name in dirs if name not in {".git", ".ghost"}]
                present.update(str((Path(folder) / name).relative_to(self.source)) for name in files if name != ".git")
        else:
            present = set(git(self.repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")) - {""}
        source_root = self.source or self.repo
        for relative in tracked | present:
            if relative.startswith(".ghost/") or relative == ".ghost":
                continue
            if Path(relative).is_absolute() or ".." in Path(relative).parts or ".git" in Path(relative).parts:
                continue
            source = source_root / relative
            target = self.path / relative
            if source.is_symlink():
                # Never carry a link from the developer checkout into experiments.
                if target.is_symlink():
                    target.unlink()
                continue
            if source.is_file():
                scoped(source_root, relative)
                scoped(self.path, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            elif relative in tracked and target.exists():
                target.unlink()
    def _remove_external_symlinks(self) -> None:
        # Committed links are present even in a clean HEAD worktree.
        for candidate in self.path.rglob("*"):
            if candidate.is_symlink() and not candidate.resolve().is_relative_to(self.path):
                candidate.unlink()

    def __exit__(self, *args):
        if self.created:
            git(self.repo, "worktree", "remove", "--force", str(self.path), timeout=30)
            self.created = False
        return False
