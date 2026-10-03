# Ghost launch readiness

Release status: **more hardening is required before a production launch**.

This document is the handoff for manual launch-readiness work. The hourly schedule is paused at the owner's request. Keep work bounded, preserve user changes, test behavior before marking an item complete, commit and push verified improvements to GitHub, and leave release decisions to the owner.

## Configured cross-user access proof (2026-10-03)

- `ghost auth --init` writes a private example contract under ignored `.ghost/`.
  A developer defines synthetic owner and other-user headers and a local GET route.
- `ghost find --auth` runs those requests against a Python ASGI app or a CommonJS
  request handler in an OS-confined disposable worktree. It records status codes,
  scope and verdict, not headers or bodies. Owner failure, timeout, unavailable
  runtime, malformed results or disabled confinement make the check incomplete.
- `ghost auth --prepare-candidate` copies the app into a private proposed-fix file.
  `ghost auth --candidate` runs the baseline and proposed app in **separate fresh
  worktrees**, then verifies that an observed cross-user failure is denied while
  the owner still succeeds. The tested candidate hash is saved. The real checkout is not changed; its active failure
  keeps exit 1 until the developer updates it and reruns the check.
- CLI and REPL help, JSON persistence, narrow/no-color output and Python/JS
  examples document the supported behavior. The tests use a real FastAPI app and
  a local Node handler; both demonstrate confirmed exposure before the fix and
  expected denial after it.

This is a developer-authored local contract, not automatic IDOR discovery, a live
network test, or general Express support. It runs trusted project code with OS
confinement that still allows broad file reads. No claim of universal security
coverage or production readiness follows from a passing case. Broader tenant and
authorization workflows remain open.

Verification on macOS: the full suite passed **262 tests in 325.05s**. After
adding a world-readable-contract and malicious-candidate regression, the focused
authorization suite passed **21 tests in 62.71s** after the final candidate-hash
recording change. A fresh wheel install
included both worker files and the `auth` command. Its installed CLI ran the Node
sample end to end: baseline confirmed, candidate denied, real checkout unchanged,
worktrees cleaned. No-color terminal output showed both cards without ANSI. The
test fixture also used a real FastAPI app for Python. This is evidence for the
configured examples, not measured recall on real projects. Linux remains untested.

## Current product direction — security first (2026-10-03)

The owner selected **Python and JavaScript/TypeScript, with Python fixes first**.
Primary workflow: explicit `watch`/`run` context → `find` → inspect `findings` →
`solve <id>` → executable verification → approval. Keep CLI/REPL polish and useful
commands recurring priorities. The existing debugger remains available; new work
should prioritize security proof, useful coverage, triage and safe repairs.
Do not claim all-terminal capture, universal vulnerability discovery, or better
accuracy than competitors without benchmarks. Capture remains explicit. The
previously recorded Ghost Security naming overlap still requires an owner decision.

### Implemented in the security pivot

- `find` checks Python with Bandit and JS/TS with four local Semgrep rules, saves
  per-engine coverage and a bounded session metadata summary, and rejects source
  changes between engine runs. `audit` retains the Python-only path.
- The JS worker strips inherited Semgrep controls, disables metrics/version checks,
  uses trusted bundled configuration, ignores project suppressions, and executes
  under existing OS confinement. The macOS profile now permits read-only system
  metadata (`sysctl-read`) required by the scanner; write/network denial remains.
- A constant-false parse coverage rule forces JS/TS parsing even without security
  keywords. This closes a demonstrated incomplete-parse accounting gap; strict
  scanner errors prevent a passing review. Four security rules are unchanged.
- `solve` supports one deliberately narrow Python B307 literal-parser recipe.
  Passing baseline tests, original/modified trusted helper probes, unchanged
  project files, matching positive test counts with no skipped cases, Python
  rescan and fresh checkout identity are required. No LLM statement is used as proof.
  Tests run only in isolated worktrees; the checkout lock includes approval/apply.
- `solution` retains repair evidence separately from static candidates. The source
  audit always remains suspected. Noninteractive repair defaults to no application;
  `--apply` is explicit authorization. Unsupported/stale/failed repairs are persisted.
