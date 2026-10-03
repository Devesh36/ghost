"""Run the real find/solve workflow against a disposable mixed-language fixture."""
import os
from pathlib import Path
import shutil
import tempfile
from core.security.solver import solve, apply_solution
from infrastructure.database.locking import investigation_lock
from infrastructure.database.repository import Database
from infrastructure.security.review import find_risks
from surfaces.cli.commands.audit import show_audit
from surfaces.cli.commands.demo import create_demo
from surfaces.cli.commands.security import show_solution
from surfaces.shared.terminal.brand import activity


def run_security_demo(console, *, keep=False):
    if any(os.environ.get(key) for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')):
        raise ValueError('Run the demo without Git repository environment overrides.')
    directory = Path(tempfile.mkdtemp(prefix='ghost-security-demo-')).resolve()
    try:
        repo = create_demo(directory / 'project', broken=False)
        (repo / 'parser.py').write_text('def parse(value):\n    return eval(value)\n')
        (repo / 'test_parser.py').write_text('import unittest\nfrom parser import parse\n\nclass ParserTests(unittest.TestCase):\n    def test_literal(self):\n        self.assertEqual(parse("[1, 2]"), [1, 2])\n')
        (repo / 'client.ts').write_text('export const parse = (value: string) => eval(value);\n')
        db = Database(repo)
        console.rule('SECURITY DEMO / find, reproduce, repair, verify')
        console.print('A Python parser and a TypeScript helper evaluate expressions.\nOnly the generated Python sample will be repaired automatically.')
        with activity(console, '1 / Find Python and TypeScript risks'):
            audit = find_risks(repo, db)
        db.save_audit(audit)
        show_audit(audit, console)
        if audit.status != 'completed' or not any(f.rule == 'GJS001' for f in audit.findings):
            raise ValueError('Mixed-language scan did not complete. No demo success can be claimed.')
        finding = next(f for f in audit.findings if f.rule == 'B307' and f.path == 'parser.py')
        with investigation_lock(repo):
            with activity(console, '2 / Reproduce evaluation and verify a Python repair'):
                result = solve(repo, db, audit, finding, 'python -m unittest discover -v', timeout=30)
            show_solution(result, console)
            if result.status != 'verified':
                raise ValueError('Security repair verification did not pass.')
            apply_solution(repo, db, result)
        with activity(console, '3 / Rescan the repaired sample'):
            after = find_risks(repo, db)
        db.save_audit(after)
        if after.status != 'completed' or any(f.rule == 'B307' for f in after.findings):
            raise ValueError('Post-application rescan did not confirm the Python repair.')
        console.print('Python repair verified and applied to the sample.', style='green')
        console.print('TypeScript evaluation remains a static finding; automatic JS/TS repairs are not supported yet.', style='yellow')
        if keep:
            console.print(f'Sample kept: {repo}', markup=False)
            console.print('Inside it: ghost findings / ghost solution / ghost timeline')
    finally:
        if not keep:
            shutil.rmtree(directory)
