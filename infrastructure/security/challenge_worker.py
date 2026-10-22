"""Run explicitly selected unittest cases; emit outcomes, never tracebacks/source."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import unittest


class Discard:
    encoding = 'utf-8'
    def write(self, value):
        return len(value)
    def flush(self):
        pass
    def isatty(self):
        return False


class Outcomes(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.cases = []
        self.unsupported = False

    def record(self, test, outcome):
        name = test.id()
        if not isinstance(name, str) or not name or len(name) > 500 or len(self.cases) >= 1000:
            self.unsupported = True
            self.stop()
            return
        identity = hashlib.sha256(name.encode()).hexdigest()
        if any(row['id'] == identity for row in self.cases):
            self.unsupported = True
        self.cases.append({'id': identity, 'outcome': outcome})

    def addSuccess(self, test):
        self.record(test, 'pass')

    def addFailure(self, test, err):
        self.record(test, 'failure' if issubclass(err[0], AssertionError) else 'error')
        self.failures.append((test, ''))

    def addError(self, test, err):
        self.record(test, 'error')
        self.errors.append((test, ''))

    def addSkip(self, test, reason):
        self.record(test, 'skip')

    def addExpectedFailure(self, test, err):
        self.record(test, 'expected_failure')

    def addUnexpectedSuccess(self, test):
        self.record(test, 'unexpected_success')

    def addSubTest(self, test, subtest, err):
        self.unsupported = True


def main():
    result = Outcomes()
    completed = False
    # Import the trusted worker dependencies before permitting project imports.
    sys.path.insert(0, str(Path.cwd()))
    with contextlib.redirect_stdout(Discard()), contextlib.redirect_stderr(Discard()):
        try:
            suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:])
            def identities(node):
                if isinstance(node, unittest.TestSuite):
                    for child in node:
                        yield from identities(child)
                else:
                    name = node.id()
                    if not isinstance(name, str) or not 1 <= len(name) <= 500:
                        raise ValueError
                    yield hashlib.sha256(name.encode()).hexdigest()
            expected = []
            for identity in identities(suite):
                expected.append(identity)
                if len(expected) > 1000:
                    raise ValueError
            suite.run(result)
            observed = [case['id'] for case in result.cases]
            completed = (not result.unsupported and bool(expected) and len(expected) == len(set(expected))
                         and sorted(expected) == sorted(observed) and result.testsRun == len(expected))
        except BaseException:
            completed = False
    print(json.dumps({'schema_version': 1, 'complete': completed, 'cases': result.cases}))


if __name__ == '__main__':
    main()
