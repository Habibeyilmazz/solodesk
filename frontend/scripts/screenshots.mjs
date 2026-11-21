// Regenerates docs/screenshots from a running, seeded instance:
//   make seed && make run          (in one terminal)
//   cd frontend && SOLODESK_PASSWORD=... node scripts/screenshots.mjs
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const base = process.env.SOLODESK_URL ?? "http://127.0.0.1:4150";
const out = fileURLToPath(new URL("../../docs/screenshots/", import.meta.url));
const browser = await chromium.launch();

async function session(viewport) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 2 });
  await page.goto(base);
  await page.getByLabel("Password").fill(process.env.SOLODESK_PASSWORD ?? "change-me-please");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("heading", { name: "Dashboard" }).waitFor();
  return {
    page,
    async shot(path, name, fullPage = false) {
      await page.goto(base + path);
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: `${out}${name}.png`, fullPage });
    },
  };
}

const desktop = await session({ width: 1280, height: 940 });
const invoices = await (await desktop.page.request.get(`${base}/api/invoices`)).json();
const pick = (status) => invoices.find((i) => i.status === status)?.id;

await desktop.shot("/", "dashboard");
await desktop.shot("/time", "time");
await desktop.shot("/clients", "clients");
await desktop.shot("/invoices", "invoices");
if (pick("draft")) await desktop.shot(`/invoices/${pick("draft")}`, "invoice-draft");
if (pick("overdue")) await desktop.shot(`/invoices/${pick("overdue")}`, "invoice-overdue");
if (pick("paid")) {
  const pdf = await desktop.page.request.get(`${base}/api/invoices/${pick("paid")}/pdf`);
  writeFileSync(`${out}../sample-invoice.pdf`, await pdf.body());
}

const phone = await session({ width: 390, height: 844 });
await phone.shot("/", "phone-dashboard", true);

await browser.close();
console.log(`Screenshots written to ${out}`);
