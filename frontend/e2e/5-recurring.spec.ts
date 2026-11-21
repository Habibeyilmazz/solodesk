import { expect, test } from "playwright/test";

// Repeat the smoke test's INV-0001 every year: the first draft is made at once, only its
// fixed line ($48 hosting plus 20% tax) is copied, and stopping keeps that draft.
test("repeat an invoice, then stop", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Invoices", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Recurring" })).toHaveCount(0);

  await page.getByRole("link", { name: "INV-0001" }).click();
  await page.getByRole("button", { name: "Repeat", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("How often").selectOption({ label: "Every year" });
  await dialog.getByLabel("First draft on").fill(new Date().toLocaleDateString("sv")); // today
  await dialog.getByRole("button", { name: "Repeat invoice" }).click();

  const recurring = page.getByRole("region", { name: "Recurring" });
  const row = recurring.getByRole("row", { name: /INV-0001/ });
  await expect(row).toContainText("Every year");
  await expect(row).toContainText("$57.60");
  const nextYear = new Date();
  nextYear.setFullYear(nextYear.getFullYear() + 1);
  await expect(row).toContainText(String(nextYear.getFullYear()));

  await page.getByRole("button", { name: /^Drafts/ }).click();
  const invoices = page.locator("table.invoices");
  const draft = invoices.getByRole("row", { name: /Acme Yazılım/ }).filter({ hasText: "$57.60" });
  await expect(draft).toHaveCount(1);

  page.once("dialog", (confirm) => confirm.accept());
  await row.getByRole("button", { name: "Stop repeating INV-0001" }).click();
  await expect(recurring).toHaveCount(0);
  await expect(draft).toHaveCount(1);
});
