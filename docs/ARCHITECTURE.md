# Ghost architecture

Ghost follows OpenSRE's layered package layout, adapted to a local terminal debugger.
The console command remains `ghost`; the distribution remains `ghost-debugger`.

```text
.
├── surfaces/
│   ├── entrypoint.py            Console script; composes CLI and REPL
│   ├── cli/
│   │   ├── app.py               Typer commands and command dispatch
│   │   └── commands/            Guided demo and environment diagnostics
│   ├── interactive_shell/
│   │   └── shell.py             REPL, completion, background watching
│   └── shared/terminal/         Rich reports, logo, prompts, motion
├── bootstrap/
│   └── runtime.py              Session and optional provider composition
├── core/
│   ├── agent_harness/          Investigation loop, agents, execution budgets
│   ├── security/               Typed security audits and evidence states
│   ├── domain/types.py         Sessions, events, hypotheses, patch/evidence models
│   ├── llm/                    Provider protocol, fake and compatible providers
│   ├── tool/execution.py       Validated tool requests, dispatch and action logging
│   └── verification/           Discovery of executable verification commands
├── infrastructure/
│   ├── security/               Bounded offline scanner adapter
│   ├── collectors/             File watching, Git diffs, command recording
│   ├── database/               SQLite repository and investigation locking
│   ├── repository/             Scoped files, Git subprocesses, patch installation
│   └── safety/
│       ├── guardrails/         Command policy and bounded process execution
│       ├── masking/            Credential-path and model-input checks
│       └── sandbox/            Git worktrees and OS confinement
├── config/                    Shared defaults and terminal palette
├── tests/                     Unit, adversarial, and isolated integration tests
├── examples/                  Executable sample-project creation
├── assets/                    Ghost wordmark and icon
└── docs/                      Architecture and launch-readiness evidence
```

## Dependency direction

```text
surfaces/entrypoint
        ├── CLI
        └── interactive shell
                 │
                 v
             bootstrap
                 │
                 v
       core <──> infrastructure
                 │
                 v
               config
```

Higher layers may import any lower layer. `core` and `infrastructure` are peers,
as in OpenSRE: execution infrastructure reads harness budgets and domain types,
while agents use persistence and sandbox services. `config` has no first-party
imports. CLI and REPL do not import each other; their composition belongs in
`surfaces/entrypoint.py`, and shared terminal code belongs in `surfaces/shared`.
`tests/test_architecture.py` checks these boundaries, including function-local
imports and references to the retired `ghost.*` source layout.

Current local tool contracts and dispatch live in `core/tool`, with filesystem,
Git, and process mechanics in `infrastructure`. Add OpenSRE-style `tools/` or
`integrations/` capability packages when actual additional adapters need them;
register them through `bootstrap` instead of importing upward from the core.
There is no gateway, web surface, or remote service in this CLI MVP.

## Investigation flow

The CLI composes a session, SQLite repository, optional provider, and terminal
progress callback. The harness records a snapshot and runs code, Git, and runtime
investigators concurrently. Typed tool requests collect bounded evidence. The
experimenter compares real command results in separate worktrees; the judge uses
those results to determine whether patch generation is justified. Verification
executes the proposed patch in another worktree. Working-tree application still
requires explicit approval and source-identity checks.

Terminal animation is injected through a task-local progress callback. The core
has a stable text fallback for direct callers. The orchestrator still constructs
some Rich evidence tables and the final approval prompt; moving those remaining
presentation details behind a complete reporter interface is future work. This
layout change does not claim that presentation has been fully decoupled.

## Development and migration

Install with `pip install -e '.[dev]'` and run `pytest -q`. The wheel explicitly
includes `surfaces`, `bootstrap`, `core`, `infrastructure`, and `config`.
The installed entrypoint is `surfaces.entrypoint:main`; `python -m
surfaces.entrypoint --help` is also supported.

After updating an older editable checkout, reinstall it so its console script
and package paths are refreshed. For a uv tool installation, run
`uv tool install --force --editable .`. Internal Python imports have moved to the
canonical packages above; there are no compatibility forwarding modules under
`ghost/`. CLI commands, environment variables, and `.ghost/` database/worktree
locations are unchanged, so saved sessions need no data migration.

## Security review path

`surfaces/cli/commands/audit.py` invokes the scanner adapter in
`infrastructure/security/bandit.py`. It copies selected source bytes through a
bounded, symlink-refusing reader into a temporary directory, runs the installed
Bandit package under OS confinement and Python isolated mode, validates complete
scanner accounting, and checks source identities again. It never imports project
code. `core/security/models.py` keeps every initial finding in the `suspected`
state with `static` evidence. SQLite stores reports separately from debugging
investigations. A debugging regression's verified patch is not implicitly a
verified security fix; the two workflows currently have separate evidence.
