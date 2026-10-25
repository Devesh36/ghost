# Ghost Challenge: try to disprove a repair

A passing suite can be blind to the behavior a repair is intended to change.
Ghost Challenge asks a narrower, executable question: do these developer-selected
regression cases reject the original code and accept the proposed repair?

Try a real, self-contained example with no model or FalkorDB dependency:

```bash
ghost demo --challenge
```

The synthetic configuration importer accepts literal values but originally also
evaluates function calls. Its ordinary literal test passes on both implementations.
Challenge reports that this test does **not support** the repair. A separate
regression test requires function-call input to be rejected; it fails on the
original, passes on the repair, and repeats both results in fresh snapshots.
The demo creates and removes its own repository. `--keep` retains the sample
and saved records. It applies no patch and changes no developer source.

## Use your own regression cases

Write the cases before preparing the proposal, so they are part of its recorded
source identity. Select a normal passing baseline separately from a regression
that intentionally fails on the original implementation:

```bash
ghost find
ghost solve <finding-id> --tests "python -m unittest test_existing_behavior"
# Answer N at the apply prompt to keep the proposal unapplied.
ghost challenge --tests "python -m unittest test_security"
ghost challenge --json
ghost solution --json
```

Replace the modules and finding ID for your project. For an AI proposal, add
`--llm` to `solve`; its ordinary baseline must still pass. Challenge makes no
model request and installs no packages. It uses Ghost's Python interpreter;
install Ghost in the project environment when its tests need project dependencies.
Initial support is one unapplied Python
file from a verified recipe or tested LLM proposal. Use explicit local unittest
module, class or method names; pytest, Node, discovery, filters and subtests
are not supported by Challenge yet. Existing repair runners remain available.

After inspecting the proposal, explicitly request a **new** challenge and apply
only if it supports the repair:

```bash
ghost challenge --tests "python -m unittest test_security" --apply
```

Omitting `--apply` never changes project source. `--apply` without `--tests` is
rejected: a saved positive result is not silently reused to apply a patch.
Application displays the full saved proposal; with `--json --apply`, that
display goes to stderr while the challenge report remains JSON on stdout.
Both recipe and LLM application recheck the latest saved Challenge using the same
consistency checks as `--report`, including the exact patch digest and four
complete runs. A changed patch, incomplete evidence, or a legacy Challenge
without a patch digest cannot authorize application; run a new challenge.
An older supported attempt cannot override a newer inconclusive attempt.
Proposals with no Challenge records retain their existing verification and
explicit-approval requirements. These checks detect inconsistent local records;
they are not signatures or protection against deliberate record rewriting.
Without `--tests`, `ghost challenge` reads the latest saved attempt without
executing code or taking an investigation writer lock. `/challenge` and
`help challenge` provide the same command inside the REPL.

## The four controls

| Fresh snapshot | Required observation |
| --- | --- |
| Original | At least one assertion failure; no runtime errors or skips. |
| Patched | The exact same test identities all pass. |
| Original repeated | The same assertion-failing identities fail again. |
| Patched repeated | The same test inventory all passes again. |

Each stage starts from an independent worktree of the recorded source state.
The host applies the proposal only in patched copies. Tests run under Ghost's
existing OS confinement with a per-stage timeout (default 30 seconds, maximum
120) and a bounded output channel. Ghost checks source/fixture integrity before
and after execution, then removes that stage's worktree. Both original snapshots
contain the same bytes: this is the negative control, not a persistent rollback
in the developer checkout.

The host requires a complete structured unittest inventory, with at most 1,000
cases and 20 explicit selectors. Case identities are hashes; raw test names,
tracebacks, assertion messages and source excerpts are not exported by the
worker. Test output is discarded inside it. Early-stopped suites, duplicate
identities, zero tests, changed inventory, non-assertion failures, skips,
expected failures, subtests, timeouts, unconfined execution, truncated/malformed
reports, source changes and unstable repeated failures cannot qualify.

## Outcomes and saved evidence

