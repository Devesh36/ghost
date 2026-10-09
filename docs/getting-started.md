# Use Ghost in your repository

Ghost helps you review security evidence before shipping. Start with a local
repository you control and a disposable demo if you want to see the workflow.

## Install

Requires Python 3.12 or newer and Git. Experiments require `sandbox-exec` on
macOS or `bubblewrap` (`bwrap`) on Linux. Project tests need their dependencies
installed in the Python environment Ghost uses.

### One-command installation

With Homebrew already installed:

```bash
brew tap devesh36/ghost https://github.com/Devesh36/ghost.git && brew install --HEAD devesh36/ghost/ghost
```

This repository contains `Formula/ghost.rb` and acts as its own custom tap.
The formula installs Git, Python 3.12, uv and Linux Bubblewrap, then installs
Ghost and its locked runtime dependencies in a dedicated environment. It
downloads dependencies during installation and follows the development `main`
branch; it is not a Homebrew core formula or a versioned stable release.

Alternatively, the installer picks Homebrew or an existing uv installation:

```bash
curl -fsSL https://raw.githubusercontent.com/Devesh36/ghost/main/install.sh | bash
```

You can inspect the script at that URL before running it. Without Homebrew,
the uv path requires Git and your OS sandbox already installed. It installs
Ghost as a user tool and uses `uv tool update-shell` to update shell startup
files for PATH; open a new terminal if prompted. On Ubuntu/Debian, install
the sandbox with `sudo apt install bubblewrap`. No sudo commands are run by
the installer. If neither package manager is available, it shows where to
install one and exits without claiming success.

To update a Homebrew development installation:

```bash
brew update
brew upgrade --fetch-HEAD devesh36/ghost/ghost
```

Uninstall with `brew uninstall devesh36/ghost/ghost` (or `uv tool uninstall
ghost-debugger` for uv). Your projects' local `.ghost/` history is kept.

### Install in a project environment

For Python repairs, install Ghost into the same environment as your project's
test dependencies. Homebrew/user-tool environments do not automatically share
them. Install from a Ghost checkout into the project environment:

```bash
git clone https://github.com/Devesh36/ghost.git
cd ghost
python -m pip install -e .
ghost --help
ghost demo --security
```

The demo creates its own sample, finds Python and TypeScript candidates, and
verifies a Python repair. Its approved change applies only to the sample.

## Choose the project

After installation, change to the repository you want Ghost to review:

```bash
cd ~/Dev/my-app
git rev-parse --show-toplevel
git rev-parse --verify HEAD
ghost doctor
ghost
```

Ghost uses the containing Git repository, including when launched from a
subdirectory. It needs an initial commit. Add `.ghost/` to that project's
`.gitignore`; the directory contains local history, settings and experiment data.

`ghost` opens the workspace overview without starting a scan or session. It
suggests one next step: check coverage for a first review, resolve diagnostic
notes for an incomplete scan, or inspect the highest-priority saved candidate.
Use `ghost home` to return to this overview. Saved results do not recheck current
source; rerun `ghost find` after edits.

## Run your first review

```bash
ghost scope
ghost find
ghost brief
ghost findings --id <finding-id>
```

`scope` shows selected files and blind spots. `find` executes the scanners and
saves a review. `brief` shows the highest-severity static candidates, local
access counts and next steps. `findings` provides the full saved context.

`find` returns 0 when selected checks completed without reported findings, 1
when findings were reported, and 2 when checks are incomplete. These are scoped
scan results. Reading a saved brief returns 0 on success even when its audit is
incomplete; it is an inspection command.

To review an older snapshot, use `ghost audits`, then
`ghost brief --audit <audit-id>`. After edits, run `ghost find` again and
`ghost compare` to compare the latest two compatible static reviews.

For a larger review, group candidates before opening individual evidence:

```bash
ghost findings --group-by file
ghost findings --group-by rule --limit 5
ghost findings --path src/parser.py --rule B307
ghost findings --severity HIGH --confidence HIGH
ghost findings --id <finding-id>
```

`--path` matches an exact repository-relative path; filters combine. Grouped
views count matching candidates and show a command for their highest-priority
example. `--limit` limits groups when grouping and finding cards otherwise.
An empty filtered list does not mean the full review is clean. Full review
counts, incomplete coverage and local access results remain visible.

For tools that accept SARIF, `ghost sarif --audit <audit-id> > review.sarif`
exports saved static candidates without rescanning or uploading them. Check
the command's exit status and review metadata before sharing. Incomplete review
warnings stay in the file, and authorization proofs are omitted from static
results. See [SARIF export](sarif-export.md) for format and coverage details.

One-finding views explain why the pattern may matter, what to verify and the
available repair path. Priority uses severity, then static confidence, then
location; confidence does not establish exploitability. `--json` continues to
export the complete saved record and cannot be combined with list filters.

## Use the interactive shell

```bash
ghost repl
```

Inside Ghost, commands use the same options with a leading slash:

```text
/guide review
/home
/scope
/find
/brief
/findings --id <finding-id>
```

On supported interactive terminals, type `/` to browse commands with the arrow
keys. Enter inserts the selected command; press Enter again to run it. `/theme`
previews and switches palettes. `help <command>` shows options. `exit` leaves
the shell. Plain terminals and piped input use the text fallback.

Plain commands and copied CLI commands such as `ghost findings --id <id>` also
work in the REPL. The command menu starts with the local review workflow; AI
connections are optional. Review cards put higher-severity candidates first and
provide next commands with the selected finding and audit IDs already filled in.

## While you code

In the REPL, `/watch` observes edits in the background; `/unwatch` stops it.
Use `/run python -m pytest -q` to record a chosen command and `/timeline` to
read the events. Standalone `ghost watch` occupies its terminal until Ctrl-C.

If a recorded command fails, `ghost failures --output` shows captured evidence.
`ghost debug` investigates the latest recorded failure in isolated worktrees.
`ghost run` executes your chosen trusted command in the actual repository.

## Verify a supported repair

Choose a finding ID from the latest review, then run:

```bash
ghost solve <finding-id> --tests "python -m pytest -q"
ghost solution
```

Use your project's test command. Ghost checks support for the repair recipe,
reproduces the behavior, generates a patch in a worktree and runs verification.
It asks before applying a verified change to your project. Answer N to leave the
project unchanged and inspect the proof. Unsupported findings need manual review.

After applying an approved repair, rerun `ghost find` and your own tests.
`ghost sandboxes` inspects leftover experiment paths if a run was interrupted.

## Add AI advice if useful

Use `ghost connect` or `/connect` to choose a provider. Ghost supports Codex,
Claude Code, Claude's API, OpenAI-compatible APIs and other configured options.
Consult `ghost connect --help` and the [provider guide](../README.md#commands).

Ask questions with `ghost ask "What should I review first?"` or natural language
in the REPL. Chat advice does not execute commands or establish evidence.
`ask --context` and `ask --finding <id>` opt into sharing saved summary metadata
with the provider. Local security checks work without a model connection.

Continue with [security briefs](security-brief.md), the
[command reference](../README.md#commands), or [Ghost's safety model](../README.md#safety-and-local-data).
