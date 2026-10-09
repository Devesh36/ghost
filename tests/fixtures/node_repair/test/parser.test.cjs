"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { parse } = require("../parser.cjs");

test("preserves JSON arrays", () => {
  assert.deepEqual(parse("[3, 4]"), [3, 4]);
});

test("preserves JSON strings", () => {
  assert.equal(parse('"hello"'), "hello");
});
