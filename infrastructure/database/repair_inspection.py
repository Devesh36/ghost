"""Bounded reads of repair lifecycle metadata, with full record validation."""
from core.security.models import SecuritySolution


def repair_records(db):
    total = 0
    records = []
    ids = set()
    rows = db.execute('SELECT substr(id, 1, 129), length(CAST(payload AS BLOB)), '
                      'CASE WHEN length(CAST(payload AS BLOB)) <= 2000000 THEN payload END '
                      'FROM security_solutions LIMIT 1001')
    for key, size, payload in rows:
        if not isinstance(size, int):
            raise ValueError('Invalid repair history')
        total += size
        if len(records) >= 1000 or size > 2_000_000 or total > 16_000_000 or not isinstance(payload, str):
            raise ValueError('Repair history budget exceeded')
        solution = SecuritySolution.model_validate_json(payload)
        if solution.id != key or not key or len(key) > 128:
            raise ValueError('Repair identity differs')
        for run in solution.recovery_runs:
            if run.id in ids:
                raise ValueError('Duplicate repair workspace identity')
            ids.add(run.id)
        records.append(solution)
    return records


def repair_recovery_notice(repo):
    """A bounded startup hint; detailed inspection and all actions stay explicit."""
    import sqlite3
    from infrastructure.database.inspection import readonly_history
    from infrastructure.database.migrations import check_schema, check_version
    try:
        with readonly_history(repo) as db:
            if db is None:
                return None
            version = check_version(db)
            check_schema(db, version=version)
            if version == 0:
                return None
            records = repair_records(db)
            latest = max(records, key=lambda item: (item.started_at, item.id), default=None)
            if ((latest is not None and latest.finished_at is None)
                    or any(run.stage not in {'cleaned', 'archived'}
                           for solution in records for run in solution.recovery_runs)):
                return 'Unfinished repair history needs review. Run ghost recover; verification has not been resumed.'
    except (OSError, ValueError, sqlite3.Error, RecursionError):
        return 'Repair recovery state could not be inspected. Run ghost recover; preserve .ghost.'
    return None
