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
