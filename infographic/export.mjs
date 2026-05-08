// Export the carousel to a single multi-page PDF using Playwright.
// One PDF page per .slide section. Page size matches design exactly: 1080×1350.

import { chromium } from "playwright";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT = 8765; // separate from preview port to avoid conflicts
const URL = `http://localhost:${PORT}`;
const OUTPUT = path.join(__dirname, "carousel.pdf");

// 1. Spin up the static server in a child process
console.log("starting static server...");
const server = spawn("node", ["server.mjs"], {
  cwd: __dirname,
  env: { ...process.env, PORT: String(PORT) },
  stdio: ["ignore", "pipe", "inherit"],
});

await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error("server start timeout")), 5000);
  server.stdout.on("data", (data) => {
    if (data.toString().includes("http://")) {
      clearTimeout(timeout);
      resolve();
    }
  });
  server.on("error", reject);
});

// 2. Launch headless Chromium and load the page
console.log("launching chromium...");
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1080, height: 1350 },
  deviceScaleFactor: 2,
});
const page = await context.newPage();

console.log(`loading ${URL}...`);
await page.goto(URL, { waitUntil: "networkidle" });

// Force print media so the @media print rules in base.css kick in
await page.emulateMedia({ media: "print" });

// Make sure web fonts are loaded before exporting
await page.evaluate(() => document.fonts.ready);

// 3. Generate the PDF — one page per .slide via CSS page-break-after: always
console.log(`writing ${OUTPUT}...`);
await page.pdf({
  path: OUTPUT,
  width: "1080px",
  height: "1350px",
  printBackground: true,
  preferCSSPageSize: false,
  margin: { top: 0, right: 0, bottom: 0, left: 0 },
});

await browser.close();
server.kill();

console.log(`✓ exported to ${OUTPUT}`);
console.log("  upload as a document attachment to LinkedIn for a carousel post.");
