"""Intentionally vulnerable FastAPI app for local Ghost authorization tests."""
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()
RECORDS = {'1': {'owner': 'alice', 'value': 'alice-private-example'}}


@app.get('/records/{record_id}')
def read_record(record_id: str, x_test_user: str = Header(default='anonymous')):
    record = RECORDS.get(record_id)
    if record is None:
        raise HTTPException(status_code=404)
    # BUG: a different user can read Alice's record.
    return {'value': record['value']}
