# Reviews and findings improvement schedule

Planning timezone: Asia/Kolkata. Target dates begin on 9 October 2026.
This is a milestone plan; it does not create recurring jobs or execute future work.
Dates are targets, and each milestone needs its acceptance checks before completion.

| Target date | Milestone | Acceptance checks | Status |
| --- | --- | --- | --- |
| 9 October 2026 | Make saved findings easier to triage | File/rule/confidence filters intersect correctly; grouped views retain full totals and access evidence; detail views explain investigation and repair options; compact scanner reports retain every finding within explicit bounds; terminal and real-scan checks pass. | Complete |
| 12 October 2026 | Make source freshness explicit | Opt-in current-source check. Changed, missing, unreadable and unsafe files receive distinct states; reading saved evidence remains available without importing project code or making network requests. | Complete |
| 14 October 2026 | Improve comparisons and review history | Paged history and category/severity/confidence filtering; saved source identity and both review contexts remain visible. Duplicate pairing preserves equal levels before interpreting residual changes. Incomplete or incompatible coverage blocks a delta verdict. | Complete |
| 15 October 2026 | Investigate intermittent storage concurrency failure | Reproduce the observed cancellation/storage failure with sanitized diagnostics and concurrent read/write/cancel fixtures. Preserve ownership/link checks and evidence; a passing rerun alone cannot close the issue. | Planned |
| 16 October 2026 | Graph Hacks: FalkorDB triage demo | Synthetic graph loaded through parameterized writes; FalkorDB computes priority and returns evidence paths. Removing a relationship changes the real recommendation. Existing audits and repairs remain untouched. | Complete |
| 20 October 2026 | Add reviewer notes and decisions | After storage reliability investigation, keep manual decisions separate from immutable scan evidence. A dismissal needs a reason; changed source invalidates its applicability; exports identify evidence and reviewer decision separately. | Planned; gated on storage investigation |
| 19 October 2026 | Expand finding guidance and coverage diagnostics | Review every supported JS/TS rule and common Python finding families. Extend independent positive/negative cases for each supported form. Explain unsupported repairs, parse errors, excluded paths, timeouts and unknown confidence without inventing reachability or exploit proof. | Planned |
| 21 October 2026 | Exercise complete review journeys | Validate first review, incomplete review recovery, grouped triage, historical inspection, supported repair, manual repair and rescan using independent Python/JS fixtures. Include narrow, plain and themed terminals. | Planned |
| 23 October 2026 | Finish documentation and release review | Full regression suite and real scan/repair demo pass; unresolved issues and scanner limits are documented; examples work; owner reviews the resulting change before release. | Planned |

## Evidence for the completed milestone

Validated on 9 October 2026: **881 regression tests passed**, with no failures,
errors or skips. The real mixed-language review, Python repair and rescan demo
passed. A confined 3,000-finding fixture retained every candidate without
exporting source excerpts. Ghost's own scoped review completed both engines
across 156 source files and retained 1,538 static candidates. These scan results
are investigation leads, not proof that each candidate is an applicable defect.

## Working sequence

1. Check coverage with `ghost scope`, then create a saved review with `ghost find`.
2. Use `ghost brief` to check overall coverage and reproduced local access results.
3. Group static candidates with `ghost findings --group-by file` or `--group-by rule`.
4. Narrow the list using `--path`, `--rule`, `--severity` and `--confidence`.
5. Open one real finding ID with `ghost findings --id <id>` and investigate its callers and input boundaries.
6. Use `ghost solve` only to check a supported Python recipe; review manual changes and run project tests otherwise.
7. Use `ghost freshness` to inspect recorded source identities and unreviewed paths without rescanning; rerun `ghost find` after edits, then compare compatible saved reviews.

## Continuous improvement cycle — 12 October 2026

This cycle adds explicit source inspection and expands the Node shell-execution
rule while preserving immutable saved evidence. The independent 179-file
JS/TS corpus contains 115 shell-command candidates and 64 safe or unrelated
neighbors. With the same confined scanner, the old rule detected 3 candidates;
the improved rule detected all 115. Neither configuration matched the 64
negative cases. Tested forms include ESM imports and aliases, CommonJS
bindings, sync/async exec, literal shell options, and shadowed names.

These are bounded pattern-detection measurements, not an application security
accuracy percentage. Dynamic imports, computed methods, indirect aliases and
variable shell options remain outside exhaustive coverage. Existing review
comparisons identify the changed rule configuration and refuse to present a
scope-incompatible disappearance as a verified fix.

Linux qualification passed a full **1,187-test** regression run in 608.70 seconds,
with no failures, errors or skips. Final freshness-only checks passed **37 cases**,
including failed-read byte-budget accounting. The real CLI journey completed a
mixed-language scan, matching-source check, stale-source check after an edit,
immutable historical export, rescan, compatible comparison and unapplied Python
repair. Three baseline and patched unittest cases passed; Python source stayed
unchanged and no model was called. Website types/build and production Chromium
checks at 320, 390, 768 and 1440 pixels passed, including the refreshed captures
and pages without JavaScript.

