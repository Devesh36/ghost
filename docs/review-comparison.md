# Follow changes across saved security reviews

Save a review before and after an edit with `ghost find`, then use `ghost compare`.
It compares the latest two saved audits by default, including an incomplete latest
run. It never silently selects an older successful scan.

```bash
ghost audits --limit 5
ghost audits --limit 5 --offset 5
ghost compare
ghost compare --base <base-id> --audit <target-id>
ghost compare --change new --severity HIGH --confidence HIGH
ghost compare --change repeated --group-by file --limit 5
ghost compare --change repeated --group-by file --limit 5 --offset 5
ghost compare --change no-longer-reported --rule B307
ghost compare --json
```

Use IDs or unique prefixes from your own history. `--base` alone selects the
latest target; `--audit` requires `--base`. All options work in the REPL and the
command picker offers the four `--change` choices.

## Browse the result without losing context

| `--change` | Displayed locations |
| --- | --- |
| `new` | Target candidates without a matching base report location. |
| `repeated` | Both reports contain the same rule, path and line. |
| `no-longer-reported` | A base candidate was absent from a target report that scanned that path. |
| `not-compared` | The target did not record the base candidate's source path. |

`--path`, `--rule`, `--severity` and `--confidence` intersect. Severity and
confidence use the target finding when present, or the base finding for a
base-only row. For example, a MEDIUM → HIGH repeated row matches `--severity HIGH`.
Static confidence describes the pattern match; it does not measure exploitability.

`--limit` bounds rows per displayed category. With `--group-by file` or `rule`,
it bounds groups, each with a representative location and full member count.
`--offset` skips matching rows or groups after filtering. Rerun the same command
with the suggested offset to continue. The offset applies separately to each
displayed category; select a single `--change` for a simple sequence of pages.
An empty page offers a return to offset zero, rather than implying there are no
findings. Limits are 1–1,000 and offsets 0–1,000,000.

Full category totals, severity increases, both saved review contexts, baseline
local access counts and coverage warnings stay visible across filters and pages.
Filters never change the exit code. New candidates hidden by a filter still
produce exit 1; incompatible or incomplete coverage still produces exit 2.
Access checks and candidate repair proofs are not included in the static delta.

## Understand repeated and disappearing locations

Matching uses rule, path and line, not a persistent bug identity. A line move
appears as a new location and an absent location. Duplicate candidates remain
separate: equal severity/confidence pairs are retained first, then equal severity,
before pairing remaining rows. This prevents a disappearing duplicate from
changing the apparent severity of a surviving equal-level candidate. Residual
pairing is deterministic, but cannot establish which underlying issue survived.

Repeated rows identify whether their **saved whole-file SHA-256 hashes** differ.
The inventory summary counts unchanged, changed, added and removed source paths.
Neither observation reads current source. Changed bytes can be unrelated to the
reported line; identical bytes do not establish the same bug or runtime behavior.
Use `ghost freshness` to inspect current source explicitly.

A disappearance is never a verified fix. Compatible comparisons need completed,
confined static scans with consistent source hashes and scanner identity,
version, scope and recorded configuration. Missing fingerprints, inventory
changes or unknown severity transitions limit the result. Invalid evidence,
incomplete scans and incompatible scanners/configuration block a delta verdict.
Both saved review contexts remain available even when no locations can be compared.

## Export and inspect the underlying evidence

`ghost compare --json` retains all four complete location arrays, original
summary keys, notes and exit policy. Additive fields include `base_review`,
`target_review`, `source_inventory` and each location's `source_changed` value
(`true`, `false`, or `null` for an unpaired/unknown identity). A blocked comparison
has no source-inventory delta. JSON cannot be combined with display filters,
grouping or a nonzero comparison offset; `--limit` still does not truncate it.

`ghost audits --json` keeps its existing array of full saved records. History
`--limit` and `--offset` select the exported page. Terminal history shows its
total and next-page command; page and total come from one read-only database
snapshot. Stable timestamp/ID ordering prevents tied timestamps from shuffling
pages in an unchanged history. New saves can shift numeric offsets between
commands; use explicit audit IDs for repeatable comparisons.

No inspection command runs a scanner, project code or model, changes saved
records, or selects historical evidence for a repair. Inspect exact candidates
using the base/target `ghost findings --audit … --id …` commands printed per row.
Exit 0 describes a comparable saved delta without new locations or severity
increases; existing suspected risks may remain. It does not approve deployment.
