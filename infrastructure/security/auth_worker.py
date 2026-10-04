"""Pure-stdlib ASGI authorization probe; executed only in a confined worktree."""
import asyncio
import importlib
import json
from pathlib import Path
import sys


async def status(app, case, headers):
    seen = []
    body = bytearray()
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        return {'type': 'http.disconnect'}

    async def send(message):
        if message['type'] == 'http.response.start':
            if seen:
                raise ValueError('Duplicate HTTP status')
            seen.append(message['status'])
        elif message['type'] == 'http.response.body':
            chunk = message.get('body', b'')
            if not isinstance(chunk, bytes) or len(body) + len(chunk) > 1_000_000:
                raise ValueError('Response exceeded probe budget')
            body.extend(chunk)

    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
             'http_version': '1.1', 'method': 'GET', 'scheme': 'http',
             'path': case['path'], 'raw_path': case['path'].encode('ascii'),
             'query_string': b'', 'root_path': '',
             'headers': [(key.lower().encode('ascii'), value.encode('utf-8')) for key, value in headers.items()],
             'client': ('127.0.0.1', 0), 'server': ('ghost.invalid', 80), 'state': {}}
    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    if len(seen) != 1 or not isinstance(seen[0], int) or not 100 <= seen[0] <= 599:
        raise ValueError('Missing HTTP response status')
    return seen[0], case['protected_marker'].encode('utf-8') in body


async def probe(config, order):
    if order not in {'owner_first', 'other_first'}:
        raise ValueError('Invalid probe order')
    module, export = config['app'].split(':', 1)
    sys.path.insert(0, str(Path.cwd()))
    app = getattr(importlib.import_module(module), export)
    if not callable(app):
        raise ValueError('ASGI app is not callable')
    results = [None] * len(config['cases'])
    indices = range(len(results)) if order == 'owner_first' else reversed(range(len(results)))
    actors = ('owner', 'other') if order == 'owner_first' else ('other', 'owner')
    for index in indices:
        case = config['cases'][index]
        observed = {}
        for actor in actors:
            observed[actor] = await status(app, case, case[f'{actor}_headers'])
        owner, owner_marker = observed['owner']
        other, other_marker = observed['other']
        results[index] = {'owner_status': owner, 'other_status': other,
                          'owner_marker_seen': owner_marker, 'other_marker_seen': other_marker}
    return {'results': results}


if __name__ == '__main__':
    try:
        with open(sys.argv[1], encoding='utf-8') as stream:
            settings = json.load(stream)
        print(json.dumps(asyncio.run(probe(settings, sys.argv[2])), separators=(',', ':')))
    except Exception:
        # Project exceptions may contain credentials or response bodies.
        sys.exit(2)
