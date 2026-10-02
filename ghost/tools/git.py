from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, timeout: int = 15) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GitError("Git command timed out") from exc
    if result.returncode:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def root(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip()).resolve()


def state(repo: Path) -> dict[str, str]:
    return {
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "branch": git(repo, "branch", "--show-current").strip() or "(detached)",
        "status": git(repo, "status", "--porcelain=v1", "--untracked-files=normal"),
        "diff": git(repo, "diff", "--no-ext-diff", "--binary"),
        "staged_diff": git(repo, "diff", "--cached", "--no-ext-diff", "--binary"),
        "log": git(repo, "log", "-5", "--oneline"),
    }
