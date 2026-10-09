"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { parse } = require("../parser.cjs");

test("patched parser rejects an expression", () => {
  assert.throws(() => parse("2 + 3"), SyntaxError);
});
