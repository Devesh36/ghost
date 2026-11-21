import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

const snapshot = [{
  hash: "a".repeat(40), timestamp: "2001-01-01T00:00:00Z", date: "2001-01-01",
  subject: "Recorded Ghost change", description: "Keep this recorded description",
}];

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), "ghost-history-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith("GIT_")));
  Object.assign(env, {
    GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1", GIT_CEILING_DIRECTORIES: root,
    GIT_AUTHOR_DATE: "2026-11-21T00:00:00Z", GIT_COMMITTER_DATE: "2026-11-21T00:00:00Z",
  });
  return { root, env };
}

function exportSource(checkout, recorded = snapshot) {
  mkdirSync(join(checkout, "site/scripts"), { recursive: true });
  mkdirSync(join(checkout, "site/content"), { recursive: true });
  copyFileSync(new URL("./generate-history.mjs", import.meta.url), join(checkout, "site/scripts/generate-history.mjs"));
  writeFileSync(join(checkout, "site/content/commit-history.json"), JSON.stringify(recorded));
}

function git(checkout, env, ...args) {
  return execFileSync("git", args, { cwd: checkout, env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function commit(checkout, env, subject) {
  git(checkout, env, "init", "-q", "--template=");
  git(checkout, env, "add", ".");
  git(checkout, env, "-c", "user.name=Ghost Timeline Test", "-c", "user.email=timeline@example.invalid",
    "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", subject);
  return git(checkout, env, "rev-parse", "HEAD");
}

function generate(checkout, env, ...args) {
  return execFileSync(process.execPath, [join(checkout, "site/scripts/generate-history.mjs"), ...args],
    { cwd: checkout, env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
}

function generated(checkout) {
  return JSON.parse(readFileSync(join(checkout, "site/.generated/history.json"), "utf8"));
}

test("a genuine Ghost checkout merges its commits and preserves recorded descriptions", (t) => {
  const { root, env } = fixture(t);
  const checkout = join(root, "ghost with spaces");
  exportSource(checkout);
  const hash = commit(checkout, env, "Synthetic Ghost implementation");
  generate(checkout, env, "--snapshot");
  const history = generated(checkout);
  assert.deepEqual(history[0], snapshot[0]);
  assert.equal(history.length, 2);
  assert.equal(history[1].hash, hash);
  assert.equal(history[1].subject, "Synthetic Ghost implementation");
  assert.deepEqual(JSON.parse(readFileSync(join(checkout, "site/content/commit-history.json"), "utf8")), history);
});

test("a standalone Git-free export uses its bundled snapshot", (t) => {
  const { root, env } = fixture(t);
  const checkout = join(root, "ghost");
  exportSource(checkout);
  assert.match(generate(checkout, env), /Using recorded Ghost history/);
  assert.deepEqual(generated(checkout), snapshot);
});

test("a Git-free export inside another repository never imports or persists parent history", (t) => {
  const { root, env } = fixture(t);
  const parent = join(root, "unrelated");
  mkdirSync(parent);
  const parentHash = commit(parent, env, "UNRELATED_PARENT_ONLY");
  const checkout = join(parent, "ghost-export");
  exportSource(checkout);
  assert.match(generate(checkout, env, "--snapshot"), /Using recorded Ghost history/);
  assert.deepEqual(generated(checkout), snapshot);
  assert.deepEqual(JSON.parse(readFileSync(join(checkout, "site/content/commit-history.json"), "utf8")), snapshot);
  assert.ok(!JSON.stringify(generated(checkout)).includes(parentHash));
});

test("unrelated parent history cannot substitute for a missing Ghost snapshot", (t) => {
  const { root, env } = fixture(t);
  const parent = join(root, "unrelated");
  mkdirSync(parent);
  commit(parent, env, "UNRELATED_PARENT_ONLY");
  const checkout = join(parent, "ghost-export");
  exportSource(checkout, []);
  assert.throws(() => generate(checkout, env), /No Git history or recorded history is available/);
});

test("a shallow Ghost checkout retains older bundled entries", (t) => {
  const { root, env } = fixture(t);
  const source = join(root, "source");
  exportSource(source);
  commit(source, env, "Older synthetic Ghost commit");
  const latest = commit(source, env, "Latest synthetic Ghost commit");
  const checkout = join(root, "shallow");
  git(root, env, "clone", "--depth=1", pathToFileURL(source).href, checkout);
  assert.equal(git(checkout, env, "rev-parse", "--is-shallow-repository"), "true");
  generate(checkout, env);
  assert.deepEqual(generated(checkout).map(({ hash }) => hash), [snapshot[0].hash, latest]);
});

test("a linked Ghost worktree can read its own history through a symlinked path", (t) => {
  const { root, env } = fixture(t);
  const source = join(root, "source");
  exportSource(source);
  const hash = commit(source, env, "Synthetic Ghost worktree history");
  const checkout = join(root, "linked-worktree");
  git(source, env, "worktree", "add", "--detach", checkout, "HEAD");
  const alias = join(root, "checkout-alias");
  symlinkSync(checkout, alias, "dir");
  // Preserve the script alias so the generator itself must canonicalize it.
  execFileSync(process.execPath, ["--preserve-symlinks-main", join(alias, "site/scripts/generate-history.mjs")],
    { cwd: alias, env, stdio: ["ignore", "pipe", "pipe"] });
  assert.deepEqual(generated(checkout).map((entry) => entry.hash), [snapshot[0].hash, hash]);
});
