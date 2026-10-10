import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { readFileSync, writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const site = fileURLToPath(new URL("../", import.meta.url));
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || "/usr/bin/chromium",
  headless: true,
  args: ["--no-sandbox"],
});
const page = await browser.newPage({
  viewport: { width: 960, height: 100 },
  deviceScaleFactor: 2,
});
const dimensions = {};
try {
  for (const name of [
    "01-repl",
    "02-commands",
    "03-findings",
    "04-verified-repair",
    "05-brief",
    "06-chat",
  ]) {
    await page.setContent(
      readFileSync(`${site}../.ghost/site-gallery/${name}.html`, "utf8"),
    );
    await page.evaluate(() => document.fonts.ready);
    const height = await page.evaluate(
      () => document.documentElement.scrollHeight,
    );
    await page.screenshot({
      path: `${site}public/assets/screenshots/${name}-terminal.png`,
      fullPage: true,
    });
    dimensions[name] = { width: 1920, height: height * 2 };
  }
  writeFileSync(
    `${site}content/terminal-gallery.json`,
    `${JSON.stringify(dimensions, null, 2)}\n`,
  );
  console.log(
    "Rendered six terminal captures using one frame, font, width, and Ghost palette.",
  );
} finally {
  await browser.close();
}
