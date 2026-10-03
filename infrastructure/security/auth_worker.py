"""Pure-stdlib ASGI authorization probe; executed only in a confined worktree."""
import asyncio
import importlib
import json
from pathlib import Path
import sys


async def status(app, case, headers):
    seen = []
    size = 0
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        return {'type': 'http.disconnect'}

    async def send(message):
        nonlocal size
        if message['type'] == 'http.response.start':
            if seen:
                raise ValueError('Duplicate HTTP status')
            seen.append(message['status'])
        elif message['type'] == 'http.response.body':
            size += len(message.get('body', b''))
            if size > 1_000_000:
                raise ValueError('Response exceeded probe budget')

    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
             'http_version': '1.1', 'method': 'GET', 'scheme': 'http',
             'path': case['path'], 'raw_path': case['path'].encode('ascii'),
             'query_string': b'', 'root_path': '',
             'headers': [(key.lower().encode('ascii'), value.encode('utf-8')) for key, value in headers.items()],
             'client': ('127.0.0.1', 0), 'server': ('ghost.invalid', 80), 'state': {}}
    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    if len(seen) != 1 or not isinstance(seen[0], int) or not 100 <= seen[0] <= 599:
        raise ValueError('Missing HTTP response status')
    return seen[0]


async def probe(config):
    module, export = config['app'].split(':', 1)
    sys.path.insert(0, str(Path.cwd()))
    app = getattr(importlib.import_module(module), export)
    if not callable(app):
        raise ValueError('ASGI app is not callable')
    results = []
    for case in config['cases']:
        owner = await status(app, case, case['owner_headers'])
        other = await status(app, case, case['other_headers'])
        results.append({'owner_status': owner, 'other_status': other})
    return {'results': results}


if __name__ == '__main__':
    try:
        with open(sys.argv[1], encoding='utf-8') as stream:
            settings = json.load(stream)
        print(json.dumps(asyncio.run(probe(settings)), separators=(',', ':')))
    except Exception:
        # Project exceptions may contain credentials or response bodies.
        sys.exit(2)
