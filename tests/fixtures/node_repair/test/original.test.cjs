"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { parse } = require("../parser.cjs");

test("original parser evaluates an expression", () => {
  assert.equal(parse("2 + 3"), 5);
});
