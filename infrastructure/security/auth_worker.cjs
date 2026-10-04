'use strict';
// A documented local adapter contract: module exports a request handler.
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const order = process.argv[3];
  if (!['owner_first', 'other_first'].includes(order)) throw new Error('Invalid probe order');
  const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const [modulePath, exportName] = config.app.split(':');
  const file = path.resolve(process.cwd(), modulePath);
  const handler = require(file)[exportName];
  if (typeof handler !== 'function') throw new Error('Handler is unavailable');
  const results = Array(config.cases.length);
  const indices = config.cases.map((_, index) => index);
  if (order === 'other_first') indices.reverse();
  const actors = order === 'owner_first' ? ['owner', 'other'] : ['other', 'owner'];
  for (const index of indices) {
    const entry = config.cases[index];
    const observed = {};
    for (const actor of actors) {
      observed[actor] = await handler({method: 'GET', path: entry.path,
                                       headers: {...entry[`${actor}_headers`]}});
    }
    const owner = observed.owner;
    const other = observed.other;
    const ownerStatus = owner && owner.status;
    const otherStatus = other && other.status;
    if (![ownerStatus, otherStatus].every(n => Number.isInteger(n) && n >= 100 && n <= 599)) {
      throw new Error('Handler did not return two HTTP statuses');
    }
    const markerSeen = response => {
      const value = response && response.body;
      const body = Buffer.isBuffer(value) ? value : Buffer.from(
        typeof value === 'string' ? value : JSON.stringify(value ?? '')
      );
      if (body.length > 1_000_000) throw new Error('Response exceeded probe budget');
      return body.includes(Buffer.from(entry.protected_marker, 'utf8'));
    };
    results[index] = {owner_status: ownerStatus, other_status: otherStatus,
                      owner_marker_seen: markerSeen(owner), other_marker_seen: markerSeen(other)};
  }
  process.stdout.write(JSON.stringify({results}));
}

main().catch(() => { process.exitCode = 2; });
