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


## 25 October Challenge application checkpoint

First reran the final 24 October code (`6e781e4`) as one aggregate suite with
both native FalkorDB test modes enabled: **1,378 passed, zero failures/errors/
skips** in 408.22 seconds. This closes the earlier aggregate-validation gap;
it does not establish production readiness or close unreproduced historical
storage/cancellation issues.

Then reproduced a local evidence-consistency gap in both application paths:
an altered proposal could reuse an earlier supported Challenge even though its
report would reject the mismatched patch fingerprint. Recipe and LLM application
now share the report validator before any source write. Missing patch identities,
incomplete controls and inconsistent case evidence require a fresh challenge.
Existing unchallenged proposals retain their prior gates, while a newer failed
or inconclusive attempt cannot fall back to an older supported one. Local records
remain trusted inputs, not cryptographically authenticated attestations.

Final validation on Linux/Python 3.12.14 with OS confinement enabled:

- Two synthetic altered-patch reproductions failed before the fix and passed
  afterward. Twenty new application regressions cover recipe/LLM paths, source
  and saved-record preservation, legacy/inconsistent evidence, latest-attempt
  precedence, unchallenged compatibility and changes at the CLI display boundary.
- Focused Challenge/application/report/architecture group: **94 passed**.
- Final aggregate suite, including embedded and TCP native FalkorDB checks:
  **1,398 passed, zero failures/errors/skips** in 433.34 seconds. The temporary
  child-process reaper and graph test server were outside the repository.
- Website type checking and production build passed. Source archive and wheel
  built. The installed wheel, outside the checkout, completed the real Challenge
  demo, report export and explicitly approved supported application.
- Installer syntax and version validation passed. Baseline clean-install checks
  also exercised the real confined scanner and security repair demo.

GitHub Actions lookup (`gh run list` for this repository) was denied with
`Forbidden` at `api.github.com`; hosted CI remains unknown and was not bypassed.
macOS, live-model quality and production/hardware behavior are not established by
these local checks. No release, tag, unattended scheduler or separate deployment
was created. Regression watch and broader accuracy evaluations remain future work.


## 25 October adversarial snapshot review

Reviewed `c2faef4` for altered proposals, missing evidence, changed source/HEAD,
path containment, symlink swaps and refusal before the patch writer. A concrete
freshness gap reproduced in both recipe and LLM paths: Git `assume-unchanged` and
`skip-worktree` could hide edits after a supported Challenge from the existing
Git-based signature. All four initial hidden-edit reproductions failed on the
reviewed code and passed after the fix.

New Challenge records fingerprint the actual bounded snapshot's sorted paths
and byte hashes. Challenge rechecks the snapshot after its final stage, and
application compares current snapshot bytes before entering the writer. A missing
legacy fingerprint requires a new Challenge; historical records remain readable.
Existing no-follow snapshot reads reject unsafe/unreadable content. No dependency
or database migration was added. This is a consistency check, not a signed
attestation or a filesystem-wide transaction.

Final Linux/Python 3.12.14 results:

- **29 new adversarial tests passed**, covering hidden source/test edits, normal
  edits, new files, changed HEAD, missing fingerprints, protected/absolute/
  traversing patch paths, file/parent symlink swaps and an edit after the fourth
  stage. Refusal tests spy on the write boundary and check source/record
  preservation. Existing patch-writer tests also exercise staging failures,
  hardlinks and intervening editor/parent-directory changes.
- **116 affected checks passed**, including the four original reproductions,
  Challenge/application/report checks and the patch writer regressions.
- Final aggregate with both native FalkorDB modes and OS confinement enabled:
  **1,427 passed, zero failures/errors/skips** in 471.73 seconds.
- Website type checking/build and source/wheel builds passed. The installed wheel
  outside the checkout completed the real demo, exported the snapshot fingerprint
  and applied a fresh supported repair only with explicit approval.

Limits: the new byte fingerprint covers Challenge execution through application;
initial proposal freshness and unchallenged paths still use their existing
Git-based checks. Arbitrary concurrent edits can still race the final check/
install boundary; the writer is not a filesystem compare-and-swap. Deliberately
rewritten local records are outside the trust model. No new path escape was
observed in the tested cases; this is not exhaustive security or production
verification. Hosted CI remains unknown after the earlier Forbidden response;
no retry or bypass, release, tag or separate deployment was performed.


## 25 October bounded pre-install hardening

Closed the documented unchallenged-proposal freshness gap and narrowed the
check/install window for recipe/LLM security repairs. Each new solver proposal
records its original tested snapshot and final patch fingerprint; completion,
Challenge startup and application reject mismatches. The single-file writer
rechecks the bounded snapshot, patch identity and HEAD after staging, omitting
only its own exact temporary path. It also validates staged bytes/mode and retains
the pinned-directory and final-target checks. Refusal removes owned staging state
without overwriting developer edits. Older proposals remain readable but require
a new solve to acquire the missing evidence. No dependency or SQL migration was
added. This remains optimistic single-file installation, not an atomic multi-file
transaction or a guarantee against non-cooperating writers after the final check.
See [repair application](repair-application.md) for the boundary and retry steps.

Validation on Linux/Python 3.12.14:

- Six initial reproductions failed on the preceding code: hidden unchallenged
  edits, target edits just before writer entry, and test edits during staging,
  for both recipe and LLM paths. All six passed after hardening.
- **32 new guard tests** cover hidden edits, late edits, changed HEAD/proposal,
  missing evidence, staged bytes/mode/deletion, exact temporary-path exclusion,
  create/replace/delete refusal cleanup, and real solver source changes during
  verification. The focused final selection passed **80 tests** (one unrelated
  demo test deselected there and included in the full suite).
- An initial broader check caught two preflight status-label regressions. They
  were corrected and the final aggregate, including native FalkorDB modes and
  OS confinement, passed **1,459 tests with zero failures/errors/skips** in
  484.11 seconds.
- Website type/build checks and source/wheel builds passed. An installed-wheel
  smoke outside the checkout exercised real solver fingerprint generation,
  unchallenged hidden-edit refusal, source preservation and approved application.

Separate concurrency lead (not changed in this increment): supplied independent
CI evidence reports `c2faef4` failing
`test_simultaneous_legacy_startup_migrates_once_and_retains_all_writes` with
`sqlite3.OperationalError: database is locked` at
`infrastructure/database/repository.py:24`, `PRAGMA journal_mode=WAL`:
[failed hosted job](https://github.com/Devesh36/ghost/actions/runs/40169436067/job/121097102582).
The same test passed **10/10 isolated local repetitions** here. This does not
establish that the intermittent failure is fixed; database code is unchanged.

The coordinator also supplied green hosted results for the earlier `3834fc2`:
[Release checks](https://github.com/Devesh36/ghost/actions/runs/40170450983),
[Frontend](https://github.com/Devesh36/ghost/actions/runs/40170451114), and
[FalkorDB demo](https://github.com/Devesh36/ghost/actions/runs/40170450971).
Those runs do not cover this increment. No denied CI endpoint was retried or
bypassed. Hosted CI for the new code, macOS behavior of the new code, live-model
quality and production/hardware guarantees remain unverified. No new release,
tag, separate deployment or further development increment was started.
