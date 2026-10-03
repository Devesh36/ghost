// Corrected example: the record owner is checked for every read.
const records = {'1': {owner: 'alice', value: 'alice-private-example'}};
exports.handle = async function (request) {
  const id = request.path.split('/').at(-1);
  const record = records[id];
  if (!record) return {status: 404};
  if (record.owner !== request.headers['x-test-user']) return {status: 403};
  return {status: 200, body: {value: record.value}};
};
