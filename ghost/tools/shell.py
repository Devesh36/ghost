from __future__ import annotations

import os
import signal
import selectors
import shlex
import subprocess
import sys
import time
import re
import codecs
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
    sandboxed: bool = False
    output_truncated: bool = False


FORBIDDEN = {"sudo", "su", "doas", "rm", "rmdir", "mkfs", "dd", "diskutil", "shutdown", "reboot", "poweroff", "chmod", "chown", "curl", "wget", "ssh", "scp", "env", "xargs", "eval", "exec", "nohup"}
AGENT_FORBIDDEN = {"sh", "bash", "zsh", "fish", "npx", "pip", "pip3", "brew", "apt", "apt-get", "dnf", "yum", "docker", "kubectl",
                   "env", "xargs", "find", "mv", "cp", "install", "unlink", "truncate", "shred", "kill", "pkill", "osascript"}
SHELL_OPERATORS = {";", "&&", "||", "|", ">", ">>", "<", "&", "`", "$("}


def parse(command: str, *, agent: bool = False) -> list[str]:
    if any(token in command for token in SHELL_OPERATORS) or "\n" in command:
        raise UnsafeCommand("Shell operators are not allowed; pass a direct command")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise UnsafeCommand(str(exc)) from exc
    if not argv or Path(argv[0]).name in FORBIDDEN:
        raise UnsafeCommand("Command is empty or blocked")
    executable = Path(argv[0]).name
    python = bool(re.fullmatch(r"(?:python|pypy)(?:\d+(?:\.\d+)*)?", executable))
    interpreter = python or executable in {"sh", "bash", "zsh", "fish", "node", "ruby", "perl"}
    if interpreter and any(a in {"-c", "-e", "--eval"}
                           or a.startswith("--eval=")
                           or (a.startswith(("-c", "-e")) and not a.startswith("--")) for a in argv[1:]):
        raise UnsafeCommand("Inline code execution is not allowed")
    if python and any(re.match(r"^-[bBdEhiIOPqRsSuvVW]*c", a) for a in argv[1:]):
        raise UnsafeCommand("Inline code execution is not allowed")
    if executable in {"sh", "bash", "zsh", "fish"} and any(re.match(r"^-[A-Za-z]*c", a) for a in argv[1:]):
        raise UnsafeCommand("Inline shell execution is not allowed")
    if executable == "node" and any((a.startswith("-p") and not a.startswith("--")) or a.startswith("--print") for a in argv[1:]):
        raise UnsafeCommand("Inline code execution is not allowed")
    if executable == "git":
        allowed = {"status", "diff", "log", "show", "rev-parse", "ls-files"}
        if len(argv) < 2 or argv[1] not in allowed or any(
                a in {"--ext-diff", "--textconv"} or a.startswith("--output") for a in argv[2:]):
            raise UnsafeCommand("Only direct read-only Git commands are allowed")
    if agent:
        if executable in AGENT_FORBIDDEN or (python and any(
                a.removeprefix("-m") in {"pip", "pip3", "ensurepip", "http.server"} for a in argv[1:])):
            raise UnsafeCommand("Agent command requires an interactive developer action")
        if executable in {"npm", "pnpm", "yarn", "uv", "cargo"} and any(
                arg in {"install", "add", "update", "upgrade", "publish", "audit", "fetch"} for arg in argv[1:]):
            raise UnsafeCommand("Package or network mutation is not allowed in experiments")
        if executable == "git":
            allowed = {"status", "diff", "log", "show", "rev-parse", "ls-files"}
            subcommand = next((arg for arg in argv[1:] if not arg.startswith("-")), None)
            if subcommand not in allowed:
                raise UnsafeCommand("Only read-only Git commands are allowed in experiments")
    return argv


def run(command: str, cwd: Path, *, timeout: int = 120, output_limit: int = 64_000,
        stream: bool = False, agent: bool = False) -> CommandResult:
    argv = parse(command, agent=agent)
    if timeout <= 0 or output_limit < 1:
        raise ValueError("Timeout and output limit must be positive")
    from ghost.agents.harness import current_harness
    harness = current_harness() if agent else None
    if harness:
        timeout, output_limit = harness.reserve(timeout, output_limit)
    sandboxed = False
    environment = None
    execution_argv = argv
    if agent:
        from ghost.sandbox.process import prepare
        execution_argv, environment, sandboxed = prepare(argv, cwd)
    started = time.monotonic()
    process = subprocess.Popen(execution_argv, cwd=cwd, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.DEVNULL, start_new_session=True, bufsize=0)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    chunks: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
    timed_out = False
    truncated = False
    decoders = {name: codecs.getincrementaldecoder("utf-8")(errors="replace") for name in chunks}
    deadline = started + timeout
    def kill_group():
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        while selector.get_map() or process.poll() is None:
            if harness:
                harness.check()
            if time.monotonic() >= deadline:
                timed_out = True
                kill_group()
                # A detached descendant might retain a pipe. Do not wait on it
                # indefinitely after the command deadline.
                if time.monotonic() >= deadline + 0.5:
                    break
            for key, _ in selector.select(timeout=0.1):
                data = os.read(key.fileobj.fileno(), 4096)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                target = chunks[key.data]
                if len(target) + len(data) > output_limit:
                    truncated = True
                if len(target) < output_limit:
                    target.extend(data[:output_limit - len(target)])
                if stream:
                    out = sys.stdout if key.data == "stdout" else sys.stderr
                    out.write(decoders[key.data].decode(data))
                    out.flush()
        process.wait(timeout=2)
    finally:
        kill_group()  # Also reap descendants that closed their inherited pipes.
        selector.close()
        if process.poll() is None:
            process.wait()
        process.stdout.close()
        process.stderr.close()
        if stream:
            for name, decoder in decoders.items():
                out = sys.stdout if name == "stdout" else sys.stderr
                out.write(decoder.decode(b"", final=True))
                out.flush()
    return CommandResult(argv, 124 if timed_out else process.returncode,
                         chunks["stdout"].decode(errors="replace"), chunks["stderr"].decode(errors="replace"),
                         time.monotonic() - started, timed_out, sandboxed, truncated)
