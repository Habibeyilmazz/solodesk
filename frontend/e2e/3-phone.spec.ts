import { expect, test } from "playwright/test";

// On a phone-sized screen every page fits its width, and the invoice list shows each
// invoice's status and total without scrolling sideways. Runs on the data the earlier specs left.
test.use({ viewport: { width: 390, height: 844 } });

test("pages fit a phone screen", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  const invoices = await (await page.request.get("/api/invoices")).json();
  const paths = ["/", "/time", "/clients", "/invoices", "/settings", "/invoices/new"];
  paths.push(...invoices.map((i: { id: number }) => `/invoices/${i.id}`));
  for (const path of paths) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, `page width of ${path}`).toBeLessThanOrEqual(390);
  }

  await page.goto("/invoices");
  const row = page.getByRole("row").nth(1);
  await expect(row).toBeVisible();
  for (const cell of await row.getByRole("cell").all()) await expect(cell).toBeInViewport();
});
