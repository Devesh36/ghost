import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const site = fileURLToPath(new URL("../", import.meta.url));
const snapshotPath = `${site}content/commit-history.json`;
let snapshot = [];
try {
  snapshot = JSON.parse(readFileSync(snapshotPath, "utf8"));
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
const commits = new Map(snapshot.map((commit) => [commit.hash, commit]));
const localDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Kolkata",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const descriptions = {
  d7b0cde:
    "Documented the original local debugging idea and intended workflow.",
  abacf92:
    "Implemented the first CLI, file and command collectors, local database, investigation agents, and isolated experiments.",
};
try {
  const log = execFileSync(
    "git",
    ["log", "--reverse", "--format=%H%x1f%aI%x1f%s"],
    {
      cwd: `${site}..`,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  for (const line of log.trim().split("\n")) {
    if (!line) continue;
    const [hash, timestamp, subject] = line.split("\x1f");
    const previous = commits.get(hash);
    commits.set(hash, {
      hash,
      timestamp,
      date: localDate.format(new Date(timestamp)),
      subject,
      description:
        previous?.description || descriptions[hash.slice(0, 7)] || subject,
    });
  }
} catch {
  if (!commits.size)
    throw new Error("No Git history or recorded history is available.");
  console.log("Using recorded Ghost history (Git metadata unavailable).");
}
const history = [...commits.values()].sort(
  (a, b) => new Date(a.timestamp) - new Date(b.timestamp),
);
mkdirSync(`${site}.generated`, { recursive: true });
writeFileSync(
  `${site}.generated/history.json`,
  `${JSON.stringify(history, null, 2)}\n`,
);
if (process.argv.includes("--snapshot")) {
  mkdirSync(`${site}content`, { recursive: true });
  writeFileSync(snapshotPath, `${JSON.stringify(history, null, 2)}\n`);
}
console.log(`Recorded ${history.length} commits for the Ghost phase timeline.`);
