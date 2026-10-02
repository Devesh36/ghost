from __future__ import annotations

import os
import signal
import selectors
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


class UnsafeCommand(ValueError):
    pass


@dataclass
class CommandResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False


FORBIDDEN = {"sudo", "su", "doas", "rm", "rmdir", "mkfs", "dd", "diskutil", "shutdown", "reboot", "poweroff", "chmod", "chown", "curl", "wget", "ssh", "scp"}
SHELL_OPERATORS = {";", "&&", "||", "|", ">", ">>", "<", "&", "`", "$("}


def parse(command: str) -> list[str]:
    if any(token in command for token in SHELL_OPERATORS) or "\n" in command:
        raise UnsafeCommand("Shell operators are not allowed; pass a direct command")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise UnsafeCommand(str(exc)) from exc
    if not argv or Path(argv[0]).name in FORBIDDEN:
        raise UnsafeCommand("Command is empty or blocked")
    if Path(argv[0]).name in {"sh", "bash", "zsh", "fish", "python", "python3", "node", "ruby", "perl"} and any(a in {"-c", "-e", "--eval"} for a in argv[1:]):
        raise UnsafeCommand("Inline code execution is not allowed")
    if argv[0] == "git" and any(a in {"push", "commit", "reset", "clean", "checkout", "switch", "restore"} for a in argv[1:]):
        raise UnsafeCommand("Git mutation is not allowed")
    return argv


def run(command: str, cwd: Path, *, timeout: int = 120, output_limit: int = 64_000, stream: bool = False) -> CommandResult:
    argv = parse(command)
    started = time.monotonic()
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.DEVNULL, start_new_session=True, bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    timed_out = False
    try:
        while selector.get_map():
            if time.monotonic() - started > timeout:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
            for key, _ in selector.select(timeout=0.1):
                data = os.read(key.fileobj.fileno(), 4096)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                target = chunks[key.data]
                if len(target) < output_limit:
                    target.extend(data[:output_limit - len(target)])
                if stream:
                    out = sys.stdout if key.data == "stdout" else sys.stderr
                    out.write(data.decode(errors="replace"))
                    out.flush()
        process.wait(timeout=2)
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    return CommandResult(argv, 124 if timed_out else process.returncode,
                         chunks["stdout"].decode(errors="replace"), chunks["stderr"].decode(errors="replace"),
                         time.monotonic() - started, timed_out)
