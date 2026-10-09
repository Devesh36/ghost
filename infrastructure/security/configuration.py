"""Hash selected Ghost-owned scanner inputs, without storing their contents."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys

OWN_INPUTS = (
    'infrastructure/security/configuration.py',
    'infrastructure/security/bandit.py',
    'infrastructure/security/bandit_worker.py',
    'config/defaults.py',
    'infrastructure/safety/masking/model_input.py',
    'infrastructure/safety/guardrails/commands.py',
    'infrastructure/safety/sandbox/process.py',
)


def input_digest(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Configuration input is not a regular file')
        content = stream.read(1_000_001)
        if len(content) > 1_000_000:
            raise ValueError('Configuration input exceeds its budget')
    return hashlib.sha256(content).hexdigest()


def scanner_configuration(workspace: Path, command: str, *, engine: str,
                          version: str, scope: str) -> str:
    argv = shlex.split(command)
    if not argv:
        raise ValueError('Scanner command is empty')
    # The interpreter location and temporary directory are not rule identities.
    argv[0] = '<python>'
    paths = OWN_INPUTS + (('infrastructure/security/semgrep.py',
                          'infrastructure/security/semgrep_worker.py') if engine == 'semgrep' else ())
    root = Path(__file__).resolve().parents[2]
    payload = {
        'schema': 'ghost-scanner-configuration-v1', 'engine': engine, 'version': version,
        'scope': scope, 'argv': argv, 'python': list(sys.version_info[:3]), 'platform': sys.platform,
        'staged_config': input_digest(workspace / 'scanner.yaml'),
        'ghost_inputs': {path: input_digest(root / path) for path in paths},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
