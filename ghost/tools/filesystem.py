from __future__ import annotations

from pathlib import Path


class UnsafePath(ValueError):
    pass


def scoped(repo: Path, relative: str, *, allow_ghost: bool = False) -> Path:
    base = repo.resolve()
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise UnsafePath("Path is outside repository")
    parts = path.relative_to(base).parts
    if ".git" in parts or (not allow_ghost and ".ghost" in parts):
        raise UnsafePath("Protected repository path")
    return path


def read_file(repo: Path, relative: str, start: int | None = None, end: int | None = None) -> str:
    path = scoped(repo, relative)
    if not path.is_file() or path.stat().st_size > 512_000:
        raise UnsafePath("Not a readable source file")
    lines = path.read_text(errors="replace").splitlines()
    return "\n".join(lines[(start or 1) - 1:end])[:32_000]


def list_files(repo: Path, limit: int = 1000) -> list[str]:
    ignored = {".git", ".ghost", "node_modules", "dist", "build", ".next", "__pycache__", ".venv", "venv", "coverage"}
    result = []
    for path in repo.rglob("*"):
        if any(part in ignored for part in path.relative_to(repo).parts):
            continue
        if path.is_file() and not path.is_symlink():
            result.append(str(path.relative_to(repo)))
            if len(result) >= limit:
                break
    return result


def search_code(repo: Path, query: str, limit: int = 50) -> list[str]:
    if not query or len(query) > 200:
        raise ValueError("Invalid search query")
    matches = []
    for relative in list_files(repo):
        path = scoped(repo, relative)
        if path.stat().st_size > 512_000:
            continue
        try:
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if query in line:
                    matches.append(f"{relative}:{number}: {line[:240]}")
                    if len(matches) >= limit:
                        return matches
        except (UnicodeError, OSError):
            continue
    return matches