- CLI and REPL now lead with security commands. README, terminal preview and logo
  tagline reflect the new direction. `demo --security` runs mixed-language scanning,
  Python reproduction/repair and post-application rescanning in its generated sample.

### Scope still missing

This is a first security repair, not a general vulnerability-fixing agent. The
probe establishes helper behavior only, not attacker input or remote reachability.
It intentionally narrows expression evaluation to literals; `literal_eval` is not
resource-exhaustion protection. Project tests are trusted code. Summaries/counts
are imperfect coverage evidence and do not defeat malicious test output. No new
regression-test file is retained in the project yet. JS/TS repairs, framework-aware
automatic authorization/tenant discovery, dependency CVEs and benchmarked triage remain open.

Repair validation reads at most 1,000 regular project files, 512 KB each and 16 MB
total, after worktree creation. Five subprocesses are bounded to 120 seconds each.
Initial worktree copying, source signatures, Git operations and cleanup are not
covered by a single wall deadline. Read confidentiality, detached processes,
transaction durability and Linux execution coverage remain existing blockers.

### Verification completed for the security pivot

- Full suite on macOS: `pytest -q` — **243 passed in 286.76s**. This includes the
  prior debugger, sandbox, persistence and terminal tests plus new real scanning
  and isolated repair cases. This run preceded final presentation and error text
  changes.
- Focused security, architecture and brand suite after those changes:
  **54 passed in 100.28s**. One final CLI regression for the stale finding error
  passed separately (**1 passed in 9.30s**) after the last error handling edit.
- Ran `ghost demo --security` from a fresh installed wheel. It found Python and
  TypeScript candidates, reproduced and verified the Python repair in a worktree,
  applied it only to the generated sample, then rescanned. The TypeScript candidate
  remained open. A generated fixture also confirmed that declined interactive
  approval leaves the developer checkout unchanged.
- A real Semgrep parse error (`eval(!!!!`) returned an incomplete result; an
  earlier malformed TypeScript fixture exposed a prefilter gap, which the bundled
  parse coverage rule closed. An inherited Semgrep baseline/configuration override,
  project suppressions, no tests, skipped/failed tests, unsafe parser shapes,
  stale source, checkout changes and test-induced source mutation were exercised.
- Fresh wheel installation and the global editable installation both included
  Semgrep 1.179.0 and the CLI commands. `ghost doctor --json` passed the actual
  macOS sandbox probe after the profile change: local writes worked, outside writes
  and network binds were denied. Linux/bubblewrap was not executed.
- Inspected real interactive/no-color REPL output and a rendered terminal preview;
  `git diff --check` and Python compilation passed. No package was published.

This evidence supports the bounded workflow above, not production readiness or
complete vulnerability detection.

## Completed in the first hardening pass

- Added a per-investigation execution harness: a default 600-second time budget, 24 experiment/verification commands, 120 seconds per command, and 64,000 captured bytes per stream. `ghost debug --time-budget` and `--max-commands` expose the principal limits.
- Added cooperative cancellation: command workers observe cancellation, terminate their process groups, and finish worktree cleanup before the snapshot is removed. Final state and command counts are persisted, including cancellation and exhausted budgets.
- Fixed timeout handling when a command closes stdout/stderr while continuing to run. Pipe draining is bounded after the deadline; output truncation is observable.
- Rejected several concrete command-policy bypasses: versioned Python inline execution, attached inline flags, absolute-path Git mutations, Git option overrides/output writes, execution wrappers, and versioned Python package installation.
- Isolated internal Git operations from inherited `GIT_*` environment overrides and disabled Git hooks/fsmonitor for those operations.
- Made timed-out or signal-terminated experiments inconclusive, including reproduction. They cannot establish a high-confidence root cause.
- Added `ghost doctor` / `doctor` and JSON output. The sandbox check executes a controlled probe: writes inside its own temporary directory must work; writes outside and host network access must fail.
- Protected snapshot cleanup when recording an investigation event fails; failed investigations retain their final status.
- Refined the session panel and diagnostic screen with consistent colors, typography, and literal rendering of repository metadata. Saved reports show execution state and command usage.

## Verification for this pass

