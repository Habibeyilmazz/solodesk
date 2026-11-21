// Records docs/demo.gif: client -> project -> time -> invoice -> sent -> paid, in the real app.
//   (an EMPTY instance)  SOLODESK_PASSWORD=... make run
//   cd frontend && SOLODESK_PASSWORD=... node scripts/demo.mjs     (needs ffmpeg)
import { execFileSync } from "node:child_process";
import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const base = process.env.SOLODESK_URL ?? "http://127.0.0.1:4150";
const out = fileURLToPath(new URL("../../docs/demo.gif", import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "solodesk-demo-"));
const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1000, height: 640 },
  recordVideo: { dir, size: { width: 1000, height: 640 } },
});
const page = await ctx.newPage();
const pause = (ms = 900) => page.waitForTimeout(ms);
const type = (loc, text) => loc.pressSequentially(text, { delay: 45 });

await page.goto(base);
await type(page.getByLabel("Password"), process.env.SOLODESK_PASSWORD ?? "change-me-please");
await page.getByRole("button", { name: "Sign in" }).click();
await page.getByRole("heading", { name: "Dashboard" }).waitFor();
await pause();

await page.getByRole("link", { name: "Clients", exact: true }).click();
await page.getByRole("button", { name: "New client" }).click();
const dialog = page.getByRole("dialog");
await type(dialog.getByLabel("Name"), "Acme Studio");
await dialog.getByLabel("Invoice currency").selectOption("EUR");
await pause(500);
await dialog.getByRole("button", { name: "Add client" }).click();
const client = page.getByRole("region", { name: "Acme Studio" });
await client.getByRole("button", { name: "Add project" }).click();
await type(dialog.getByLabel("Project name"), "Website");
await type(dialog.getByLabel(/Hourly rate/), "80");
await pause(500);
await dialog.getByRole("button", { name: "Add project" }).click();
await pause();

await page.getByRole("link", { name: "Time", exact: true }).click();
const add = page.getByRole("region", { name: "Add time by hand" });
await type(add.getByLabel("Duration"), "2:15");
await type(add.getByLabel("Description"), "Wireframes");
await add.getByRole("button", { name: "Add entry" }).click();
await pause();

await page.getByRole("link", { name: "Invoices", exact: true }).click();
await page.getByRole("link", { name: "New invoice" }).click();
await pause();
await page.getByRole("button", { name: /Create draft with/ }).click();
await page.getByRole("heading", { name: "Draft invoice" }).waitFor();
await pause(1200);
await page.getByRole("button", { name: "Add line" }).click();
await type(page.getByLabel("Line 2 description"), "Hosting, one year");
await type(page.getByLabel("Line 2 unit price"), "48");
await pause(1200);
await page.getByRole("button", { name: "Save draft" }).click();
page.once("dialog", (d) => d.accept());
await page.getByRole("button", { name: "Mark as sent" }).click();
await page.getByRole("heading", { name: /Invoice INV-/ }).waitFor();
await pause(1200);
await page.getByRole("button", { name: "Mark as paid" }).click();
await pause(1000);
await page.getByRole("link", { name: "Dashboard", exact: true }).click();
await pause(2000);

await ctx.close(); // flushes the video
await browser.close();
const video = join(dir, readdirSync(dir).find((f) => f.endsWith(".webm")));
const filter = "fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4";
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", video, "-vf", filter, "-loop", "0", out]);
console.log(`Wrote ${out}`);
