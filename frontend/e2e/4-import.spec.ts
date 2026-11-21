import { expect, test } from "playwright/test";

// Import a Toggl Track detailed report: preview, import, and a second import that adds nothing.
const TOGGL = [
  "User,Email,Client,Project,Task,Description,Billable,Start date,Start time,End date,End time,Duration,Tags,Amount (EUR)",
  "Demo,demo@example.test,Lumen Optik,Catalogue,,Product photos,Yes,2026-02-03,09:00:00,2026-02-03,11:30:00,02:30:00,,",
  'Demo,demo@example.test,Lumen Optik,Catalogue,,"Layout, second pass",No,2026-02-04,14:00:00,2026-02-04,14:45:00,00:45:00,,',
].join("\n");

test("import time from a Toggl CSV", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Time", exact: true }).click();

  const file = { name: "toggl.csv", mimeType: "text/csv", buffer: Buffer.from(TOGGL) };
  const dialog = page.getByRole("dialog");
  await page.getByRole("button", { name: "Import from Toggl" }).click();
  await dialog.getByLabel("Currency for new clients").selectOption("EUR");
  await dialog.getByLabel("Toggl CSV file").setInputFiles(file);
  await expect(dialog.getByRole("status")).toContainText("2 entries, 3h 15m in total.");
  await expect(dialog.getByRole("status")).toContainText("New clients: Lumen Optik.");
  await dialog.getByRole("button", { name: "Import" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveText("Imported 2 entries (3h 15m).");

  // the same file again: nothing new, so nothing to import
  await page.getByRole("button", { name: "Import from Toggl" }).click();
  await dialog.getByLabel("Toggl CSV file").setInputFiles(file);
  await expect(dialog.getByRole("status")).toContainText("Nothing new to import.");
  await expect(dialog.getByRole("button", { name: "Import" })).toBeDisabled();
  await dialog.getByRole("button", { name: "Cancel" }).click();

  await page.getByRole("link", { name: "Clients", exact: true }).click();
  await expect(page.getByRole("region", { name: "Lumen Optik" })).toContainText("Billed in EUR");
});

// The imported billable entry goes onto a draft that already exists.
test("add tracked time to an existing draft", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Invoices", exact: true }).click();
  await page.getByRole("link", { name: "New invoice" }).click();
  await page.getByLabel("Client").selectOption({ label: "Lumen Optik (EUR)" });
  await page.getByRole("checkbox", { name: /Include Catalogue/ }).uncheck();
  await page.getByRole("button", { name: "Create empty draft" }).click();
  await expect(page.getByRole("heading", { name: "Draft invoice" })).toBeVisible();

  await page.getByRole("button", { name: "Add line" }).click();
  await page.getByLabel("Line 1 description").fill("Retainer"); // unsaved, must survive
  await page.getByLabel("Line 1 unit price").fill("100");
  await page.getByRole("button", { name: "Add tracked time" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Add 2h 30m" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByLabel("Line 1 description")).toHaveValue("Retainer");
  await expect(page.getByLabel("Line 2 description")).toHaveValue("Catalogue: 3 Feb 2026");
  await expect(page.getByLabel("Line 2 quantity")).toHaveValue("2.5");
  await expect(page.getByRole("button", { name: "Saved" })).toBeDisabled();

  await page.getByRole("button", { name: "Add tracked time" }).click();
  await expect(dialog).toContainText("No unbilled time for this client.");
  await dialog.getByRole("button", { name: "Cancel" }).click();
});
