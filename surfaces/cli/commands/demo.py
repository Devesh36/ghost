"""A real, self-contained debugging walkthrough in a disposable repository."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from core.agent_harness.orchestrator import debug
from core.agent_harness.progress import progress_handler
from surfaces.shared.terminal.brand import activity
from infrastructure.collectors.commands import recorded_run
from infrastructure.database.repository import Database
from core.domain.types import Event, EventType, Session, now
from infrastructure.repository.git import git
from surfaces.shared.terminal.brand import show_logo
from config import theme

GOOD = "def discounted_price(price, percent):\n    return price * (1 - percent / 100)\n"
BROKEN = GOOD.replace("1 - percent", "1 + percent")
TESTS = (
    "import unittest\nfrom pricing import discounted_price\n\n"
    "class PricingTests(unittest.TestCase):\n"
    "    def test_twenty_percent_discount(self):\n"
    "        self.assertEqual(discounted_price(100, 20), 80)\n\n"
    "    def test_no_discount(self):\n"
    "        self.assertEqual(discounted_price(100, 0), 100)\n"
)


def create_demo(destination: Path, *, broken: bool = True) -> Path:
    """Create only a new directory; commit a tested baseline in that directory."""
    destination.mkdir(parents=True, exist_ok=False)
    repo = destination.resolve()
    (repo / ".gitignore").write_text(".ghost/\n__pycache__/\n.pytest_cache/\n")
    (repo / "pricing.py").write_text(GOOD)
    (repo / "test_pricing.py").write_text(TESTS)
    # -B prevents stale bytecode from hiding the same-size, same-second edit.
    subprocess.run([sys.executable, "-B", "-m", "unittest", "-q"], cwd=repo,
                   check=True, capture_output=True, timeout=30)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    for args in (["init", "-q", "--template="],
                 ["config", "core.hooksPath", os.devnull],
                 ["add", "."],
                 ["-c", "user.name=Ghost Demo", "-c", "user.email=demo@localhost",
                  "-c", "commit.gpgsign=false", "commit", "-qm", "Working pricing baseline"]):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True,
                       capture_output=True, timeout=30)
    if broken:
        (repo / "pricing.py").write_text(BROKEN)
    return repo


async def run_demo(console: Console, *, keep: bool = False) -> None:
    # Git environment overrides can ignore -C and redirect a worktree operation.
    overrides = [key for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")
                 if os.environ.get(key)]
    if overrides:
        raise RuntimeError("Run the demo without Git repository overrides: " + ", ".join(overrides))
    show_logo(console)
    console.print(Text("\n  GUIDED DEMO  /  a discount that became a surcharge", style=f"bold {theme.VIOLET}"))
    console.print(Text("  Real tests and experiments in a temporary sample project.\n"
                       "  The verified fix is applied automatically to this sample.\n"
                       "  No API key is needed.\n", style=theme.MUTED))
    directory = Path(tempfile.mkdtemp(prefix="ghost-demo-"))
    db = session = None
    try:
        console.rule("1 / Start with working code", style=theme.MINT)
        repo = create_demo(directory / "pricing", broken=False)
        db = Database(repo)
        session = Session(repository_path=str(repo), starting_commit=git(repo, "rev-parse", "HEAD").strip(),
                          branch=git(repo, "branch", "--show-current").strip())
        db.start(session)
        db.add_event(Event(session_id=session.id, event_type=EventType.GIT_STATE,
                           metadata={"head": session.starting_commit, "status": ""}))
        # Use this installed interpreter; no pytest or project dependencies needed.
        command = shlex.join([sys.executable, "-B", "-m", "unittest", "-v"])
        console.print("A 20% discount on 100 should cost 80. Both baseline tests must pass.")
        baseline = recorded_run(db, session.id, repo, command, timeout=30)
        if baseline.exit_code != 0:
            raise RuntimeError("The demo baseline failed; see the command output above.")

        console.rule("2 / Introduce and capture a regression", style=theme.MINT)
        (repo / "pricing.py").write_text(BROKEN)
        change = git(repo, "diff", "--no-ext-diff", "--", "pricing.py")
        db.add_event(Event(session_id=session.id, event_type=EventType.FILE_CHANGED,
                           file_path="pricing.py", diff=change,
                           hash_before=hashlib.sha256(GOOD.encode()).hexdigest(),
                           hash_after=hashlib.sha256(BROKEN.encode()).hexdigest()))
        console.print("A one-character edit turns the discount into a surcharge: 120 instead of 80.")
        console.print(Syntax(change, "diff", theme=theme.current().code_theme, word_wrap=True))
        failure = recorded_run(db, session.id, repo, command, timeout=30)
        if failure.exit_code != 1 or "120.0 != 80" not in failure.stderr:
            raise RuntimeError("The expected assertion did not occur; the demo cannot continue reliably.")

        console.rule("3 / Investigate, experiment, and verify", style=theme.MINT)
        console.print("Ghost will reproduce the failure, test competing hypotheses, and verify a minimal fix.")
        # Provider=None keeps this demonstration offline and deterministic. The real
        # orchestrator, judge, worktrees, fixer, verifier and apply guards all run.
        with progress_handler(activity):
            result = await debug(repo, db, session.id, None, console, apply=True)
        for note in result.notes:
            console.print(Text(note, style=theme.MUTED))
        if result.status != "completed" or not result.applied or not result.patch_verified:
            raise RuntimeError("Ghost could not verify and apply the demo fix. See the investigation details above.")

        console.rule("4 / Run the tests again", style=theme.MINT)
        fixed = recorded_run(db, session.id, repo, command, timeout=30)
        if fixed.exit_code != 0:
            raise RuntimeError("The final demo tests failed; no successful demo is claimed.")
        console.print(Panel(Text("DEMO COMPLETE\n\n"
                                 "Failure captured → cause tested → patch verified → both tests pass.\n\n"
                                 "Try it in your project:\n"
                                 "  ghost watch\n"
                                 "  ghost run <your test command>\n"
                                 "  ghost debug", style=theme.MINT), border_style=theme.VIOLET))
    finally:
        if db is not None and session is not None:
            db.end(session.id, now())
        if keep:
            console.print(Text(f"\nDemo files and evidence kept at: {directory / 'pricing'}", style=theme.MUTED))
            console.print(Text(f"cd {shlex.quote(str(directory / 'pricing'))}\nghost report\nghost timeline", style=theme.MINT))
        else:
            shutil.rmtree(directory)
            console.print(Text("Temporary demo project removed. Use demo --keep to retain the evidence.", style=theme.MUTED))
