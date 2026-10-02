"""Discover local verification commands without installing dependencies."""
from __future__ import annotations

import json
import shlex
import shutil
import sys
import tomllib
from pathlib import Path


def verification_commands(repo: Path, reproduction: str, locations: list[dict] | None = None) -> list[str]:
    commands = [reproduction]
    argv = shlex.split(reproduction)
    executable = Path(argv[0]).name if argv else ""
    pytest_index = next((i for i, arg in enumerate(argv) if Path(arg).name == "pytest"), None)
    if pytest_index is not None and (executable == "pytest" or "-m" in argv[:pytest_index]):
        test_paths = [arg for arg in argv[pytest_index + 1:] if arg.endswith(".py") or "::" in arg]
        if not test_paths:
            for loc in locations or []:
                if Path(loc["path"]).name.startswith("test_"):
                    commands.insert(0, shlex.join([*argv[:pytest_index + 1], loc["path"], "-q"]))
                    break
        else:
            broad = shlex.join([*argv[:pytest_index + 1], "-q"])
            if broad != reproduction:
                commands.append(broad)
    package_file = repo / "package.json"
    if executable in {"npm", "pnpm", "yarn"} and package_file.exists():
        try:
            scripts = json.loads(package_file.read_text()).get("scripts", {})
        except (OSError, json.JSONDecodeError):
            scripts = {}
        for script in ("lint", "typecheck"):
            if script in scripts:
                commands.append(f"{executable} run {script}")
    config = repo / "pyproject.toml"
    if config.exists():
        try:
            tool = tomllib.loads(config.read_text()).get("tool", {})
        except (OSError, tomllib.TOMLDecodeError):
            tool = {}
        if "ruff" in tool and shutil.which("ruff"):
            commands.append("ruff check .")
        if "mypy" in tool and shutil.which("mypy"):
            commands.append("mypy .")
    return list(dict.fromkeys(commands))
