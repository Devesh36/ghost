# Repair application: tested bytes and a final source check

Both recipe and LLM security proposals now record `source_snapshot_sha256` and
`patch_sha256`. The source fingerprint is captured from the original bounded
worktree **before** tests or candidate edits. Verification compares the developer
checkout with that fingerprint before declaring a result verified/tested. It
does not simply fingerprint whatever source happens to exist after testing.

This protects proposals with or without Ghost Challenge. The existing explicit
approval, solver status, source/HEAD and Challenge gates still apply. LLM tests
remain evidence about selected behavior, not an independent security proof.

## Installation checks

1. Require the saved patch and source fingerprints; compare the current bounded
   snapshot and HEAD before calling the writer.
2. Prepare the single-file candidate in a newly created exclusive temporary file
   beside the target, flush its bytes and preserve the intended file mode.
3. Recheck proposal identity, snapshot bytes and HEAD inside the writer immediately
   before installation. Exclude only that writer's exact owned staging path from
   the inventory, never every file with a matching prefix.
4. Recheck pinned directory attachment, validate the staged candidate's bytes/mode,
   recheck target identity, and install using the existing single-file operations.

If a check refuses the operation, the original target is not replaced. The writer
removes its staging file and cleans empty directories that it created, preserving
files an editor created meanwhile. A new file, changed test, changed HEAD,
Git-hidden edit, altered proposal or corrupted staging file cannot qualify in
the tested refusal cases. Snapshot reads retain their no-symlink traversal and
file/count/total-byte budgets. The inventory still excludes ignored and sensitive
paths; this is not a capture of the whole filesystem or dependency environment.

## Old proposals and retrying

Historical records remain readable with `ghost solution --json` and the existing
Challenge report commands. They cannot authorize installation if their new solver
fingerprints are absent. Rerun the review and solve against your current source:

```bash
ghost find
ghost solve <finding-id> --tests "python -m unittest test_existing_behavior"
```

Use your own tests. Retain `--llm` if you intentionally want a model proposal;
existing source-sharing and model approval rules still apply. A rejected apply
does not automatically run a model or retry installation. Review the new proposal
before approving it, and rerun Challenge separately if you use that workflow.

## Remaining writer limits

These are optimistic checks, **not a filesystem compare-and-swap**. A writer that
does not cooperate with Ghost can still change another file after the snapshot
check or race the target's final check and rename/unlink. The change narrows the
window and catches the tested intervening edits; it does not eliminate the window,
lock out other editors, or make multi-file changes atomic. Broad transactional
protection would need a separately designed cooperating writer/checkout protocol.

Local records and tests remain trusted. Hashes do not authenticate a person or
prevent someone deliberately rewriting all evidence. The hardening applies to
recipe/LLM security repair application, not a claim that every debugging workflow,
external tool or production filesystem has the same guarantees.
