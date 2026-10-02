# Ghost 👻

**Your code worked 30 minutes ago. Ghost figures out what you did.**

Ghost watches a coding session, records changes and command failures, and investigates a regression with executable experiments in isolated Git worktrees. It records hypotheses and evidence locally in SQLite. A verified patch reaches your working tree only after you confirm it.

## What it does

```text
watch / run → SQLite timeline → code + Git + runtime investigators
                                     ↓
                             file hypotheses
                                     ↓
                    reproduce failure in worktree
                                     ↓
                  restore one changed file at a time
                                     ↓
                         evidence-based judgment
                                     ↓
                   minimal patch → sandbox verification
                                     ↓
                         optional user approval
```

The three investigators gather evidence concurrently. Ghost tests each changed-file hypothesis by reproducing the recorded failure and running the same command with that file restored to `HEAD`. A passing reversal is causal evidence. If exactly one reversal passes, Ghost proposes a small one-hunk reversal when possible, or asks a configured model to propose a validated text edit. It verifies the proposed patch in another worktree before offering to apply it.

## Install

Requires Python 3.12+ and Git.

```bash
pip install -e .
ghost --help
```

The CLI exposes `watch`, `run`, `debug`, `status`, and `timeline`.

## Quick demo

From a Git repository with an existing commit:

```bash
ghost watch
# In another terminal, edit a source file and run:
ghost run "python -m pytest -q"
ghost timeline
ghost status
ghost debug
```

`ghost watch` runs until Ctrl-C. `ghost run` also creates a session automatically, so a watcher is optional for command-based debugging. If Ghost verifies a patch, it asks `Apply verified patch to working tree? [y/N]`. Use `ghost debug --apply` to supply that approval on the command line.

Configure an OpenAI-compatible chat completions endpoint if you want model-generated minimal patches:

```bash
export GHOST_API_KEY=...
export GHOST_BASE_URL=https://api.openai.com/v1
export GHOST_MODEL=your-model
```

Ghost can identify a causal file and produce simple one-hunk reversals without an API key. The model is only asked for a patch after experiments establish a single high-confidence cause. The model interface is replaceable; tests use a fake provider.

## Local data and safety

Ghost creates `.ghost/ghost.db`, `.ghost/config.toml`, and temporary `.ghost/worktrees/` directories. It adds no Git commits and does not push. Add `.ghost/` to your repository's `.gitignore` if it is not present. Set extra watched directory names in `.ghost/config.toml`, for example `ignore = ["generated", "tmp"]`.

Agent file tools are repository-scoped and typed. Agent commands run only inside isolated worktrees, with timeouts, output limits, and a blocklist for destructive commands. Ghost does not use a shell for commands, and it rejects shell operators. `ghost run` intentionally executes the command you supply in the real repository, as a normal developer command would. The watcher never modifies Git state.

## Development

```bash
pip install -e '.[dev]'
pytest -q
```

Tests cover persistence, watcher filtering and debounce, Git diff collection, command capture, unsafe command rejection, worktree isolation, and an end-to-end failure → hypothesis → experiment → verified patch flow.

## Current limits

Ghost focuses on changes relative to `HEAD` and recorded commands. It does not yet bisect historical commits, infer arbitrary test commands, or attempt a patch when evidence is ambiguous. The safety command filter is conservative: commands that need shell pipelines or network access must be run directly by the developer outside agent experiments. Worktrees use the current tracked and untracked file state, but external services or environment state may prevent a failure from reproducing. A passing single-file reversal shows that a file is involved; it may not isolate the exact line when a file has several independent edits.

A Git worktree isolates repository files, but it is not an operating system sandbox. Project test code can still access resources available to the current user. Run Ghost only against repositories and test commands you trust.
# ghost
