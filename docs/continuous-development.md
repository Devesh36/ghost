# Continuous development of Ghost

The requested cadence is **one development checkpoint every ten minutes**.
Each cycle chooses the next concrete issue, implements a focused improvement,
verifies it, records the outcome, and pushes validated work to `main`.

**Execution status as of 22 October 2026:** development runs during active Codex
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

## 21 October checkpoint

Recent demo setup failures made installation and graph-runtime diagnosis the
focused task for this cycle. Added opt-in `doctor --graph`, native-runtime
startup/shutdown checks with `--embedded`, distinct connection/authentication/
missing-module guidance, and the running Python/source/PATH command details.
The acceptance criterion is to distinguish ordinary Redis from FalkorDB without
loading or changing graph data. Real native tests cover both server types and
verify empty graph/key state and child-process cleanup. Query execution and
query ACLs remain outside this diagnostic; the demo verifies that separately.
This does not close the historical storage/cancellation issue below.

Local Linux qualification passed 141 focused diagnostic, native graph, CLI/REPL,
architecture and home/picker tests. A wheel installed outside the checkout
passed the native check and reported a real unavailable-port failure as JSON.
Website type/build checks passed. Graph CI includes the new checks on its
existing Linux/macOS jobs; these local results do not claim hosted macOS success.

## 21 October core-review checkpoint

The owner redirected the next cycle toward core Ghost behavior. Extended
GJS004 to detect Node's process-wide TLS-verification bypass, including the
tested Node process/env bindings, while retaining suspected/static evidence.
The same confined scanner improved from 1 to 91 detected candidates in a
161-file independent corpus, with zero matches in its 70 negative cases before
and after. This measurement is scoped to those fixtures; it does not close
the storage/cancellation investigation or establish application exploitability.

## Next work

The 22 October feature cycle adds Ghost Challenge: explicit Python regression
cases must reject original code and accept its proposal, then repeat both
observations in fresh confined snapshots. A synthetic demo distinguishes a
blind passing test from a useful regression. Attempts preserve prior evidence;
they neither certify security nor close the historical storage issue. Next
extensions should qualify more runner forms and realistic application-level
contracts before broadening its scope or making competitive novelty claims.

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


## 24 October repair-evidence checkpoint

Added `ghost challenge --report` for a reviewable Markdown account of the
latest saved challenge. New attempts record a patch digest; export checks source
and proposal identity, all four stages, case inventories, repeated failures and
count consistency before reporting support. Legacy/missing/inconsistent evidence
exports as inconclusive. The report omits source bodies, raw logs and arbitrary
notes, escapes metadata, and explicitly describes historical unsigned local
evidence rather than a current-source or security certification. No dependency,
model call or database migration was added. README, website docs and Phases now
include the command. Narrow REPL help spacing and the demo description were also
corrected after the full suite exposed two presentation regressions.

Validation on Linux, Python 3.12.14:

- Full suite with OS confinement enabled and a temporary child-process reaper:
  **1,355 passed, 2 failed, 21 skipped** in 413.27 seconds. The two failures were
  the narrow-help height and demo-help description; both were corrected and
  passed `pytest --last-failed`. The 49 report/demo/branding tests also passed
  together after the fixes, including 28 new evidence-report tests.
- All 21 opt-in graph tests ran separately against native disposable FalkorDB:
  **8 embedded + 13 TCP integration passed**. The real embedded JSON demo passed.
- Existing Challenge/architecture checks: **46 passed**. Command-picker/home/
  branding checks: **54 passed**. Packaging/architecture checks: **34 passed**.
- Website type checking and production build passed. Built the source archive
  and wheel; installed the wheel into a fresh base-only environment, outside
  the checkout, then ran the real Challenge demo and Markdown export. The
  sample source remained unchanged. No model was called.

These results cover the local checks, not hosted macOS CI or live-model accuracy.
They do not establish that historical storage/cancellation issues cannot recur.
Development remains active-session work; no unattended scheduler was installed.
