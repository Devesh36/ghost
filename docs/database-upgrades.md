# Local database compatibility and recovery

Ghost stores project history in `.ghost/ghost.db`. Startup now records a schema
version in SQLite's `PRAGMA user_version`; the first supported version is **1**.
This version describes the SQL layout, independently of Ghost's package version
and the evidence models stored in JSON payloads.

## Upgrade behavior

- A new database is initialized at version 1.
- Version 0 is the legacy unversioned format. Recognized legacy tables and
  indexes are checked before the missing parts of that layout are created.
  Existing session IDs, event sequence numbers, audits, investigations, solutions
  and payload bytes remain unchanged. An incomplete investigation stays incomplete.
- Migration statements and the version marker run in one explicit transaction.
  A failed statement or interruption rolls back the entire upgrade. SQLite
  recovers an uncommitted transaction on the next compatible open after a crash.
- Concurrent startup obtains SQLite's writer lock and rechecks the version
  after waiting. An upgrade runs once; other processes see the committed layout.
  Lock waits retain the existing ten-second connection timeout.
- A future or invalid version is refused before migration or a journal-mode
  change. An unrecognized or incomplete versioned layout is also refused.
  Ghost does not reset the database or guess how to repair it.

Every subsequent repository connection checks the version inside its transaction.
A running process cannot silently keep writing after another installation changes
the version. Writers acquire their lock before this check; history readers use
query-only transactions and retain a consistent WAL snapshot while writers work.
Internal callers of `Database.connect()` receive a write transaction by default;
use `connect(write=False)` for inspection.

The existing storage ownership, private permissions, no-follow/link checks and
file-identity checks still apply. SQLite opens named paths; these checks do not
prevent malicious concurrent replacement by another process with the same user's
permissions.

## Recover without discarding history

1. Stop Ghost watchers, shells and other processes using this repository's history.
2. Back up the entire `.ghost/` directory in private storage, including any SQLite
   WAL, shared-memory or rollback-journal files. Copying only a live `ghost.db`
   can omit committed records that are still in the WAL.
3. For a future-version error, install a Ghost version that supports that schema.
   Do not lower `user_version` or open the database with an older unversioned build;
   those older binaries do not implement the new compatibility guard.
4. For a migration error, preserve the backup and inspect permissions, available
   storage, concurrent writers and the reported compatibility limitation. Retry
   with a compatible version after resolving the cause. Investigate corruption
   using a copy rather than deleting tables or replacing the original database.

Version 1 is a structural upgrade. It does not deserialize and rewrite every
payload or certify that every saved record is valid. Existing model validation
still applies when records are inspected. Malformed investigation JSON may block
the creation of its JSON-expression index; the upgrade then rolls back. Other
invalid payloads remain preserved for explicit inspection and recovery.

## Adding a migration

Append an ordered migration in `infrastructure/database/migrations.py` and advance
the supported schema version together with its version-specific schema checks.
Retain historical layouts so databases are checked against their existing version
before upgrading, and check each new layout before completing its migration. Never alter a
released migration to change history. Execute individual statements through the
provided connection: `executescript()` can commit a pending transaction and break
the rollback guarantee. Do not open another connection, commit inside a migration,
execute project code or make network calls.

Qualification must cover independently authored legacy files, unchanged payloads,
ordered multi-step upgrades, rollback at each affected stage, abrupt termination,
concurrent startup, future versions and unsafe/inaccessible storage. Database
transactions do not recover interrupted worktrees or make source patch application
durable; those remain separate production improvements.
