# Ghost launch readiness

Release status: **more hardening is required before a production launch**.

This document is the handoff for the hourly improvement pass. Keep work bounded, preserve user changes, test behavior before marking an item complete, commit and push verified improvements to GitHub, and leave release decisions to the owner.

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

## Remaining launch blockers, in priority order

1. **Private data and model boundaries.** Credential-path exclusions and heuristic request blocking are now covered, but are not complete secret detection. Add configurable policy, broader secret/encoded-value coverage, local output/history handling, provider-independent deadline enforcement, and adversarial prompt-injection tests. Short/unrecognized/transformed secrets may still leave the machine; raw Git evidence and sandbox snapshots are not scrubbed. The OS sandbox permits broad reads needed by runtimes. Review credential access before claiming hostile-repository containment.
2. **Patch application durability.** Add crash recovery and durable transaction journaling before enabling multi-file application. Sync directory metadata for power-loss guarantees, recover orphaned staging files, and preserve ACLs/extended attributes/ownership where supported. Single-file staging, permission bits, CRLF preservation, and preparation-time conflict checks are now covered. A concurrent replacement/delete after the final check remains a race; coordinate writers or use stronger platform-specific primitives before claiming atomic compare-and-swap.
3. **Evidence integrity.** Compare normalized failure signatures across control/reversal/repeat runs; detect changed or skipped test coverage. Add multi-file, committed-regression, nondeterministic, missing-dependency, and malicious-output evaluation cases. Persist provenance and failure reasons consistently.
4. **Process and sandbox coverage.** Exercise Linux/bubblewrap in CI. Test detached descendants, signal storms, oversized/binary output, and sandbox backend failure. Process groups do not provide complete containment of deliberately detached descendants on every platform.
5. **Persistence and concurrency.** Investigation exclusion for one checkout is now covered by an OS lock. Add crash recovery, database schema migrations, interrupted-run recovery, and cleanup diagnostics for orphaned worktrees; OS lock release alone does not recover those artifacts. Extend coverage of overlapping watch/run/debug processes, linked checkouts, and filesystem/platform locking behavior.
6. **Packaging and release gates.** Add supported-platform CI, reproducible package builds, clean-install smoke tests, dependency review, and release/versioning documentation. Choose a license with the owner before distribution terms are advertised.
7. **Terminal polish and accessibility.** Test resizing, very narrow terminals, long editable commands with macOS readline/libedit, color contrast, and reduced motion. Extend literal metadata handling beyond session/history/saved-report views and sanitize control sequences from live command output without breaking useful test output. Expand consistent actionable empty/error states beyond session browsing.

## Working rules for later passes

- Read current Git state and this document before choosing work; avoid repeating completed fixes.
- Reproduce a concrete failure or unmet requirement, implement a coherent change, then add meaningful regression coverage.
- Run the affected end-to-end path. Broaden testing for changes to execution, isolation, persistence, or patch application.
- Record the exact checks performed and distinguish platform behavior actually tested from code paths only reviewed.
- Do not label Ghost production-ready while blockers remain. Review and commit completed, verified improvements, then push to the existing GitHub origin without force. The owner authorized GitHub pushes for hourly improvements. Preserve unrelated user changes and exclude secrets and runtime artifacts. Package releases still require separate authorization.
