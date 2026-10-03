'use strict';
// A documented local adapter contract: module exports a request handler.
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const [modulePath, exportName] = config.app.split(':');
  const file = path.resolve(process.cwd(), modulePath);
  const handler = require(file)[exportName];
  if (typeof handler !== 'function') throw new Error('Handler is unavailable');
  const results = [];
  for (const entry of config.cases) {
    const owner = await handler({method: 'GET', path: entry.path, headers: {...entry.owner_headers}});
    const other = await handler({method: 'GET', path: entry.path, headers: {...entry.other_headers}});
    const ownerStatus = owner && owner.status;
    const otherStatus = other && other.status;
    if (![ownerStatus, otherStatus].every(n => Number.isInteger(n) && n >= 100 && n <= 599)) {
      throw new Error('Handler did not return two HTTP statuses');
    }
    results.push({owner_status: ownerStatus, other_status: otherStatus});
  }
  process.stdout.write(JSON.stringify({results}));
}

main().catch(() => { process.exitCode = 2; });
