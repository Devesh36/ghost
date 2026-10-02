"""Read-only environment checks with an executable OS sandbox probe."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
from typing import Literal

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from infrastructure.repository.git import git, root, GitError
from infrastructure.safety.guardrails.commands import run
from surfaces.shared.terminal.brand import MINT, VIOLET, MUTED


class Check(BaseModel):
    name: str
    status: Literal["pass", "warn", "fail", "info"]
    detail: str


def probe_sandbox() -> Check:
    if os.getenv("GHOST_DISABLE_OS_SANDBOX") == "1":
        return Check(name="Sandbox", status="warn", detail="OS isolation is disabled. Unset GHOST_DISABLE_OS_SANDBOX to restore it.")
    try:
        with tempfile.TemporaryDirectory(prefix="ghost-doctor-") as folder:
            parent = Path(folder).resolve()
            workspace = parent / "workspace"
            workspace.mkdir()
            script = workspace / "probe.py"
            script.write_text(
                "import json, socket, sys\nfrom pathlib import Path\n"
                "Path('inside.txt').write_text('allowed')\n"
                "blocked = {}\n"
                "try:\n    Path(sys.argv[1]).write_text('outside')\n"
                "except OSError:\n    blocked['write'] = True\n"
                "else:\n    blocked['write'] = False\n"
                "sock = socket.socket()\n"
                "try:\n    sock.bind(('0.0.0.0', 0))\n"
                "except OSError:\n    blocked['network'] = True\n"
                "else:\n    blocked['network'] = False\n"
                "finally:\n    sock.close()\n"
                "print(json.dumps(blocked))\n")
            # Network namespaces can bind a local socket while still isolating
            # host networking. The Linux probe tests host reachability instead.
            if sys.platform.startswith("linux"):
                return _probe_linux(workspace, script, parent / "outside.txt")
            result = run(shlex.join([sys.executable, str(script), str(parent / "outside.txt")]),
                         workspace, agent=True, timeout=10)
            evidence = json.loads(result.stdout) if result.exit_code == 0 else {}
            if result.sandboxed and evidence == {"write": True, "network": True}:
                return Check(name="Sandbox", status="pass", detail="Verified: local writes work; outside writes and network binds are denied.")
            return Check(name="Sandbox", status="fail", detail="Sandbox probe failed. Check the OS backend before debugging.")
    except Exception as exc:
        return Check(name="Sandbox", status="fail", detail=str(exc))


def _probe_linux(workspace: Path, script: Path, outside: Path) -> Check:
    import socket
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        script.write_text(script.read_text().replace(
            "sock.bind(('0.0.0.0', 0))",
            f"sock.settimeout(1); sock.connect(('127.0.0.1', {server.getsockname()[1]}))"))
        result = run(shlex.join([sys.executable, str(script), str(outside)]), workspace, agent=True, timeout=10)
        evidence = json.loads(result.stdout) if result.exit_code == 0 else {}
    if result.sandboxed and evidence == {"write": True, "network": True}:
        return Check(name="Sandbox", status="pass", detail="Verified: outside writes and host network access are denied.")
    return Check(name="Sandbox", status="fail", detail="Bubblewrap probe failed. Check user namespace support and bwrap permissions.")


def diagnose(cwd: Path) -> list[Check]:
    checks = [Check(name="Python", status="pass" if sys.version_info >= (3, 12) else "fail",
                    detail=f"{sys.version.split()[0]} · Python 3.12+ required")]
    checks.append(Check(name="Git", status="pass" if shutil.which("git") else "fail",
                        detail=shutil.which("git") or "Install Git and add it to PATH."))
    checks.append(probe_sandbox())
    key, model = os.getenv("GHOST_API_KEY"), os.getenv("GHOST_MODEL")
    if bool(key) != bool(model):
        checks.append(Check(name="Model", status="warn", detail="Partial configuration: set both GHOST_API_KEY and GHOST_MODEL, or unset both."))
    else:
        checks.append(Check(name="Model", status="info", detail="Provider configured (connection not tested)." if key else "Offline reasoning available; an API key is optional."))
    try:
        repo = root(cwd)
        git(repo, "rev-parse", "--verify", "HEAD")
        checks.append(Check(name="Repository", status="pass", detail=str(repo)))
    except (GitError, OSError):
        checks.append(Check(name="Repository", status="info", detail="Use a Git repository with an initial commit, or try ghost demo from here."))
    return checks


def show_doctor(console: Console, checks: list[Check]) -> None:
    failures = sum(item.status == "fail" for item in checks)
    warnings = sum(item.status == "warn" for item in checks)
    console.print()
    console.print(Text("  GHOST / ENVIRONMENT", style=f"bold {MINT}"))
    console.print(Text("  Executable checks for your local debugging setup.\n", style=MUTED))
    table = Table(box=None, padding=(0, 2), expand=True)
    table.add_column("Check", style="bold", no_wrap=True)
    table.add_column("Result", no_wrap=True)
    table.add_column("Details", ratio=1)
    colors = {"pass": MINT, "warn": "yellow", "fail": "red", "info": MUTED}
    for check in checks:
        table.add_row(Text(check.name), Text(check.status.upper(), style=colors[check.status]), Text(check.detail))
    console.print(table)
    summary = "Environment checks passed" if not failures and not warnings else f"{failures} failed checks · {warnings} warnings"
    console.print(Panel(Text(summary + "\nNext: ghost demo or ghost repl", style=MINT if not failures else "yellow"),
                        border_style=VIOLET, padding=(1, 2)))
