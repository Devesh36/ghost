from pathlib import Path
from ghost.tools.git import git


def file_diff(repo: Path, relative: str) -> str:
    try:
        return git(repo, "diff", "--no-ext-diff", "--", relative)[:16_000]
    except Exception:
        return ""
