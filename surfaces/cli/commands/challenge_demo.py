"""A real, synthetic repair challenge; no model or developer source changes."""
import os
from pathlib import Path
import shutil
import tempfile

from core.security.challenge import challenge
from core.security.solver import solve
from infrastructure.database.locking import investigation_lock
from infrastructure.database.repository import Database
from infrastructure.security.review import find_risks
from surfaces.cli.commands.challenge import show_challenge
from surfaces.cli.commands.demo import create_demo


def run_challenge_demo(console, *, keep=False):
    if any(os.environ.get(key) for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')):
        raise ValueError('Run the demo without Git environment overrides.')
    directory = Path(tempfile.mkdtemp(prefix='ghost-challenge-demo-')).resolve()
    try:
        repo = create_demo(directory / 'project', broken=False)
        original = 'def parse(value):\n    return eval(value)\n'
        (repo / 'parser.py').write_text(original)
        (repo / 'test_literals.py').write_text('import unittest\nfrom parser import parse\nclass Literals(unittest.TestCase):\n    def test_list(self):\n        self.assertEqual(parse("[1, 2]"), [1, 2])\n')
        (repo / 'test_security.py').write_text('import unittest\nfrom parser import parse\nclass Contract(unittest.TestCase):\n    def test_rejects_calls(self):\n        with self.assertRaises((ValueError, SyntaxError)):\n            parse("sum([1, 2])")\n    def test_keeps_literals(self):\n        self.assertEqual(parse("[1, 2]"), [1, 2])\n')
        db = Database(repo)
        console.rule('GHOST CHALLENGE / make the repair earn its evidence')
        console.print('Synthetic case: a configuration importer must accept literals and reject function calls.\nThe original parser and its repair both pass the ordinary literal test.')
        audit = find_risks(repo, db)
        db.save_audit(audit)
        if audit.status != 'completed':
            raise ValueError('The sample review did not complete.')
        finding = next(f for f in audit.findings if f.rule == 'B307' and f.path == 'parser.py')
        with investigation_lock(repo):
            solution = solve(repo, db, audit, finding, 'python -m unittest test_literals', timeout=30)
            if solution.status != 'verified':
                raise ValueError('The sample proposal did not verify.')
            console.rule('1 / Challenge with the ordinary test: blind to the repair')
            weak = challenge(repo, db, solution, 'python -m unittest test_literals')
            show_challenge(weak, console)
            if weak.status != 'not_supported':
                raise ValueError('The ordinary test unexpectedly discriminated the repair.')
            console.rule('2 / Challenge with the regression contract: fail, pass, fail, pass')
            strong = challenge(repo, db, solution, 'python -m unittest test_security')
            show_challenge(strong, console)
            if strong.status != 'supported' or (repo / 'parser.py').read_text() != original:
                raise ValueError('The challenge did not qualify or changed sample source.')
        console.print('The regression caught the original twice and accepted the repair twice.\nOriginal source is unchanged. No model was called and no patch was applied.')
        if keep:
            console.print(f'Sample kept: {repo}', markup=False)
            console.print('Inspect it with ghost challenge --json or export ghost challenge --report.')
    finally:
        if not keep:
            shutil.rmtree(directory)
