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

## Remaining launch blockers, in priority order

1. **Private data and model boundaries.** Add explicit secret-file exclusions, output redaction, provider-independent deadline enforcement, and adversarial tests for prompt injection and accidental disclosure. Built-in HTTP payload limits and total deadlines are now covered; outgoing evidence still needs secret filtering. The OS sandbox currently permits broad reads needed by runtimes. Review access to credential files before claiming hostile-repository containment.
2. **Patch application durability.** Add crash recovery and durable transaction journaling before enabling multi-file application. Sync directory metadata for power-loss guarantees, recover orphaned staging files, and preserve ACLs/extended attributes/ownership where supported. Single-file staging, permission bits, CRLF preservation, and preparation-time conflict checks are now covered. A concurrent replacement/delete after the final check remains a race; coordinate writers or use stronger platform-specific primitives before claiming atomic compare-and-swap.
3. **Evidence integrity.** Compare normalized failure signatures across control/reversal/repeat runs; detect changed or skipped test coverage. Add multi-file, committed-regression, nondeterministic, missing-dependency, and malicious-output evaluation cases. Persist provenance and failure reasons consistently.
4. **Process and sandbox coverage.** Exercise Linux/bubblewrap in CI. Test detached descendants, signal storms, oversized/binary output, and sandbox backend failure. Process groups do not provide complete containment of deliberately detached descendants on every platform.
5. **Persistence and concurrency.** Add investigation locking, crash recovery, database schema migrations, interrupted-run recovery, and cleanup diagnostics for orphaned worktrees. Verify overlapping watch/run/debug processes.
6. **Packaging and release gates.** Add supported-platform CI, reproducible package builds, clean-install smoke tests, dependency review, and release/versioning documentation. Choose a license with the owner before distribution terms are advertised.
7. **Terminal polish and accessibility.** Test resizing, very narrow terminals, long editable commands with macOS readline/libedit, color contrast, and reduced motion. Extend the session browser's literal metadata handling to other views and sanitize control sequences from command output without breaking useful test output. Expand consistent actionable empty/error states beyond session browsing.

## Working rules for later passes

- Read current Git state and this document before choosing work; avoid repeating completed fixes.
- Reproduce a concrete failure or unmet requirement, implement a coherent change, then add meaningful regression coverage.
- Run the affected end-to-end path. Broaden testing for changes to execution, isolation, persistence, or patch application.
- Record the exact checks performed and distinguish platform behavior actually tested from code paths only reviewed.
- Do not label Ghost production-ready while blockers remain. Review and commit completed, verified improvements, then push to the existing GitHub origin without force. The owner authorized GitHub pushes for hourly improvements. Preserve unrelated user changes and exclude secrets and runtime artifacts. Package releases still require separate authorization.
