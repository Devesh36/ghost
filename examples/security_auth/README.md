# Authorization examples

These tiny apps deliberately let Bob read Alice's record. The corrected versions
check the record owner. Run them only as disposable local examples.

In a new Git repository, copy one runtime's `app.py` or `app.cjs` to the root as
`app.py` or `app.cjs`, make an initial commit, and run `ghost auth --init`. Edit
`.ghost/auth.json` to match that runtime's `auth.example.json`. Python users need
FastAPI in Ghost's Python environment or can pass
`ghost find --auth --auth-python .venv/bin/python` for their project environment.
Then run `ghost find --auth` to reproduce the access failure. Run
`ghost auth --prepare-candidate`, and replace only `.ghost/candidate.py` or
`.ghost/candidate.cjs` with the matching `fixed_app` source. Run
`ghost auth --candidate`: the real app still lets Bob in, while the proposed
change denies him in a separate worktree. The owner should still receive HTTP
200; Bob should receive HTTP 403 in the proposed version. Only after reviewing
that evidence, update the real app and rerun `ghost find --auth`.

The contract deliberately uses fake users and a fake record. Its
`protected_marker` is synthetic text in Alice's response. Ghost sends GET
requests in an isolated Git worktree without opening a server port. It stores
the case name, path, status codes, verdict, and whether each actor received
the marker; it does not store response bodies or the marker. Keep real test
credentials in the ignored `.ghost/auth.json`; do not commit them.
