# Check a saved review against current source

Saved findings describe the bytes reviewed at the time of the scan. Inspect their
current identity explicitly, without running another scan:

```bash
ghost freshness
ghost freshness --audit <audit-id>
ghost freshness --audit <audit-id> --json
```

The command works in the REPL and slash picker too. It never imports project
code, calls a model, applies a change, or replaces the saved audit. Default
`findings --json` and `brief` exports keep their existing contents and meaning.

| File state | Meaning |
| --- | --- |
| `unchanged` | Current SHA-256 matches the saved static source hash. |
| `changed` | Current bytes differ, even if size and timestamps are unchanged. |
| `missing` | Source no longer exists at the recorded path. |
| `unreadable` | A permission or other read failure prevented inspection. |
| `unsafe` | The path is excluded, traverses a symlink, is not a regular file, or exceeds the per-file size bound. |
| `unknown` | A trustworthy source hash was not recorded, or finding and file hashes disagree. |
| `unchecked` | The inspection count or aggregate byte budget was reached. |

The report also checks HEAD and whether the Git-visible inventory stayed stable
during inspection. Python and JS/TS paths absent from the saved snapshot are
listed as **unreviewed**; they may be newly added or have been outside that
earlier engine's coverage. Ignored paths are not enumerated. Missing Git metadata
and source changes during inspection cannot produce a matching result.

Inspection is bounded to 2,000 recorded paths, 512,000 bytes per source file and
32,000,000 aggregate source bytes. The aggregate guard conservatively reserves
a full per-file allowance (plus the overflow-detection byte) before each read;
failed reads consume that reserved allowance. `--limit` controls displayed paths,
not which recorded paths are checked; JSON includes every state and full counts.
It exports metadata only, with fixed diagnostic descriptions rather than source
text or raw filesystem errors. Review paths and audit IDs before sharing.

Exit **0** means a completed saved review's recorded static source and commit
match, with stable inventory and no unreviewed supported paths. Exit **2** means
stale or inconclusive source observations, or originally incomplete coverage.
Exit **1** means there is no saved review. Selector and inspection errors are
reported on stderr when exporting JSON.

A matching result is a point-in-time source observation, not a new scan, verified
fix or security approval. It does not revalidate scanner versions/rules, AI
advisories, authorization evidence, ignored files or other languages. There is
no atomic snapshot across files; keep the project quiet while inspecting and
rerun `ghost find` to create current evidence after edits or upgrades.
