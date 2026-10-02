from __future__ import annotations

import os
from pathlib import Path
from ghost.llm.privacy import sensitive_path


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
    if sensitive_path(relative) or sensitive_path(str(path.relative_to(repo.resolve()))):
        raise UnsafePath("Credential files are excluded from source-reading tools")
    if not path.is_file() or path.stat().st_size > 512_000:
        raise UnsafePath("Not a readable source file")
    content = path.read_bytes()
    if b"\0" in content[:4096]:
        raise UnsafePath("Binary file is not source text")
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise UnsafePath("Source text is not UTF-8") from exc
    return "\n".join(lines[(start or 1) - 1:end])[:32_000]


def list_files(repo: Path, relative: str = ".", limit: int = 1000) -> list[str]:
    ignored = {".git", ".ghost", "node_modules", "dist", "build", ".next", "__pycache__", ".venv", "venv", "coverage"}
    base = scoped(repo, relative)
    if sensitive_path(relative) or sensitive_path(str(base.relative_to(repo.resolve()))):
        raise UnsafePath("Credential paths are excluded from source-reading tools")
    if not base.is_dir():
        raise UnsafePath("Not a repository directory")
    result = []
    for folder, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = [name for name in dirs if name not in ignored and not sensitive_path(str((Path(folder) / name).relative_to(repo))) and not (Path(folder) / name).is_symlink()]
        for name in files:
            path = Path(folder) / name
            if name in ignored or path.is_symlink() or sensitive_path(str(path.relative_to(repo))):
                continue
            result.append(str(path.relative_to(repo)))
            if len(result) >= limit:
                return result
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
