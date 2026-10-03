// Intentionally vulnerable local handler. No server or network bind is needed.
const records = {'1': {owner: 'alice', value: 'alice-private-example'}};
exports.handle = async function (request) {
  const id = request.path.split('/').at(-1);
  const record = records[id];
  if (!record) return {status: 404};
  // BUG: a different user can read Alice's record.
  return {status: 200, body: {value: record.value}};
};
