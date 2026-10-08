# Use Ghost in your repository

Ghost helps you review security evidence before shipping. Start with a local
repository you control and a disposable demo if you want to see the workflow.

## Install

Requires Python 3.12 or newer and Git. Experiments require `sandbox-exec` on
macOS or `bubblewrap` (`bwrap`) on Linux. Project tests need their dependencies
installed in the Python environment Ghost uses.

Install from a Ghost checkout into that environment:

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
```

Ghost uses the containing Git repository, including when launched from a
subdirectory. It needs an initial commit. Add `.ghost/` to that project's
`.gitignore`; the directory contains local history, settings and experiment data.

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

## Use the interactive shell

```bash
ghost repl
```

Inside Ghost, commands use the same options with a leading slash:

```text
/guide review
/scope
/find
/brief
/findings --id <finding-id>
```

On supported interactive terminals, type `/` to browse commands with the arrow
keys. Enter inserts the selected command; press Enter again to run it. `/theme`
previews and switches palettes. `help <command>` shows options. `exit` leaves
the shell. Plain terminals and piped input use the text fallback.

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
