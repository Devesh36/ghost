"""Render fresh Ghost output from a disposable sample for the website gallery.

Uses Ghost's existing renderers and real confined scanners and repair checks.
No model provider, synthetic scan results, or third-party source is included.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import re
import subprocess
import tempfile

from rich.console import Console
from rich.text import Text

from bootstrap.runtime import session_for
from config import theme
from core.security.solver import solve
from infrastructure.database.repository import Database
from infrastructure.security.review import find_risks
from surfaces.cli.commands.audit import show_audit
from surfaces.cli.commands.security import show_solution
from surfaces.interactive_shell.shell import GhostREPL
from surfaces.shared.conversation import run_ask
from surfaces.shared.terminal.brief import show_brief
from surfaces.shared.terminal.home import show_home
from surfaces.shared.terminal.runtime import configure_console

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".ghost/site-gallery"


def capture(name, command, render):
    console = Console(file=io.StringIO(), width=88, record=True, force_terminal=True,
                      color_system="truecolor", legacy_windows=False)
    configure_console(console)
    console.print(Text(f"$ {command}", style=f"bold {theme.MINT}"))
    console.print()
    render(console)
    html = console.export_html(inline_styles=True)
    terminal = re.search(r"<pre.*?</pre>", html, re.DOTALL).group()
    (OUTPUT / f"{name}.html").write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Ghost terminal capture</title>
<style>*{{box-sizing:border-box}}body{{margin:0;padding:24px;background:#101512;color:#f2eee5}}.window{{width:912px;border:1px solid #465367;border-radius:12px;overflow:hidden;background:#101720}}.bar{{height:48px;display:flex;align-items:center;justify-content:space-between;padding:0 22px;border-bottom:1px solid #293849;font:12px monospace;color:#a1adbd}}.dots{{display:flex;gap:7px}}.dots i{{width:8px;height:8px;border-radius:50%;background:#465367}}.dots i:first-child{{background:#91d9be}}.label{{letter-spacing:1.5px}}.output{{padding:22px 26px}}pre{{margin:0;font:16px/1.5 'Liberation Mono',Consolas,monospace;white-space:pre}}pre code{{font:inherit}}.footer{{border-top:1px solid #293849;padding:12px 22px;font:11px monospace;color:#a1adbd}}</style></head>
<body><div class="window"><div class="bar"><span class="dots"><i></i><i></i><i></i></span><span class="label">GHOST / LOCAL WORKSPACE</span><span>ghost theme</span></div><div class="output">{terminal}</div><div class="footer">Executed sample · Ghost default theme · Source stays local</div></div></body></html>""")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    theme.activate("ghost")
    with tempfile.TemporaryDirectory(prefix="ghost-gallery-") as directory:
        repo = Path(directory) / "demo-project"
        repo.mkdir()
        (repo / ".gitignore").write_text(".ghost/\n__pycache__/\n")
        (repo / "parser.py").write_text("def parse(value):\n    return eval(value)\n")
        (repo / "client.ts").write_text("export const parse = (value: string) => eval(value);\n")
        (repo / "test_parser.py").write_text('''import unittest
from parser import parse

class ParserTests(unittest.TestCase):
    def test_list(self):
        self.assertEqual(parse("[1, 2]"), [1, 2])
    def test_mapping(self):
        self.assertEqual(parse("{'ok': True}"), {'ok': True})
    def test_number(self):
        self.assertEqual(parse("42"), 42)
''')
        subprocess.run(["git", "init", "-q", "--template=", "--initial-branch=main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Ghost sample", "-c", "user.email=sample@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "Disposable gallery sample"], check=True)
        db = Database(repo)
        session = session_for(db, repo)
        capture("01-repl", "ghost repl", lambda console: show_home(console, repo, branch="main", repl=True, release="0.1.0"))
        capture("02-commands", "help  # inside ghost repl", lambda console: GhostREPL.help(type("HelpView", (), {"console": console})()))
        audit = find_risks(repo, db)
        assert audit.status == "completed", audit.notes
        assert {finding.rule for finding in audit.findings} == {"B307", "GJS001"}
        db.save_audit(audit)
        capture("03-findings", "ghost find", lambda console: show_audit(audit, console))
        capture("05-brief", "ghost brief", lambda console: show_brief(audit, console))
        finding = next(finding for finding in audit.findings if finding.rule == "B307")
        source = (repo / "parser.py").read_bytes()
        repair = solve(repo, db, audit, finding, "python -m unittest discover -v")
        assert repair.status == "verified", repair.notes
        project_runs = [check for check in repair.checks if "passed_tests" in check]
        assert len(project_runs) == 2 and all(check["passed_tests"] == 3 for check in project_runs)
        assert (repo / "parser.py").read_bytes() == source
        capture("04-verified-repair", f"ghost solve {finding.id[:8]} --tests 'python -m unittest discover -v'", lambda console: show_solution(repair, console))
        actions = []
        def chat(console):
            def execute(argv):
                actions.append(argv)
                assert argv == ["brief"]
                show_brief(db.latest_audit(), console)
            run_ask(repo, db, console, "summarize the findings", execute=execute)
        capture("06-chat", 'ghost chat "summarize the findings"', chat)
        assert actions == [["brief"]]
        (OUTPUT / "evidence.json").write_text(json.dumps({
            "audit_status": audit.status, "rules": sorted(f.rule for f in audit.findings),
            "repair_status": repair.status, "source_unchanged": True,
            "test_command": "python -m unittest discover -v", "project_tests": 3,
            "model_calls": 0, "theme": "ghost", "width_columns": 88,
        }, indent=2) + "\n")
    print("Captured six real Ghost views; scanners and repair verification passed; sample source unchanged.")


if __name__ == "__main__":
    main()