- `supported`: all four controls met their requirements for the selected cases.
- `not_supported`: tests also passed on the original, or still failed on the repair.
- `blocked`: a precondition failed before useful execution, such as stale source
  or an unsupported runner.
- `inconclusive`: execution or evidence could not establish the required controls.

Only `supported` exits 0; other completed attempts exit 2. JSON output preserves
the attempt ID, selected command, source/HEAD identity, stages, case hashes and
outcomes, timing and confinement metadata. Attempts are appended to the existing
repair record's new `challenges` list; prior repair checks and findings are not
rewritten. Older repair records load with an empty list; no database migration
or new table is needed. `ghost solution` also reports the latest outcome.

Once a proposal has a challenge, its latest attempt must be complete, supported
and tied to that proposal's source/HEAD before the repair helpers apply it.
Unchallenged legacy proposals keep their existing behavior. A newly generated
proposal has its own evidence; this is not a repository-wide mandatory policy.

## What this establishes—and what it does not

It establishes repeatable discrimination by the **selected regression cases**.
It does not prove that the tests express the right requirement, establish
application reachability/exploitability, eliminate flakiness after two repetitions,
or certify a project secure. Test and application code are trusted executable
inputs: this is not a tamper-resistant certificate against code deliberately
forging or gaming its tests. OS confinement protects the host; it does not make
test assertions trustworthy. Review the cases and diff yourself.

A supported challenge never promotes a static finding to confirmed or an LLM
proposal to security-verified. `--apply` remains explicit developer approval.
No industry-first or competitor-exclusivity claim is made for this mechanism.

## Qualification — 22 October 2026

The local Linux Challenge suite passed 43 cases. Broader overlapping selections
passed 284 repair/workflow/runner/REPL regression checks and 126 Challenge,
evidence-integrity, locking and packaging checks. The explicit-application JSON
path was rechecked for both recipes and LLM proposals after adding the full
proposal display on stderr. Website types and the production build passed.
A clean wheel installed outside the source checkout ran the real demo with no
FalkorDB package installed. The demo makes no model request. Hosted macOS
results are separate from these local checks.


## Export evidence for a code review

After running a challenge, export the latest saved attempt:

```bash
ghost challenge --report > /tmp/ghost-repair-evidence.md
```

The same option is available as `/challenge --report` in the REPL (shell
redirection is a terminal feature, not a REPL command). The Markdown report
contains proposal/audit/finding IDs, the selected test command, base commit,
working-state fingerprint, patch fingerprint, per-stage counts and confinement
checks. It includes unsuccessful attempts too: exit code **0** means the saved
supported record passed the consistency checks; **2** means unsupported,
incomplete/inconsistent evidence or a command error. A report can still be
written with exit code 2. Missing proposals/attempts produce an error on stderr.

`--report` cannot be combined with `--tests`, `--apply` or `--json`. It does not
execute project code, request a model, acquire an investigation writer lock or
apply changes. Existing JSON output remains available separately. Redirect to a
location outside your source checkout, as above, to avoid making a report file
part of the next source fingerprint.

New attempts record SHA-256 over the ordered proposal edit list: UTF-8 JSON,
sorted object keys, ASCII escaping and compact separators. All path, operation,
old and new values contribute to that digest. The export checks this digest,
proposal/source identity, four ordered confined stages, complete case inventory,
matching assertion-failure identities on both original runs, passing patched
runs and accurate recorded counts. Older attempts without a recorded patch hash
remain readable, but their report assessment is inconclusive; run a fresh
challenge to obtain the new evidence.

This is **historical local evidence**, not a signed attestation or a current-source
check. Hashes do not authenticate who ran the tests or protect against someone
rewriting local records. Both the base commit and working-state fingerprint
identify the tested source. A later code change requires a new review/proposal
and challenge. A report after application still describes the tested snapshots,
not a new test of the developer checkout.

Source/patch bodies, raw test output and free-form saved notes are omitted.
Commands, paths and record identifiers remain visible: review the report before
sharing it. Metadata is escaped to prevent Markdown/HTML or terminal-control
injection. The report does not upgrade suspected findings or certify security.
