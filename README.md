# Ghost 👻

**Your code worked 30 minutes ago. Ghost figures out what you did.**

![Ghost — a local-first time-travel debugger](assets/ghost-logo.svg)

Ghost is a local-first debugging CLI that remembers your coding session and investigates regressions through **evidence, hypotheses, isolated experiments, and executable verification**. It watches edits, captures failed commands, tests possible causes in Git worktrees, and offers a verified patch for your approval.

**Python 3.12+ · macOS / Linux · CLI + interactive REPL · Optional LLM provider**

[Get started](#get-started) · [Run the demo](#see-it-work) · [Commands](#commands) · [Architecture](#how-it-works) · [Safety](#safety-and-local-data)

## Get started

Requires Python 3.12+ and Git. Experiments also require `sandbox-exec` on macOS or `bubblewrap` (`bwrap`) on Linux. Project test dependencies must already be installed.

Clone the repository and install Ghost as a user tool with **uv**:

```bash
git clone https://github.com/Devesh36/ghost.git
cd ghost
uv tool install --editable . --python 3.12
uv tool update-shell
```

Open a new terminal if uv updated your `PATH`, then try:

```bash
ghost --help
ghost demo
```

<details>
<summary>Prefer pip? Install in a virtual environment.</summary>

From the cloned checkout:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ghost demo
```

Activate `.venv` in each new terminal, or call `.venv/bin/ghost` directly. Installing into a virtual environment alone does not put `ghost` on your normal shell's `PATH`.

</details>

## See it work

```bash
ghost demo
```

The demo runs from **any directory**, requires **no API key**, and uses Python's built-in `unittest` runner. It creates a temporary sample repository and walks through a real regression:

```text
1. Start with working code       20% off 100 → 80       tests pass
2. Introduce a one-character bug 20% off 100 → 120      test fails
3. Investigate in worktrees      test competing explanations
4. Verify and apply the fix      20% off 100 → 80       tests pass
```

The sample goes through the same investigators, experiments, judge, fixer, and verifier used by `ghost debug`. A failed experiment or verification is reported as a failure.

The demo automatically applies the verified fix **only to its generated sample**. It removes that sample afterward. To keep the code, timeline, and investigation report:

```bash
ghost demo --keep
```

Ghost prints the directory and commands for inspecting the saved evidence. To investigate the sample manually instead, run [`python examples/create_demo.py`](examples/create_demo.py) from an installed checkout.

## Use it in your project

Start inside a Git repository with at least one commit. Activate your project's development environment so its test runner is available.

```bash
ghost repl
```

![Ghost's interactive terminal](assets/terminal-preview.svg)

Type commands without the `ghost` prefix:

```text
ghost ❯ watch
ghost [watching] ❯ run python -m pytest -q
ghost [watching] ❯ failures --output
ghost [watching] ❯ timeline --limit 20
ghost [watching] ❯ debug
ghost [watching] ❯ report
```

`watch` records edits in the background while you work in your editor. `run` captures the command's output and exit status. `debug` investigates the latest recorded failure and shows its evidence, patch, and verification results before asking:

```text
Apply verified patch to working tree? [y/N]
```

The default answer is **no**. `debug --apply` supplies explicit approval on the command line. If files change during the investigation, Ghost refuses to apply a stale patch.

### Terminal controls

- `help` shows grouped commands; `help run` shows command options.
- `demo` runs the guided example without switching your current project or session.
- `unwatch` stops the background watcher and saves pending events.
- `logo` replays the pixel ghost animation; `clear` redraws the welcome screen.
- **Tab** completes command names; **↑ / ↓** recalls input when readline is available.
- **Ctrl-C** cancels a command or input. **Ctrl-D**, `exit`, or `quit` leaves the REPL.

Input history stays in memory. Set `GHOST_NO_ANIMATION=1` for reduced motion. Animation also turns off for `NO_COLOR`, redirected output, and basic terminals. Investigation spinners run only while actual work is in progress.

### Prefer separate terminals?

```bash
# Terminal 1
ghost watch

# Terminal 2: after changing code
ghost run "python -m pytest -q"
ghost timeline
ghost debug
```

`ghost run` creates a session automatically when needed. Only commands executed through Ghost are recorded.

## Commands

| Command | What it does |
| --- | --- |
| `ghost demo [--keep]` | Run a complete debugging walkthrough in a temporary sample. |
| `ghost doctor [--json]` | Check prerequisites and execute a sandbox write/network probe. |
| `ghost repl` | Open the interactive prompt with background watching. |
| `ghost watch` | Start a session and watch file changes until Ctrl-C. |
| `ghost run <command>` | Execute a command and capture stdout, stderr, timing, and exit status. |
| `ghost debug [--apply]` | Investigate the latest failure; offer a verified patch. |
| `ghost sessions [--limit 20] [--json]` | Browse saved sessions, newest first, with IDs for history inspection. |
| `ghost status` | Show the latest session, branch, base commit, and event counts. |
| `ghost timeline --limit 20` | Inspect recent edits, commands, and failures. |
| `ghost failures --output` | Read failed commands and the tail of their captured output. |
| `ghost diff` | Show tracked changes against HEAD and list untracked files. |
| `ghost report` | Read the latest session's saved investigation. |
| `ghost report --json` | Export that investigation as JSON, or `null` if none exists. |

Use `ghost run --timeout 30 "python -m unittest -v"` to limit a command to 30 seconds. Quoted paths and arguments are supported; shell operators such as pipes and redirects are blocked. A saved report describes its recorded run and does not reverify your current files.

### Revisit an earlier session

```bash
ghost sessions
ghost status --session <id>
ghost timeline --session <id> --limit 30
ghost failures --session <id> --output
ghost report --session <id> --json
```

Use a full session ID or a unique prefix from the list. `--session` also has a `-s` shorthand; without it, these commands inspect the latest session. Ambiguous prefixes produce an error and can be expanded using full IDs from `ghost sessions --json`.

The same commands work inside `ghost repl` without the `ghost` prefix. `help sessions` shows options. Inspecting history does not switch the session used by `watch`, `run`, or `debug`. An **open** session has no recorded end time; this does not establish that its watcher is still running.

The session browser uses a table on wide terminals and cards on narrow ones, honors no-color output, and does not animate. JSON output is an array of session records with full IDs (or `[]` when no sessions exist).

### Execution limits and diagnostics

Run `ghost doctor` before your first investigation. It checks Python, Git, optional model configuration, repository context, and the actual OS sandbox boundaries. `ghost doctor --json` emits machine-readable checks and exits nonzero if a check fails.

Investigations default to a 600-second time budget, 24 experiment/verification commands, and a 120-second cap per command. Adjust the first two with:

```bash
ghost debug --time-budget 300 --max-commands 12
```

An exhausted budget stops the investigation and leaves its evidence in `ghost report`. Ctrl-C asks command workers to stop and waits for their worktree cleanup. Cleanup and synchronous Git/filesystem operations may extend past the time budget. Timeouts and signal-terminated experiments are inconclusive evidence, never proof of a root cause. Reports record final state, limits, and command usage.

## How it works

```text
                 FILE EDITS + GIT STATE + COMMAND RESULTS
                                   │
                                   ▼
                         SQLite session timeline
                                   │
                       frozen source snapshot
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                ▼                ▼
                CODE              GIT            RUNTIME
             investigator     investigator     investigator
                  └────────────────┼────────────────┘
                                   ▼
                        3–5 testable hypotheses
                                   │
                                   ▼
                      isolated worktree experiments
                       ├─ reproduce the failure
                       ├─ reverse a suspect file
                       ├─ compare a clean baseline
                       └─ repeat to probe intermittency
                                   │
                                   ▼
                         evidence-based judgment
                                   │
                                   ▼
                     minimal patch → executable tests
                                   │
                                   ▼
                        report → explicit approval
```

The investigators gather bounded evidence through explicit, validated tools. They examine changed code, call sites, Git history, stack traces, and recorded failures concurrently with `asyncio`.

For uncommitted changes, Ghost compares the captured state with `HEAD`. For committed regressions, it uses the session's starting commit or the previous commit. Every experiment starts from the same frozen snapshot or its chosen Git baseline.

**High confidence requires executable evidence:** the failure reproduces, exactly one changed-file reversal passes, and the comparison experiments finish without supporting a competing hypothesis. Inconclusive evidence stops automatic patch generation.

A proposed patch runs through the reproduction command, directly affected and broader tests where discoverable, and configured lint/type checks where available. Model statements never count as proof that a fix works.

### Project layout

```text
ghost/
├── cli.py / repl.py    CLI entry points and interactive shell
├── demo.py            Self-contained, executable walkthrough
├── collectors/        Filesystem, Git, and command evidence
├── memory/            Typed models and SQLite persistence
├── agents/            Investigators, experiments, judgment, fixes, verification
├── tools/             Validated filesystem, Git, search, and command tools
├── sandbox/           Git worktrees and process confinement
├── llm/               Provider protocol, fake provider, compatible HTTP client
└── ui/                Rich output, pixel identity, and terminal motion
```

## Optional model configuration

Ghost works offline for causal file identification and small one-hunk reversals. An optional model refines hypothesis descriptions and proposes smaller edits when deterministic reversal is too broad.

```bash
export GHOST_API_KEY="your-api-key"
export GHOST_BASE_URL="https://your-provider.example/v1"
export GHOST_MODEL="your-model"
```

The provider must support an OpenAI-compatible chat-completions endpoint. No model is hard-coded. The `LLMProvider` protocol exposes `generate` and `tool_call`; tests use a deterministic fake provider.

The built-in HTTP client enforces a 60-second total request deadline and 1 MiB limits on both the serialized request and response. It streams and bounds the response before parsing JSON, refuses redirects and compressed responses, and requires a nonempty text completion with `finish_reason: "stop"`. Tool responses must be JSON objects; the calling agent validates their expected fields. Provider errors omit response bodies and endpoint URLs. Embedded users can customize these limits with `ProviderLimits`; CLI defaults are fixed. These checks do not redact secrets from outgoing evidence—review the selected endpoint and repository data before enabling model calls.

[`.env.example`](.env.example) lists the settings. Ghost reads environment variables; it does **not** automatically load a `.env` file. When a provider is configured, selected code, diffs, and failure context may be sent to that endpoint. The guided demo always runs without a model provider.

## Safety and local data

Ghost stores session records, events, and investigations under the target repository:

```text
.ghost/
├── ghost.db
├── config.toml
├── logs/
└── worktrees/
```

Add `.ghost/` to your project's `.gitignore`. Observation does not edit repository files. Configure extra watcher exclusions in `.ghost/config.toml`:

```toml
ignore = ["generated", "tmp/*.py"]
```

Common dependency, build, virtual environment, Git, and Ghost directories are excluded by default.

- **Experiments run in disposable Git worktrees.** Ghost detects source changes before applying a verified patch.
- **Single-file patch writes are staged.** Ghost validates every replacement before writing, syncs a temporary file beside the target, and installs it with an atomic rename. Existing permission bits and uniform CRLF line endings are preserved. New files are created with owner-only permissions and cannot overwrite an existing file. Patch targets and their parent paths cannot be symlinks; hardlinked and special files are rejected. Multi-file batches are rejected until transaction recovery is available.
- **Agent operations are logged.** Tool inputs and repository paths are validated; commands have timeouts and bounded captured output.
- **Process confinement limits writes and networking.** macOS uses `sandbox-exec`; Linux uses `bwrap` with a read-only root, writable worktree, and separate network namespace.
- **Commands are screened.** Direct destructive operations, privilege escalation, shell operators, and agent package-install/network commands are blocked.
- **Applying a project fix requires approval.** Debugging never commits or pushes. The demo creates one baseline commit inside its own generated repository.

The process sandbox allows reads needed by runtimes and installed dependencies. `ghost run` executes your chosen project command in the real repository, so use it with code and commands you trust.

If no supported OS sandbox is available, Ghost refuses agent execution. `GHOST_DISABLE_OS_SANDBOX=1` explicitly opts into **worktree-only isolation**, which does not enforce the OS write or network restrictions.

## Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
```

The suite covers persistence, file watching, command capture, tool validation, dangerous-command rejection, sandbox isolation, causal judgment, verification, approval, the REPL, terminal fallbacks, and the guided demo. Integration tests create intentionally broken Git repositories and run real commands; no API key is required. Tests involving experiment execution need the supported OS sandbox.

Brand assets: [wordmark](assets/ghost-logo.svg) · [icon](assets/ghost-icon.svg).

## Current limitations

Launch hardening is in progress. See [the readiness tracker](docs/launch-readiness.md) for completed work, executable checks, and remaining blockers.

Ghost is an MVP focused on reproducible regressions captured with `ghost run`.

- Git comparison is bounded to HEAD, a session baseline, or the parent commit; there is no history bisect yet.
- A passing file reversal implicates a file and may not isolate a single edit. Complex or interacting changes can remain inconclusive.
- External services, ignored dependencies/configuration, and nondeterministic environments may prevent reproduction in a worktree.
- Model-generated patches still require local executable verification; a useful patch is not guaranteed.
- Patch installation supports one file at a time (multiple replacement hunks are allowed). It checks for editor changes immediately before installation, but this is not an atomic compare-and-swap with other writers. Crash/power-loss recovery, directory-entry durability, and preservation of ACLs, extended attributes, and ownership are not yet implemented. Interrupted staging may leave a `.ghost-patch-*.tmp` file beside the target; Ghost excludes these files from watcher events.
- The current interface is a CLI and REPL. There is no editor extension, dashboard, shell-history interception, cloud account, or automatic PR workflow.

When the evidence is insufficient, Ghost reports that result and leaves the project's code unchanged.
