# Recover after an interrupted repair or investigation

After an interrupted run, start with a recovery plan:

```bash
ghost recover
ghost recover --json
ghost recover --limit 5
ghost recover --archive <exact-workspace-id> --json
```

Without `--archive`, the command is also available as `/recover` in the REPL and reads saved history
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
the observations or exit status, and JSON includes the complete bounded plan. Repair history adds a separate
1,000-record, 2 MB per-record and 16 MB total budget.

| Exit | Meaning |
| --- | --- |
| 0 | Inspection completed without unfinished records or leftover paths in its observed scope. |
| 1 | Inspection completed and records or paths need manual review. |
| 2 | Planning was blocked, unsafe, incompatible, malformed, changed during inspection or over budget. |

An exit of 0 is not a claim that no descendants remain or that an application is
safe. Invalid or oversized history cannot become a clean partial result. JSON
sets `complete=false` for incomplete inspection, and `cleanup_permitted=false`
for every plan: it never grants deletion permission. Each repair workspace
separately reports `archive_available`; the explicit archive command returns
`deleted=false` and `verification_changed=false`.

## Security repair checkpoints

New recipe repairs, LLM proposals and each Challenge workspace record a unique
workspace ID before creation, then persist `prepared`, `testing`, `proposing`,
`patching`, `rescanning`, `cleanup_pending` and `cleaned` checkpoints as applicable.
These describe the last saved stage; they do not prove process liveness or that
an in-flight test completed. The plan includes the saved proposal status,
completion timestamp presence, recorded checks and named Challenge variant, without exporting
source, patches, prompts or logs. Existing records without checkpoints stay
readable and cannot authorize workspace recovery.

Ghost's home screen and REPL warn about unfinished repair history. Run
`ghost recover` to see the stage and next action. The plan retains completed and
unfinished historical records; a later successful solve does not rewrite an
interrupted record. Startup warnings stop for older archived runs once a newer
solve finishes, while unarchived pending workspaces remain visible.

## Explicit archive cleanup

When the plan offers an archive command, copy its exact workspace ID:

```bash
ghost recover --archive 0123456789abcdef0123456789abcdef
```

This example ID is illustrative; use the ID printed by your plan. Ghost moves
that registered, detached workspace to `.ghost/recovered/repair-<id>` using
`git worktree move`. **No contents are deleted and no disk space is reclaimed.**
Candidate edits, ignored files, untracked notes and logs in the workspace remain
in the retained archive. Other worktrees and the developer checkout stay in place.
The saved run records the archive location through its stable ID. Review archive
contents privately before any later manual removal; there is no automatic purge.

Archiving requires an existing available checkout lock, one unambiguous saved
repair run, matching directory device/inode and `.git` fingerprint, the original
Git common directory, an unlocked detached registration and an absent destination.
Storage paths use no-follow and ownership checks. Only `prepared` (before project
execution) or `cleanup_pending` (normal workspace body completed) checkpoints
qualify. A process killed during testing, model work, patching or rescanning leaves
an uncertain workspace that is **retained in place**. Old debugger references,
unregistered leftovers, symlinks, replacement directories and locked or attached
worktrees never authorize this action. File modifications inside an eligible
workspace are preserved in the archive, including ignored and untracked files.

If the move finishes but saving its new location fails, no files are discarded.
Rerun `ghost recover --json`, then repeat the same archive command. Ghost verifies
the existing destination identity before recording it; it never overwrites a
second directory. A recorded `archived` run remains historical, not verified.

**Recovery never resumes testing or applies a patch.** An unfinished or archived
workspace record blocks application of its proposal. Run a fresh `ghost solve`
and any required `ghost challenge --tests ...` before approving a new proposal.
Existing patch fingerprints and source freshness checks still apply. The command
never promotes an interrupted test or Challenge to a passing result.

This is conservative retained-workspace recovery, not destructive cleanup or a
process-termination guarantee. The checkout lock coordinates cooperating Ghost
commands. Same-user non-cooperating processes can still race filesystem checks;
detached descendant liveness is not inferred from a free lock or a checkpoint.
Git's move and SQLite's metadata update are not one atomic transaction; the
verified retry handles a completed move with an unsaved record. Interrupted
patch installation, power loss, and arbitrary debugger experiment ownership
remain separate work.
