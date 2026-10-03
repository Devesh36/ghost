"""Corrected example: the record owner is checked for every read."""
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()
RECORDS = {'1': {'owner': 'alice', 'value': 'alice-private-example'}}


@app.get('/records/{record_id}')
def read_record(record_id: str, x_test_user: str = Header(default='anonymous')):
    record = RECORDS.get(record_id)
    if record is None:
        raise HTTPException(status_code=404)
    if record['owner'] != x_test_user:
        raise HTTPException(status_code=403)
    return {'value': record['value']}
