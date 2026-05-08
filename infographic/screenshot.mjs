// Capture each slide as a PNG so we can inspect them visually.
// Outputs to screenshots/slide-NN.png at native resolution (1080x1350).

import { chromium } from "playwright";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const URL = process.env.URL || "http://localhost:8000";
const OUT_DIR = path.join(__dirname, "screenshots");

fs.mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1100, height: 1400 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();

console.log(`loading ${URL}`);
await page.goto(URL, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);

// Strip the preview toolbar so it doesn't bleed into screenshots
await page.evaluate(() => {
  document.querySelector(".preview-toolbar")?.remove();
});

const count = await page.locator(".slide").count();
console.log(`found ${count} slides`);

for (let i = 1; i <= count; i++) {
  const out = path.join(OUT_DIR, `slide-${String(i).padStart(2, "0")}.png`);
  await page.locator(`#slide-${i}`).screenshot({ path: out });
  console.log(`  → ${out}`);
}

await browser.close();
console.log("done");
