"""Best available process confinement for agent-run project commands."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from uuid import uuid4


def prepare(argv: list[str], workspace: Path) -> tuple[list[str], dict[str, str], bool]:
    """Return executable argv, scrubbed environment, and whether OS confinement is active."""
    root = workspace.resolve()
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_') and
                   not any(marker in key.upper() for marker in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
    home = root / ".ghost-home"
    temp = root / ".ghost-tmp"
    cache = root / ".ghost-cache"
    for directory in (home, temp, cache):
        directory.mkdir(exist_ok=True)
    python_cache = str(cache / ('python-' + uuid4().hex))
    environment.update({"HOME": str(home), "TMPDIR": str(temp), "TMP": str(temp), "TEMP": str(temp),
                        "XDG_CACHE_HOME": str(cache), "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTHONPYCACHEPREFIX": python_cache,
                        "GIT_TERMINAL_PROMPT": "0"})
    if re.fullmatch(r'python(?:\d+(?:\.\d+)*)?', Path(argv[0]).name):
        # -I ignores environment settings. Explicit flags prevent cached project
        # bytecode from hiding a same-size, same-timestamp experiment edit.
        argv = [argv[0], '-B', '-X', 'pycache_prefix=' + python_cache, *argv[1:]]
    if os.getenv("GHOST_DISABLE_OS_SANDBOX") == "1":
        return argv, environment, False
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        profile = "\n".join(("(version 1)", "(deny default)", "(allow file-read*)",
                             "(allow process*)", "(allow mach-lookup)", "(allow sysctl-read)",
                             "(allow file-write* (literal \"/dev/null\"))",
                             f"(allow file-write* (subpath {json.dumps(str(root))}))"))
        return ["sandbox-exec", "-p", profile, *argv], environment, True
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return ["bwrap", "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/",
                "--bind", str(root), str(root), "--dev", "/dev", "--proc", "/proc",
                "--chdir", str(root), *argv], environment, True
    from infrastructure.safety.guardrails.commands import UnsafeCommand
    raise UnsafeCommand("No OS sandbox available for agent commands; install bubblewrap on Linux or set "
                        "GHOST_DISABLE_OS_SANDBOX=1 to opt into worktree-only isolation")
