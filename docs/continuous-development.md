# Continuous development of Ghost

The requested cadence is **one development checkpoint every ten minutes**.
Each cycle chooses the next concrete issue, implements a focused improvement,
verifies it, records the outcome, and pushes validated work to `main`.

**Execution status as of 16 October 2026:** development runs during active Codex
sessions. No recurring-agent scheduler or unattended model credentials are
available in this environment, so no automatic ten-minute coding job has been
installed. GitHub's existing workflows test pushes; they do not choose or
implement future features. This document is a handoff procedure, not a running
scheduler.

## Cycle procedure

1. Inspect `AGENTS.md`, the working tree, current `main`, and the latest evidence
   in the [review schedule](review-improvement-plan.md). Preserve unrelated edits.
2. Choose the highest-value reproducible issue. Define the observed problem and
   one acceptance criterion before changing code. Prefer reliability and review
   accuracy over expanding unsupported capabilities.
3. Implement independently from Ghost's own code and requirements. Add a
   regression for meaningful behavior, and show it fails on the prior behavior
   when practical. Preserve saved evidence and source protections.
4. At the ten-minute checkpoint, report the result or remaining uncertainty.
   If a check is still running, continue it before shipping. Do not overlap
   writers or skip verification to meet the clock; a checkpoint is not a promise
   of a commit every ten minutes.
5. Run focused checks, then the applicable regression suite. Record exact results
   and distinguish local verification from hosted CI. An unresolved failure
   keeps the issue open even if a later rerun passes.
6. Add a dated outcome to the Phases notes using Asia/Kolkata dates, update the
   relevant guide and run `npm run history:update` in `site`. Commit the focused
   change and push it to `main` with normal fast-forward protection. Never force
   push or publish a release as a routine cycle action.
7. Record the next task and any blocking evidence before ending or handing off.

## Next work

| Order | Task | Completion evidence |
| --- | --- | --- |
| 1 | Diagnose the historical cancellation/storage failure | Capture a reproducible failing case with the new sanitized storage reason. Establish the cause before claiming a fix. The recent safe-sidecar diagnostic change does not close it. |
| 2 | Expand security review accuracy cases | Extend independent positive/negative fixtures for a supported rule; report misses and false matches separately and retain suspected-finding semantics. |
| 3 | Verify Graph Hacks rules when available | Read the actual event rules, reconcile dates/reuse/agent criteria with the implementation, and complete the remaining submission checks without inventing eligibility. |
| 4 | Add reviewer decisions after storage investigation | Keep manual notes separate from immutable scanner evidence; require a dismissal reason and detect changed-source applicability. |

For a future supported scheduler, configure this procedure for
`Devesh36/ghost` on `main`, with a ten-minute interval, a single active writer and
authenticated Git access. The scheduler must be separately created and verified;
an interval in a document or a sleeping shell is not unattended agent execution.
Package publication and messages to external parties are separate actions.
