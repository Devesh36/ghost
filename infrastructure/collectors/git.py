from pathlib import Path
import difflib
from infrastructure.repository.git import git, GitError


def file_diff(repo: Path, relative: str) -> str:
    try:
        result = git(repo, "diff", "--no-ext-diff", "HEAD", "--", relative)
        if result:
            return result[:16_000]
        try:
            git(repo, "ls-files", "--error-unmatch", "--", relative)
            return ""
        except GitError:
            pass
        path = repo / relative
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= 16_000:
            return "".join(difflib.unified_diff([], path.read_text(errors="replace").splitlines(keepends=True),
                                                fromfile="/dev/null", tofile=relative))[:16_000]
        return ""
    except Exception:
        return ""
