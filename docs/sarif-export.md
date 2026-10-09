# Export a saved review as SARIF

Use Ghost's saved static findings in tools that accept SARIF 2.1.0:

```bash
ghost sarif > review.sarif
ghost sarif --audit AUDIT_ID > historical-review.sarif
```

Select a real full ID or unique prefix from `ghost audits --json`. Without
`--audit`, Ghost exports the latest saved review, including an incomplete one.
The same command is available as `/sarif` in the REPL. For file redirection,
use the standalone CLI: shell redirection is not a REPL feature.

The command reads local saved records. It does not scan, read current project
source, run tests, request a model response or upload anything. It exports every
static candidate and preserves duplicates. Successful export exits 0 even for
an incomplete review; no saved review exits 1; invalid selection, records or
unsafe paths exit 2. Errors go to stderr with no partial JSON on stdout. Check
the exit status before importing a redirected file: the shell can create or
truncate that file even when the export fails.

## What the file means

Each SARIF result is a `review` of a **suspected** static pattern. HIGH maps to
`error`, MEDIUM to `warning`, LOW to `note`, and UNDEFINED to `none`. These levels
are scan severity, not evidence that an application is exploitable. Static
confidence and CWE, when recorded, are separate result properties.

The Ghost driver identifies the exporter version. Run properties identify the
saved audit, base commit, source scope, aggregate scanner/configuration identity
and selected per-engine provenance. `exportFormatVersion: 1` versions Ghost's
custom property contract within SARIF 2.1.0; future incompatible property changes
must change that value. Existing JSON and Markdown exports retain their formats.

Artifact locations are percent-encoded repository-relative URIs, with recorded
source SHA-256 hashes where available. Absolute, traversal, backslash-separated
and invalid Unicode paths fail export. Result locations identify the saved
line, not the current line after edits. Result `findingId` preserves Ghost's
stored identity; `ghost/source-location/v1` partial fingerprints derive from
rule, path, line and recorded source hash. Line moves or source edits change that
fingerprint; it is not a cross-revision bug identity. Identical duplicate
locations retain separate results with their original finding IDs.

## Coverage and sharing

Run properties retain review status, unsupported/excluded counts and content-free
coverage warnings. The invocation describes the recorded static execution:
`executionSuccessful` is false for an incomplete or unconfined review or an
incomplete recorded static engine. Missing provenance and mismatched source
hashes also receive warnings. Neither a valid export nor a completed scan proves
that the whole application is secure. Resolve raw diagnostic notes with
`ghost findings --audit AUDIT_ID`; raw notes are omitted from SARIF.

Configured authorization proofs and candidate repair results are **omitted**
from static SARIF results. Their counts remain in
`authorizationResultsOmitted` and `authorizationCandidateResultsOmitted`.
Inspect their saved evidence in Ghost before making an access or repair decision.

Exports omit source excerpts, scanner message text, command logs, session
context, authorization request/response data and raw diagnostic notes. Generic
rule messages describe only the static evidence. Paths, hashes, audit/finding
IDs, scope and scanner metadata still require review before sharing; this is
not arbitrary-secret redaction. Ghost does not configure an upload workflow or
promise compatibility with every SARIF consumer. Consumers must retain coverage
warnings and the suspected evidence state when displaying the report.