- Targeted command-policy, timeout, cancellation, command-budget, Git-scope, and diagnostic tests passed on macOS.
- The existing executable investigation test passed after harness integration.
- `ghost doctor --json` passed an actual macOS sandbox write/network probe.
- Full suite: `pytest -q` — 56 passed in 131.08 seconds.
- Additional deadline regression: `pytest -q tests/test_execution.py -k expired_investigation_time_budget` — 1 passed, 22 deselected in 3.11 seconds. This test was added after the full-suite run; application code was unchanged.
- `ghost demo` completed the real isolated investigation and verification pipeline successfully, then removed its sample repository.
- Globally installed `ghost doctor --json` and `ghost debug --help` exposed the new diagnostics and budget controls.
- The Rich diagnostic screen was rendered and visually inspected; `git diff --check` and Python compilation passed.
- These results were obtained on macOS. Linux sandbox behavior remains unverified in this pass.

Time budgets are cooperative around filesystem/Git operations. Cleanup can extend past the budget. The built-in HTTP provider has a total request deadline; an uncooperative third-party provider still needs additional deadline enforcement. Command screening is defense in depth; process confinement is the execution boundary.

## Completed in the provider transport pass

- Bounded serialized model requests and raw HTTP responses to 1 MiB each by default, with validated `ProviderLimits` for embedded clients. Oversized requests fail before network access; oversized responses stop streaming and close the connection.
- Added a 60-second total deadline across connection setup and body streaming, including servers that continuously send small chunks. Cancellation propagates and closes the response.
- Refused redirects and compressed response bodies. The client requests identity encoding to avoid decompression before enforcing its byte limit.
- Required complete, nonempty text responses (`finish_reason: "stop"`), valid JSON without non-finite numbers, and JSON objects for tool responses. Existing agent models retain responsibility for field validation.
- Replaced HTTP error details with bounded messages that omit provider bodies, endpoint URLs, and transport exception text. This does not redact outbound prompts or other local logs.

### Verification for the provider transport pass

- `pytest -q tests/test_provider.py`: 32 passed in 6.79 seconds. Includes response/request limits, multibyte request accounting, compression refusal, malformed/nested JSON, HTTP errors, redirect refusal, transport error privacy, cancellation, and deadlines.
- A real loopback HTTP server continuously sent chunks; the total deadline terminated the request and closed the connection.
- An actual isolated investigation reproduced a regression and identified its cause, then refused an incomplete model patch response. The developer source signature was unchanged and no worktrees leaked.
- Full suite: `pytest -q` — 89 passed in 150.07 seconds on macOS, including the guided demo and existing worktree isolation/approval checks. No external model service or real API key was used.
- `git diff --check` and Python compilation passed. Linux sandbox behavior was not tested in this pass.

## Completed in the session browsing pass

- Added `ghost sessions` / REPL `sessions` with bounded listing, local start times, branch names, honest open/ended labels, and `--json` output containing full IDs.
- Added `--session` / `-s` to status, timeline, failures, and report. Exact IDs and unique literal prefixes resolve historical sessions; missing or ambiguous IDs fail with recovery guidance. Browsing does not switch the current session or its watcher.
- Added a responsive mint/violet history screen: wide tables, narrow cards, actionable empty states, and command hints. The new screen escapes control and bidi formatting characters in metadata, renders Rich markup literally, and stays static for interactive and piped output.
- Added REPL command discovery and documented historical-session examples. Existing commands still inspect the latest session when no selector is supplied.

### Verification for the session browsing pass

- `pytest -q tests/test_sessions.py tests/test_brand.py`: 15 passed in 7.13 seconds. Covers historical selection across all four inspection commands, JSON output, empty history, ambiguous/missing IDs, SQL wildcard/injection strings, bounded lists, metadata controls, and a live REPL watcher that stays on its original session.
- Rendered and visually inspected the colored screen at 40 and 100 columns; automated layout checks passed at 24, 40, 80, and 120 columns with ASCII/no-color output.
- Exercised `watch`, `sessions`, historical `status`, `help sessions`, latest `status`, and `exit` through an actual PTY REPL with reduced motion. The watcher continued during history inspection and stopped on exit.
- The installed `ghost sessions --json` returned parseable JSON without terminal controls from a disposable sample repository.
- Full suite: `pytest -q` — 101 passed in 146.10 seconds on macOS, including existing isolated debugging and guided-demo checks. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the single-file patch installation pass