One earlier qualification attempt encountered an intermittent `StorageError`
in the existing concurrent investigation cancellation test. The isolated case,
95 storage/migration/execution tests, 960 concurrent history reads and final full
run passed. Its underlying cause is not established; keep storage concurrency on
the reliability follow-up queue. No ownership, link or confinement checks were
bypassed. Hosted macOS checks remain separate from this local Linux evidence.

Next cycles retain the comparison/history, reviewer-decision and broader
diagnostic work above. Each cycle must add a reproducible case, improve the
supported behavior, run applicable checks, and update this record. The existing
Linux/macOS regression workflow runs the new fixtures on subsequent pushes;
this work does not install a recurring agent or claim unattended future work.

## Continuous improvement cycle — 14 October 2026

The comparison/history milestone adds `--change`, `--severity`, `--confidence`
and `--offset` browsing while retaining full category totals, exit policy and
coverage warnings. Both saved review contexts and baseline access counts stay
visible even when a comparison is blocked. Repeated locations distinguish saved
whole-file hashes; a source inventory records changed, unchanged, added and
removed paths. These observations never read current source or identify a
persistent bug.

An independent duplicate-location regression found that rank-only pairing could
attribute a disappearing duplicate's severity to a surviving candidate. Equal
severity/confidence pairs, then equal severity, are now preserved first. Unknown
severity transitions still block an ordered escalation verdict; ambiguous
residual pairs remain explicitly described as report-location comparisons.

History pages show the total and next-page command. Count and page selection
share a read-only database snapshot; tied timestamps use stable ID ordering.
Pagination reaches records beyond the former 1,000-record browse cap without
changing saved payloads, default JSON array shape or the latest repair selection.
The guide explains how new saves can shift numeric offsets between commands.

Linux qualification passed **1,214 regression tests** in 608.33 seconds, with
zero failures, errors or skips. Focused comparison/history/triage/freshness
qualification passed 163 cases, including the real edit/rescan/incomplete-scan
journey. A concurrent-save regression pins the history count and page to one
snapshot; a 1,005-record fixture reaches every record across pages. Independent
before/after duplicate cases retain the HIGH, LOW or UNDEFINED survivor's level;
the previous pairing incorrectly labeled the unchanged UNDEFINED survivor as a
partial severity transition. Genuine unknown transitions remain flagged.

The executed gallery now includes stale-source inspection and a compatible
mixed-language rescan comparison. The existing isolated Python recipe passed
three baseline and patched project tests; source was restored after the sample
edit and no model was called. Website types and production build passed.
Chromium checks passed at 320, 390, 768 and 1440 pixels with eight full-resolution
captures, keyboard tabs, no page overflow or browser errors, and documentation
and phases available without JavaScript. Hosted macOS evidence remains separate.

The schedule now brings storage concurrency investigation forward to 15 October,
before reviewer decisions add more persistence work. Later accuracy changes must
extend the independent positive/negative corpus, report missed and unexpected
matches separately, and keep static match confidence distinct from exploit proof.
Release timing remains gated on evidence and the owner's release decision.

## Graph Hacks increment — 16 October 2026

The submission adds an optional local FalkorDB graph and one bounded triage
question, independent of Ghost's SQLite audit/repair history. New Cypher queries
calculate the ranking from package/service, internet-exposure and incident
relationships, then return ownership and evidence paths. The synthetic demo
prioritizes F-002 at 115 points; removing only its incident edge makes F-003 first.
See the [Graph Hacks implementation and new-work record](graph-hacks.md).
All 1,238 regressions passed, including six real-server integration cases. The
final Compose configuration passed 24 focused checks and retained the same
read-only answer after restart; the installed wheel demo also passed outside the
checkout. The setup explicitly starts the database process to honor append-only
persistence rather than relying on the image's startup wrapper.

This requested event feature takes the current increment. The 15 October storage
investigation remains unfinished; the existing intermittent failure is not
considered fixed by passing subsequent tests. Reviewer decisions move to a
20 October target, still gated on that investigation. Graph triage adds no writes
to Ghost's saved evidence database.

## Quality gates for every milestone

- Existing JSON exports and saved evidence retain their meaning and contents.
- Filtering and grouping cannot hide incomplete coverage or baseline access results.
- Static confidence is pattern-match confidence, not application exploitability.
- No automatic source changes, model requests, downloaded scanner rules or external reports are added to inspection commands.
- Project changes receive focused regression checks and the relevant integration tests. Failed checks are diagnosed before a milestone is marked complete.
- Preserve developer source and keep experimental repairs isolated. A verified sample repair does not certify an application secure.

The aim is a dependable, understandable review workflow within Ghost's supported
scope. Remaining language, scanner and repair limitations must stay explicit.
