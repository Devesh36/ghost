# Reproducible security evaluation

The goal is to measure what Ghost detects, what its bounded recipe can repair,
and whether its evidence gate rejects inadequate tests and incorrect proposals.
Run the same independently authored synthetic cases before and after a change:

```bash
uv run --locked ghost evaluate
uv run --locked ghost evaluate --json > /tmp/ghost-evaluation.json
```

An installed `ghost evaluate` also works outside a Git checkout. It needs Git,
Ghost's installed Bandit/Semgrep dependencies and the supported OS confinement
backend (Linux Bubblewrap or macOS sandbox-exec). No API key, model, Docker or
FalkorDB is needed. The command creates disposable repositories under the system
temporary directory, runs selected `unittest` contracts in isolated worktrees,
and removes the fixtures afterwards. It does not scan the current directory,
open its `.ghost` database, or apply changes to your project. It offers no
arbitrary dataset or executable-command option.

`--timeout 30` is the time limit **per scanner or test operation**, not the
total run budget; supported values are 1–120 seconds. Missing confinement,
timeouts and incomplete evidence leave cases unscored. Disabling the sandbox
does not enable an unsafe fallback. Reports identify incomplete cases and safe
error categories without copying exception messages or raw command output.

## The versioned corpus

[`config/security_eval_v1.json`](../config/security_eval_v1.json) contains all
fixture source, expected outcomes and detection rationales. These are synthetic
examples written for Ghost, not examples copied from scanner repositories or
customer code. Detection snippets are statically scanned; their network, shell
and YAML functions are not executed. Executable repair contracts use literals
and the harmless expression `sum([1, 2])`.

| Track | Cases | What is measured |
| --- | ---: | --- |
| Detection | 19 | Target-rule presence on 10 unsafe and 9 safe counterparts: Python evaluation, shell calls, YAML loading, TLS; JS/TS evaluation, dynamic functions, shell calls and TLS. Includes a Python alias case. |
| Recipe repairs | 2 eligible + 1 refusal | Real scan → deterministic solver → original/patched probe → passing baseline tests → rescan. Unsupported `eval(value, {}, {})` must be refused without a patch. |
| Evidence/application | 6 | Seeded proposals → real Challenge → real apply gate, using only disposable source. |

The six evidence controls are:

- A correct literal-parser proposal with a contract that preserves valid input
  and rejects expressions: supported after four repeated original/patched stages,
  then applied to its synthetic fixture.
- The same proposal with a test that passes before and after: not supported,
  application refused.
- A proposal that rejects all input: the valid-input assertion fails, application
  refused.
- A proposal that still evaluates expressions: the security assertion fails,
  application refused.
- A skipped contract and a contract with a deliberate test error: inconclusive,
  application refused. These cases count as successful *gate controls*, not as
  successful repair validation.

The evaluator deliberately seeds the last track's proposals with the status
needed to reach Challenge. It is testing those gates, not claiming the solver
produced or verified those proposals. This fixed set is **not** an automatic
mutation-testing engine, live-model evaluation or proof of test sufficiency.

## Reading the result

Detection uses one expected rule per file. A true positive means that target rule
was found in its unsafe case; a false negative means it was missed. A false
positive means it was found in its safe counterpart. Other rules remain visible
in `matched_rules`, but are not judged against a different rule's ground truth.

- Precision: TP / (TP + FP).
- Recall: TP / (TP + FN).
- False-positive rate: FP / (FP + TN).
- Coverage: scored cases / total cases. Missing observations remain `null` and
  cannot become true negatives. A zero denominator produces a `null` rate.

Recipe success counts only eligible recipe cases. Scope refusals have their own
denominator. Evidence controls report pass/failure/incomplete separately, with
false-support counts, test identities/outcomes, repeated-stage counts and the
application decision. A timed-out or crashed worker is not a successful negative
control merely because application did not happen. Worker failure is distinct
from a deliberately seeded, fully observed unittest error.
Eligible recipe cases need the complete baseline/probe/patched-test/rescan proof
chain to be scored; partial chains or incomplete rescans remain unscored even
if earlier commands completed. Coverage must accompany every success rate.

Exit codes make these distinctions usable in scripts:

| Code | Meaning |
| ---: | --- |
| 0 | Complete; every corpus expectation met. |
| 1 | Complete; measured misses, false matches or workflow gaps remain. |
| 2 | Incomplete execution/coverage or setup failure. |

For example, an exit code of 1 does not mean the JSON file is invalid. Inspect
`summary.complete`, `summary.gaps` and individual cases. Do not use `|| true` to
turn an incomplete run into a passing check. The regression suite checks the
benchmark's accounting and existing behavior; it does not require hiding a known
scanner miss to produce a green benchmark.

## Baseline — 20 November 2026

The [saved Linux baseline](../examples/evaluation/baseline-v1.json) records:

- 9 TP, 0 FP, 9 TN, 1 FN across all 19 detection cases: 100% precision,
  90% recall, 0% false-positive rate **on this corpus**.
- 2/2 eligible recipe repairs and 1/1 unsupported-scope refusal.
- 6/6 evidence/application controls, including both deliberately incorrect
  proposals, with no false support.
- Exit code **1**: Bandit B307 misses the Python `evaluate = eval` alias case.
  Its ground truth remains unsafe; that gap is not relabeled or suppressed.

JSON records the corpus SHA-256, an implementation SHA-256 over Ghost's bundled
`core`, `infrastructure` and `config` Python/JSON/YAML files, Ghost/Python/platform
versions, per-operation timeout, scanner versions and configuration hashes.
The implementation hash excludes UI code, dependencies, docs and tests; scanner
metadata and the lockfile provide additional comparison context. Compare runs
only after checking these identities. A changed corpus needs a new version and
baseline, not a silent rewrite of historical expectations.

The existing Bandit configuration hash also includes its worker's installation
path, so an editable checkout and an installed wheel can have different scanner
hashes with the same code and outcomes. This baseline preserves that actual hash;
it does not normalize away differences in saved scanner evidence. The installed
wheel smoke run matched the corpus/implementation hashes and every case outcome,
with that installation-path difference recorded separately.

This small regression corpus is a starting point, not a representative estimate
of production vulnerability detection, exploitability, live-model repair quality,
or competitive superiority. It tests Python recipes only. Follow-up work should
expand independently labeled application-level cases and address measured gaps;
targeted mutation testing can then test stronger contracts against more wrong fixes.