- Reproduced two defects before implementation: patch application converted CRLF to LF and followed an in-repository symlink to modify its referent. Both regressions now pass.
- Moved patch installation into a deterministic filesystem tool. It validates all hunks for one target, stages complete bytes beside the target, flushes and syncs them, and uses atomic rename for replacements. Failures before installation preserve the original target; temporary files are removed during normal exception handling. Failures during post-install cleanup and crashes still require recovery work.
- Existing permission bits and uniform CRLF endings survive replacement. Newly created files use owner-only mode and an exclusive link operation that refuses to overwrite concurrent file creation. Binary, oversized, hardlinked, special-permission, protected, and non-regular targets are rejected.
- Directory descriptors and no-follow opens reject symlink traversal. Preparation checks verify the directory chain and file identity/content before committing; edits observed during that preparation stop installation. This is optimistic conflict detection, not atomic compare-and-swap or hostile-filesystem containment.
- Multiple replacement hunks in one file are supported. Multi-file batches and combined create/delete sequences are rejected before mutation until transaction recovery is available. Ghost's current causal fixer already restricts proposals to one file.
- The watcher ignores reserved `.ghost-patch-*.tmp` staging names while still observing the installed target.

### Verification for the single-file patch installation pass

- Before implementation: the CRLF and symlink regression tests both failed, demonstrating the existing defects.
- `pytest -q tests/test_patch_application.py`: 21 passed in 0.22 seconds. Covers partial writes, fsync/rename failures, editor writes during preparation, parent symlink swaps, concurrent creation, multi-file rejection, multiple-hunk validation, nested creation/deletion, cleanup, protected paths (including case variants), hardlinks, and watcher filtering.
- Full suite: `pytest -q` — 122 passed in 142.13 seconds on macOS, including real worktree investigations, provider-generated fixes, explicit approval, source protection, and the guided demo. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the investigation history pass

- Added `ghost investigations` and REPL `investigations` with bounded results, session selection, full-record JSON export, responsive tables/cards, and actionable empty states.
- Added `ghost report --id` for exact IDs or unique literal prefixes. ID lookups search the repository's sessions unless explicitly restricted by `--session`; invalid, ambiguous, or mismatched selections never fall back to a different report.
- Reproduced and fixed the saved-investigation ordering bug: updating an old investigation previously changed its SQLite row ID and made it appear latest. Saves now update existing records in place, and listing/latest queries use recorded start time with a deterministic ID tie-break and a matching index.
- Shared literal rendering across the session/history views and saved reports. Model text, experiment conclusions, command names, patch excerpts, and notes escape terminal/direction controls. Patch labels require recorded successful verification and reject timed-out verification details. These are saved results, not a fresh verification or liveness check.

### Verification for the investigation history pass

- Before implementation, the regression test confirmed that updating an older investigation incorrectly changed the latest report.
- `pytest -q tests/test_investigations.py tests/test_sessions.py tests/test_brand.py`: 30 passed in 7.53 seconds. Covers history ordering, selection/scoping, literal SQL prefixes, malformed/ambiguous selections, empty history, JSON, REPL discovery, saved-report control characters, patch labels, and layouts from 24 to 120 columns.
- Rendered and visually inspected colored history screens at 40 and 110 columns with synthetic saved-record fixtures. Exercised listing, selecting a stopped report, command help, and exit through an actual reduced-motion PTY REPL.
- The installed CLI returned valid, control-free JSON for the history list and a selected report in a disposable repository.
- Full suite: `pytest -q` — 137 passed in 140.25 seconds on macOS, including the existing real debugging, approval, isolation, and demo checks. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the investigation locking pass

