import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// The CLI owns the Ghost palette. No second set of website colors to maintain.
const site = fileURLToPath(new URL("../", import.meta.url));
const sourcePath = `${site}../config/theme.py`;
const snapshotPath = `${site}content/terminal-palette.json`;
const names = [
  "text",
  "mint",
  "lavender",
  "muted",
  "line",
  "warning",
  "danger",
  "bg",
  "panel",
];
let colors;
if (existsSync(sourcePath)) {
  const source = readFileSync(sourcePath, "utf8");
  const declaration = source.match(/['"]ghost['"]:\s*Palette\(([\s\S]*?)\),/);
  colors = declaration?.[1].match(/#[\da-f]{6}/gi);
} else {
  // Root-directory deployments can use the recorded CLI palette, like captures.
  const snapshot = JSON.parse(readFileSync(snapshotPath, "utf8"));
  colors = names.map((name) => snapshot[name]);
}
if (
  !colors ||
  colors.length !== names.length ||
  colors.some(
    (color) => typeof color !== "string" || !/^#[\da-f]{6}$/i.test(color),
  )
)
  throw new Error(
    "Ghost terminal palette could not be read; update the theme generator for its new format.",
  );
if (existsSync(sourcePath))
  writeFileSync(
    snapshotPath,
    `${JSON.stringify(Object.fromEntries(names.map((name, index) => [name, colors[index]])), null, 2)}\n`,
  );
mkdirSync(`${site}.generated`, { recursive: true });
writeFileSync(
  `${site}.generated/terminal-theme.css`,
  `/* Generated from config/theme.py by scripts/generate-theme.mjs. */\n:root {\n${names.map((name, index) => `  --${name}: ${colors[index]};`).join("\n")}\n}\n`,
);
console.log(
  `Website colors generated from the Ghost terminal palette${existsSync(sourcePath) ? "" : " snapshot"}.`,
);
