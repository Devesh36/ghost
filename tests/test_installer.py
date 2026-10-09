"""Installer routing and failures are exercised without network or OS changes."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


INSTALLER = Path(__file__).resolve().parents[1] / 'install.sh'


@pytest.fixture
def installer(tmp_path):
    commands = tmp_path / 'bin'
    commands.mkdir()
    log = tmp_path / 'calls.jsonl'
    environment = dict(os.environ, PATH=str(commands), GHOST_TEST_LOG=str(log),
                       GHOST_TEST_PLATFORM='Linux')

    def executable(name):
        program = commands / name
        program.write_text(
            f'#!{sys.executable}\n'
            'import json, os, sys\n'
            'from pathlib import Path\n'
            'name = Path(sys.argv[0]).name\n'
            'with open(os.environ["GHOST_TEST_LOG"], "a") as stream:\n'
            '    stream.write(json.dumps([name, *sys.argv[1:]]) + "\\n")\n'
            'if name == "uname": print(os.environ["GHOST_TEST_PLATFORM"])\n'
            'if name == "uv" and sys.argv[1:] == ["tool", "dir", "--bin"]:\n'
            '    print("/path with spaces/bin")\n'
            'if os.environ.get("GHOST_TEST_FAIL") == name + ":" + " ".join(sys.argv[1:]):\n'
            '    raise SystemExit(9)\n')
        program.chmod(0o755)

    def invoke(*arguments):
        return subprocess.run(['/bin/bash', str(INSTALLER), *arguments], env=environment,
                              capture_output=True, text=True, timeout=15)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    executable('uname')
    return executable, invoke, calls, environment


def test_homebrew_installs_the_qualified_tap_without_overwriting_other_packages(installer):
    executable, invoke, calls, _ = installer
    executable('brew')
    executable('uv')
    outcome = invoke()
    assert outcome.returncode == 0, outcome.stderr
    assert calls() == [['uname', '-s'],
                       ['brew', 'tap', 'devesh36/ghost', 'https://github.com/Devesh36/ghost.git'],
                       ['brew', 'install', '--HEAD', 'devesh36/ghost/ghost']]
    assert 'Ghost installed' in outcome.stdout and 'ghost find' in outcome.stdout


@pytest.mark.parametrize('failed', ['tap devesh36/ghost https://github.com/Devesh36/ghost.git',
                                   'install --HEAD devesh36/ghost/ghost'])
def test_brew_failure_never_claims_install_success(installer, failed):
    executable, invoke, calls, environment = installer
    executable('brew')
    environment['GHOST_TEST_FAIL'] = 'brew:' + failed
    outcome = invoke()
    assert outcome.returncode == 9
    assert 'Ghost installed' not in outcome.stdout
    if failed.startswith('tap'):
        assert len(calls()) == 2


@pytest.mark.parametrize('platform,sandbox', [('Linux', 'bwrap'), ('Darwin', 'sandbox-exec')])
def test_uv_install_checks_prerequisites_and_explains_missing_path(installer, platform, sandbox):
    executable, invoke, calls, environment = installer
    environment['GHOST_TEST_PLATFORM'] = platform
    for name in ('uv', 'git', sandbox):
        executable(name)
    outcome = invoke()
    assert outcome.returncode == 0, outcome.stderr
    assert calls()[1:] == [['uv', 'tool', 'install', '--python', '3.12',
                           'git+https://github.com/Devesh36/ghost.git'],
                          ['uv', 'tool', 'update-shell'], ['uv', 'tool', 'dir', '--bin']]
    assert '"/path with spaces/bin/ghost"' in outcome.stdout


@pytest.mark.parametrize('missing', ['git', 'bwrap'])
def test_missing_uv_prerequisite_exits_before_downloading(installer, missing):
    executable, invoke, calls, _ = installer
    for name in {'uv', 'git', 'bwrap'} - {missing}:
        executable(name)
    outcome = invoke()
    assert outcome.returncode == 1
    assert calls() == [['uname', '-s']]
    assert 'Ghost installed' not in outcome.stdout
    assert ('Git' if missing == 'git' else 'Bubblewrap') in outcome.stderr


def test_uv_failure_stops_before_shell_changes(installer):
    executable, invoke, calls, environment = installer
    for name in ('uv', 'git', 'bwrap'):
        executable(name)
    environment['GHOST_TEST_FAIL'] = 'uv:tool install --python 3.12 git+https://github.com/Devesh36/ghost.git'
    outcome = invoke()
    assert outcome.returncode == 9
    assert len(calls()) == 2 and 'Ghost installed' not in outcome.stdout


def test_no_package_manager_gives_actionable_failure(installer):
    _, invoke, calls, _ = installer
    outcome = invoke()
    assert outcome.returncode == 1 and calls() == [['uname', '-s']]
    assert 'https://brew.sh' in outcome.stderr and 'Ghost installed' not in outcome.stdout


def test_unsupported_os_does_not_call_package_managers(installer):
    executable, invoke, calls, environment = installer
    executable('brew')
    environment['GHOST_TEST_PLATFORM'] = 'MINGW64_NT'
    outcome = invoke()
    assert outcome.returncode == 1 and calls() == [['uname', '-s']]
    assert 'WSL2' in outcome.stderr


def test_help_and_invalid_arguments_make_no_changes(installer):
    _, invoke, calls, _ = installer
    assert invoke('--help').returncode == 0
    assert invoke('--unexpected').returncode == 1
    assert calls() == []