- Reproduced concurrent entry: two investigations could enter the same checkout simultaneously. Added a nonblocking OS advisory lock before investigation persistence or snapshot creation.
- The lock covers the entire investigation, approval/application, worker drain, worktree cleanup, and final persistence. A competing CLI/REPL request returns a clear “Investigation not started” message and exit code 2 without creating a second investigation.
- Uses a persistent, empty `.ghost/investigation.lock` file opened without following symlinks; non-regular and hardlinked files are rejected. The file is never unlinked during normal operation, preventing different contenders from locking different inodes. Descriptor inheritance across exec is disabled.
- Process exit releases the OS lock; leftover lock-file existence is not used as a liveness indicator. Different checkout directories remain independent. Advisory locking coordinates cooperating Ghost processes, not editors or hostile lock-file replacement.

### Verification for the investigation locking pass

- The concurrency regression failed before implementation, confirming that the second investigation previously entered and persisted.
- `pytest -q tests/test_investigation_lock.py`: 11 passed in 0.44 seconds. Covers same-process overlap, separate-process exclusion and force-kill recovery, cancellation through worker cleanup, exception/final-persistence failure release, persistent inode reuse, independent checkouts, symlinks/hardlinks/FIFOs, and CLI/REPL recovery guidance.
- Full suite: `pytest -q` — 148 passed in 141.76 seconds on macOS, including real debugging, approval, isolation, and demo checks.
- With a separate process holding the lock, the installed CLI in a real terminal returned exit 2 and actionable guidance; it created no investigation, source edit, or worktree. After release, the installed CLI reproduced a real sample failure, verified and applied its fix, and cleaned all experiment worktrees.
- `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## Completed in the model evidence privacy pass

- Confirmed the previous file reader exposed a synthetic `.env` credential; the new reader rejects that path. Common credential files/directories are excluded from source reads, listings, and searches, including aliases that resolve to credential paths.
- Added a provider-independent request check at both built-in agent reasoning call sites. It checks system text, evidence, and schemas before invoking a provider; the HTTP provider additionally checks explicitly configured API credentials against message content.
- Recognizes selected secret-named environment values (eight or more characters, including JSON-escaped forms), private-key headers, selected token formats, and quoted credential assignments. Blocks the entire request with a content-free reason; deterministic analysis can continue without sending redacted source for patch generation.
- Model patch proposals refuse credential paths even when the source file was deleted. This does not prevent deterministic local analysis, raw Git access, or sandboxed commands from accessing local evidence.

### Verification for the model evidence privacy pass

- Reproduced `.env` disclosure using the pre-change reader from Git against a synthetic fixture, then confirmed rejection by the new reader.
- `pytest -q tests/test_privacy.py tests/test_provider.py`: 57 passed in 7.11 seconds before the added local-fallback integration test.
- `pytest -q tests/test_privacy.py`: 26 passed in 6.47 seconds. Covers path exclusions, symlink aliases, quoted/multiline/Unicode environment values, credential patterns, system/schema boundaries, zero HTTP-client/provider invocation on rejection, and unchanged transmission of ordinary evidence.
- A real isolated investigation with a synthetic credential in runtime output made zero model calls, reproduced the bug, established a cause, verified a patch, left developer source unchanged, and cleaned its worktrees.
- Full suite: `pytest -q` — 174 passed in 145.34 seconds on macOS, including the final deleted-credential-file check, existing provider/guardrail tests, real investigations, and guided demo. `git diff --check` and Python compilation passed. Linux was not tested in this pass.

## OpenSRE-style source layout — 2026-10-02

Completed the owner's request to organize Ghost like the local OpenSRE project,
using its canonical architecture document as the reference:

- Moved the working implementation into `surfaces`, `bootstrap`, `core`,
  `infrastructure`, and `config`; removed the old `ghost/` package without adding
  forwarding modules. Existing CLI commands and `.ghost/` storage formats remain
  unchanged.
- Separated CLI/REPL composition in `surfaces/entrypoint.py`, session/provider
  composition in `bootstrap/runtime.py`, domain types in `core/domain`, and
  persistence, repository operations, masking, guardrails, and sandbox mechanics
  in `infrastructure`. Added the canonical source map in `docs/ARCHITECTURE.md`.
- Removed the core's import of terminal UI through a task-local progress callback;
  actual CLI/demo operations still receive the existing accessible activity UI.
  Some Rich tables and approval rendering remain in the orchestrator, documented
  as future presentation-decoupling work.
- Added an AST import-boundary test to reject upward dependencies, CLI/REPL peer
  imports, and retired `ghost.*` imports. Updated all test/example imports,
  monkeypatch paths, wheel package inclusion, and the console entrypoint.

Verification:

- Full macOS suite: `.venv/bin/python -m pytest -q` — **175 passed in 162.75s**,
  including real isolated investigations, adversarial safety tests, approval
  protection, persistence/history, and the new architecture check.
- Built a wheel with `uv build --wheel`, installed it in a fresh temporary virtual
  environment, and ran `ghost --help` and the complete `ghost demo` from `/tmp`.
  The demo reproduced the bug, established causal evidence, verified/applied the
  sample fix, passed both tests, and removed its worktrees/sample repository.
  Isolated Python imports confirmed packages loaded from the wheel's site-packages.
- Inspected a real PTY REPL (`help`, `status`, `exit`) and a piped 40-column REPL
  (`help status`, `sessions`, `exit`) with no color/reduced motion; the latter
  exited successfully with no ANSI escapes. Refreshed the development editable
  install and the user's global uv tool install, then checked `ghost repl --help`.
- Python compilation and final staged whitespace checks passed. This was local
  macOS verification; Linux and automated clean-install CI remain outstanding.

Later passes should use the canonical packages and preserve the checked dependency
boundaries. Reinstall older editable checkouts to refresh their entrypoint.

## Retry command and terminal workflow — 2026-10-02

- Added `ghost retry` and REPL `retry` to repeat the latest session's newest
  completed failure in the current checkout. `--dry-run` shows and validates the
  exact saved command without subprocess execution or new run events; `--timeout`
  defaults to 120 seconds. The command uses the same parsing/execution guards as
  `ghost run` and clearly identifies its current-working-tree semantics.
- Added a database query that selects failures by insertion order without a
  timeline-window cutoff. It excludes successful/incomplete commands and test
  summary/error events. It never falls back to an older session. Execution opens
  a new session if the source session ended; previews leave sessions untouched.
- New start/finish/error events retain the source session and failure timestamp
  as retry metadata. Commands retain their original quoting. Failures, timeouts,
  launch errors, and signal exits return observable exit statuses; successful
  execution is reported only after the actual command passes.
- Added a responsive command preview with literal rendering of saved metadata,
  safe handling of terminal/direction controls, and clear result/next-action text.
  CLI help and the REPL guide/completion expose the new command. Documented
  examples, scope, timeout behavior, and exit codes in the README.

Verification:

- Focused initial suite: retry, architecture, sessions, and execution tests —
  **53 passed in 27.50s**. Added one further signal/launch-error regression test
  afterward; the full-suite result is recorded below.
- Real installed CLI flow in a temporary Git project: captured failing unittest
  command, previewed without adding events, retried and reproduced the failure,
  ran `ghost debug --apply` with the model disabled, then retried successfully.
  The real investigation verified/applied the sample fix and cleaned its worktrees.
- Inspected piped 40-column/no-color/reduced-motion preview and success output;
  no ANSI escapes in the preview. Tests cover widths 24/40/80 with hostile saved
  command text, quote preservation, stdout/stderr capture, missing or blocked
  commands, ended/empty sessions, bounded execution, and REPL dispatch.
- Full macOS suite: `.venv/bin/python -m pytest -q` — **193 passed in 174.16s**.
  A real PTY REPL also passed `help retry`, `retry --dry-run`, `retry`, and `exit`;
  the retry executed both sample tests successfully. Python compilation and
  whitespace checks passed. Linux was not exercised in this pass.

Limitations: this is explicit developer-command replay, not sandbox execution.
As with `ghost run`, scripts run against the current working tree/environment.
Raw live stdout/stderr sanitization remains a launch blocker. Saved source session
and timestamp are provenance context, not a globally unique event identifier.

## Security direction and competitive research — 2026-10-02

The owner asked whether comparable products exist and authorized improvements
that make Ghost competitive as a pre-deployment security tool. Primary sources
show substantial overlap:

- [Ghost Security](https://ghostsecurity.ai/) already markets security agents and
  [AppSec tools](https://github.com/ghostsecurity). This creates a concrete naming
  and positioning overlap to review with the owner before launch. No trademark
  conclusion or automatic rename is implied.

- [Semgrep Agentic Workflows](https://semgrep.dev/products/semgrep-agentic-workflows/)
  advertises detection, dynamic validation, triage, and fixes. Its
  [workflow documentation](https://semgrep.dev/docs/workflows/overview) describes
  IDOR/authorization workflows and combining deterministic tools with agents.
- [Shannon](https://github.com/KeygraphHQ/shannon) describes source analysis and
  executable exploit validation for web applications and APIs.
- [Snyk CLI](https://snyk.io/platform/snyk-cli/) covers local and CI security checks;
  [its remediation-agent announcement](https://snyk.io/blog/snyk-remediation-agent-in-the-cli/)
  describes terminal-based dependency remediation.
- [Aikido](https://www.aikido.dev/blog/ai-pentesting-agent-security) documents
  enforced target scope and agent isolation. Its
  [local scanner](https://www.aikido.dev/code/local-scanner) also addresses local
  operation, so local-first execution alone is not a unique differentiator.

These are vendor-described capabilities, not an independently executed comparison.
Ghost must earn comparative claims through shared fixtures, measured false
positives, reproduced vulnerabilities, legitimate-behavior regression tests,
resource budgets, and privacy/scope checks. No superiority claim is supported yet.

### Shipped security foundation

- Added `ghost audit` and `ghost findings`, including JSON, finding-ID inspection,
  REPL help/dispatch, bounded terminal cards, and explicit coverage/evidence labels.
- Uses Bandit's established Python rules with no model/API key. Source is copied
  into a disposable bounded snapshot and scanned under OS confinement. Python
  isolated mode prevents project modules/sitecustomize from being imported.
  Project scanner configuration and nosec comments cannot silently suppress findings.
- Persisted findings contain rule/CWE, source location/hash, severity, scanner
  confidence/version, and the static/suspected evidence state. Raw code excerpts
  and issue messages that may contain password literals are not persisted.
- Missing/unsafe source reads, malformed reports, skipped scanner accounting,
  syntax errors, disabled sandbox, timeout, output limits, and detected source
  changes cannot produce a completed passing result. Other languages are explicitly
  outside the Python scope. No targets are contacted and no fixes are applied.

Verification so far: focused audit/architecture suite **28 passed in 29.60s**,
including six vulnerable/safe rule pairs (evaluation, pickle, YAML, shell execution,
weak hashing, and TLS verification), adversarial source/config cases, CLI/REPL
integration, private-literal omission, and 24/40/80-column rendering. This is a
regression suite for Ghost's behavior, not a benchmark win over competing engines.

Final verification:

- Full suite: **220 passed in 209.97s** before the final concurrent-runtime-artifact
  guard. The final audit/architecture suite then passed **29 tests in 33.72s**,
  including the added test proving `.ghost` activity does not invalidate source
  inventory. The updated security-first welcome screen passed all **3 brand tests**.
- Built and installed a wheel in a fresh temporary environment. The installed CLI
  detected the evaluation finding, returned 0 after a manual safe replacement,
  and returned 2 for malformed Python. Inspected real 40-column/no-color output
  and a PTY session running `audit`, `findings`, and `help audit` without losing
  the REPL on the findings exit code. Rebuilt the wheel after the final changes.
- Six rule pairs were scanned as source without installing their framework
  dependencies or executing their modules. A malicious source import side effect
  and repository `sitecustomize.py` were not executed. Secret-literal omission
  and persisted JSON round trips passed. Existing isolated debugging integration
  scenarios passed in the full suite. Linux was not exercised in this pass.
- The global editable installation now includes Bandit and the new commands.
  Scanner version used here: Bandit 1.9.4. No package was published.
- Ran the installed command against Ghost's own repository: 80 Python files,
  completed under OS confinement, exit 1 with 436 static candidates (3 medium,
  433 low). Of these, 403 are Bandit B101 assertion findings, largely in tests;
  these counts are not confirmed vulnerabilities. Added severity-first ordering
  and severity totals so higher-risk candidates are not buried in the first
  20 cards. Context-aware triage remains a concrete product gap.
- After the final ordering/UI changes, audit/architecture/brand checks passed
  **33 tests in 31.75s**. Rebuilt/reinstalled the final wheel and exercised piped
  REPL audit/findings/exit, confirming the security welcome shortcut, severity
  totals, successful exit, and no ANSI output. Compilation and whitespace checks
  passed.

### Next security milestones

1. Expand authorized local application contracts beyond one GET path and actor
   pair, retaining legitimate access checks and measuring false negatives.
2. Connect security findings to isolated investigation and patch verification with
   separate suspected/reproduced/fix-verified states; never promote static evidence.
3. Expand language/dependency coverage based on an explicit supported-stack policy,
   and measure recall/false positives/cost on a versioned benchmark before marketing
   comparative accuracy. Existing providers' breadth exceeds this first Python pass.
4. Continue UI/CLI improvements and execution/privacy hardening under the existing
   architecture boundaries. Audits should become a first-class recurring priority.

## Remaining launch blockers, in priority order

1. **Private data and model boundaries.** Credential-path exclusions and heuristic request blocking are now covered, but are not complete secret detection. Add configurable policy, broader secret/encoded-value coverage, local output/history handling, provider-independent deadline enforcement, and adversarial prompt-injection tests. Short/unrecognized/transformed secrets may still leave the machine; raw Git evidence and sandbox snapshots are not scrubbed. The OS sandbox permits broad reads needed by runtimes. Review credential access before claiming hostile-repository containment.
2. **Patch application durability.** Add crash recovery and durable transaction journaling before enabling multi-file application. Sync directory metadata for power-loss guarantees, recover orphaned staging files, and preserve ACLs/extended attributes/ownership where supported. Single-file staging, permission bits, CRLF preservation, and preparation-time conflict checks are now covered. A concurrent replacement/delete after the final check remains a race; coordinate writers or use stronger platform-specific primitives before claiming atomic compare-and-swap.
3. **Evidence integrity.** Compare normalized failure signatures across control/reversal/repeat runs; detect changed or skipped test coverage. Add multi-file, committed-regression, nondeterministic, missing-dependency, and malicious-output evaluation cases. Persist provenance and failure reasons consistently.
4. **Process and sandbox coverage.** Exercise Linux/bubblewrap in CI. Test detached descendants, signal storms, oversized/binary output, and sandbox backend failure. Process groups do not provide complete containment of deliberately detached descendants on every platform.
5. **Persistence and concurrency.** Investigation exclusion for one checkout is now covered by an OS lock. Add crash recovery, database schema migrations, interrupted-run recovery, and cleanup diagnostics for orphaned worktrees; OS lock release alone does not recover those artifacts. Extend coverage of overlapping watch/run/debug processes, linked checkouts, and filesystem/platform locking behavior.
6. **Packaging and release gates.** Add supported-platform CI, reproducible package builds, clean-install smoke tests, dependency review, and release/versioning documentation. Choose a license with the owner before distribution terms are advertised.
7. **Terminal polish and accessibility.** Test resizing, very narrow terminals, long editable commands with macOS readline/libedit, color contrast, and reduced motion. Extend literal metadata handling beyond session/history/saved-report views and sanitize control sequences from live command output without breaking useful test output. Expand consistent actionable empty/error states beyond session browsing.

## Working rules for later passes

- Read current Git state and this document before choosing work; avoid repeating completed fixes. The hourly automation is paused; work resumes on direct request.
- Reproduce a concrete failure or unmet requirement, implement a coherent change, then add meaningful regression coverage.
- Run the affected end-to-end path. Broaden testing for changes to execution, isolation, persistence, or patch application.
- Record the exact checks performed and distinguish platform behavior actually tested from code paths only reviewed.
- Do not label Ghost production-ready while blockers remain. Review and commit completed, verified improvements, then push to the existing GitHub origin without force. The owner authorized GitHub pushes for this manual work. Preserve unrelated user changes and exclude secrets and runtime artifacts. Package releases still require separate authorization.
