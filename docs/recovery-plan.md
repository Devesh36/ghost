# Inspect an interrupted investigation

After an interrupted run, start with a recovery plan:

```bash
ghost recover
ghost recover --json
ghost recover --limit 5
```

The command is also available as `/recover` in the REPL. It reads saved history
and worktree metadata without running project code, importing source, invoking
scanners/models, migrating a database, changing its permissions or deleting paths.
It does not create `.ghost/` or a lock file in a project without local storage.

## Read the plan

- **Saved runs needing review** retain their recorded state. `running` or a missing
  finish time means the record needs inspection, not that its process is alive
  or that it is safe to declare the run completed.
- **Registered, missing, unregistered and unsafe worktrees** come from Git's
  registrations and no-follow inspection of immediate `.ghost/worktrees` children.
  Git lock/prunable flags remain visible. Other checkouts are counted; their paths
  and source are not exported.
- **Recorded snapshot references** connect a snapshot event to an investigation
  ID and session when recorded. New debugger snapshot events include the run ID.
  Older events may provide only a session reference, and individual experiment
  worktrees may have no recorded association. A removed reference can coexist with
  a present path after manual reuse; the last recorded action remains visible.
- **Retain and review** applies to every path, including matched snapshots.
  Historical references do not establish current ownership, process liveness,
  disposable contents or permission to delete.

Use `ghost investigations`, `ghost report --id <investigation-id>` and
`ghost sandboxes --json` to inspect the relevant saved evidence and metadata.
Review paths and IDs before sharing the JSON plan; source, logs, patches,
hypotheses, private notes and raw diagnostics are omitted.

## Lock and database behavior

If an investigation holds the checkout lock, recovery planning stops. An existing
available lock is held for the inspection and released afterward, preserving its
permanent inode. If no lock exists, the plan says `unavailable` and does not create
one. That inspection can overlap a new investigation; the output is an observation,
not permission to perform cleanup. Watchers and command recorders do not hold the
investigation lock and can continue writing history.

History is read with normal SQLite `mode=ro`, a query-only transaction and a
consistent snapshot, so committed WAL evidence remains visible. SQLite can use
or create shared-memory bookkeeping when reading a WAL database; this is not an
evidence update. Existing sidecars must pass ownership, regular-file and no-link
checks. No migration or journal-mode change is requested. An unrecovered hot
rollback journal or an inaccessible/incompatible database can make the plan
incomplete; preserve the data and follow the [database recovery guide](database-upgrades.md).

Unsafe or foreign-owned storage is refused. Existing modes are left unchanged.
The reader verifies named-file identities and keeps
directory handles open, but SQLite still opens named paths; malicious concurrent
replacement by another process with the same user permissions remains outside
these checks.

## Limits and exit status

The history reader bounds sessions, investigation records and agent-action events
to 1,000 rows per category. Each payload is limited to 2 MB and each payload
category to 16 MB. SQL execution has a two-second progress deadline, with a
separate two-second lock wait. Git worktree inspection retains its existing
1,000-entry and 1 MB report limits. `--limit` bounds display only; it never changes
the observations or exit status, and JSON includes the complete bounded plan.

| Exit | Meaning |
| --- | --- |
| 0 | Inspection completed without unfinished records or leftover paths in its observed scope. |
| 1 | Inspection completed and records or paths need manual review. |
| 2 | Planning was blocked, unsafe, incompatible, malformed, changed during inspection or over budget. |

An exit of 0 is not a claim that no descendants remain or that an application is
safe. Invalid or oversized history cannot become a clean partial result. JSON
sets `complete=false` for incomplete inspection, and `cleanup_permitted=false`
for every result.

## Cleanup remains separate

There is no `--apply`, deletion or database-state reconciliation in this command.
Stop Ghost and preserve a private backup before considering manual recovery.
Never remove an unrelated or locked worktree, the real checkout, unknown leftovers
or dirty source based on this plan. Durable per-experiment identity records,
descendant termination evidence and explicit auditable cleanup remain open in
[issue #4](https://github.com/Devesh36/ghost/issues/4) and the
[production improvement plan](production-improvement-plan.md).
