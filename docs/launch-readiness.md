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

## Remaining launch blockers, in priority order

1. **Private data and model boundaries.** Add explicit secret-file exclusions, output redaction, provider-independent deadline enforcement, and adversarial tests for prompt injection and accidental disclosure. Built-in HTTP payload limits and total deadlines are now covered; outgoing evidence still needs secret filtering. The OS sandbox currently permits broad reads needed by runtimes. Review access to credential files before claiming hostile-repository containment.
2. **Patch application durability.** Make application atomic or recoverable across multiple edits. Test partial write failures, symlink races, and concurrent editors. Preserve file modes and intentional line endings.
3. **Evidence integrity.** Compare normalized failure signatures across control/reversal/repeat runs; detect changed or skipped test coverage. Add multi-file, committed-regression, nondeterministic, missing-dependency, and malicious-output evaluation cases. Persist provenance and failure reasons consistently.
4. **Process and sandbox coverage.** Exercise Linux/bubblewrap in CI. Test detached descendants, signal storms, oversized/binary output, and sandbox backend failure. Process groups do not provide complete containment of deliberately detached descendants on every platform.
5. **Persistence and concurrency.** Add investigation locking, crash recovery, database schema migrations, interrupted-run recovery, and cleanup diagnostics for orphaned worktrees. Verify overlapping watch/run/debug processes.
6. **Packaging and release gates.** Add supported-platform CI, reproducible package builds, clean-install smoke tests, dependency review, and release/versioning documentation. Choose a license with the owner before distribution terms are advertised.
7. **Terminal polish and accessibility.** Test resizing, very narrow terminals, long editable commands with macOS readline/libedit, color contrast, and reduced motion. Sanitize control sequences from untrusted output without breaking useful test output. Add consistent actionable empty/error states.

## Working rules for later passes

- Read current Git state and this document before choosing work; avoid repeating completed fixes.
- Reproduce a concrete failure or unmet requirement, implement a coherent change, then add meaningful regression coverage.
- Run the affected end-to-end path. Broaden testing for changes to execution, isolation, persistence, or patch application.
- Record the exact checks performed and distinguish platform behavior actually tested from code paths only reviewed.
- Do not label Ghost production-ready while blockers remain. Review and commit completed, verified improvements, then push to the existing GitHub origin without force. The owner authorized GitHub pushes for hourly improvements. Preserve unrelated user changes and exclude secrets and runtime artifacts. Package releases still require separate authorization.
