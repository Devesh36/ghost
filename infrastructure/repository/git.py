from __future__ import annotations

import subprocess
import os
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, timeout: int = 15, binary: bool = False) -> str | bytes:
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("GIT_")}
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull,
                                 "-c", "core.fsmonitor=false", "-C", str(repo), *args],
                                capture_output=True, text=not binary, env=environment, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise GitError("Git command timed out") from exc
    if result.returncode:
        error = result.stderr.decode(errors='replace') if binary else result.stderr
        raise GitError(error.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def root(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip()).resolve()


def state(repo: Path, *, include_diff: bool = True) -> dict[str, str]:
    return {
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "branch": git(repo, "branch", "--show-current").strip() or "(detached)",
        "status": git(repo, "status", "--porcelain=v1", "--untracked-files=normal"),
        "diff": git(repo, "diff", "--no-ext-diff", "--binary") if include_diff else '',
        "staged_diff": git(repo, "diff", "--cached", "--no-ext-diff", "--binary") if include_diff else '',
        "log": git(repo, "log", "-5", "--oneline"),
    }
