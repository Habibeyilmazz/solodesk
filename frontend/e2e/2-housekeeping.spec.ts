import { expect, test } from "playwright/test";

// The edits and undo paths around the main flow: settings, renames, archiving, fixing and
// deleting time, throwing a draft away, undoing a payment. Runs after the smoke test on the
// same database, so it only touches data it creates itself.
test("change settings, fix mistakes and undo things", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  // Signing in again elsewhere replaces the session and its CSRF token. This tab still holds
  // the old token; its next write must recover instead of failing.
  await page.request.post("/api/auth/login", { data: { password: "e2e-password" } });

  // settings persist
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Business name").fill("Mavi Fener Studio");
  const prefix = page.getByLabel("Number prefix");
  await prefix.fill("INV 2026!"); // the form itself refuses characters the server would reject
  expect(await prefix.evaluate((el: HTMLInputElement) => el.validity.patternMismatch)).toBe(true);
  await prefix.fill("INV/");
  expect(await prefix.evaluate((el: HTMLInputElement) => el.validity.valid)).toBe(true);
  await prefix.fill("INV-");
  await page.getByLabel("Default tax %").fill("18,5");
  await page.getByLabel("Payment terms (days)").fill("30");
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByRole("status")).toHaveText("Settings saved.");
  await page.reload();
  await expect(page.getByLabel("Default tax %")).toHaveValue("18.5");
  await expect(page.getByLabel("Payment terms (days)")).toHaveValue("30");

  // create and rename a client
  await page.getByRole("link", { name: "Clients", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const newClient = page.getByRole("button", { name: "New client" });
  await newClient.click();
  await expect(dialog.getByLabel("Name")).toBeFocused();
  for (const close of [
    () => page.keyboard.press("Escape"),
    () => dialog.getByRole("button", { name: "Cancel" }).click(),
  ]) {
    await close(); // either way, focus goes back to where it came from
    await expect(dialog).toHaveCount(0);
    await expect(newClient).toBeFocused();
    await newClient.click();
  }
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await newClient.click();
  await dialog.getByLabel("Name").fill("Beta Ltd");
  await dialog.getByLabel("Invoice currency").selectOption("GBP");
  await dialog.getByRole("button", { name: "Add client" }).click();
  await page.getByRole("button", { name: "Edit client Beta Ltd" }).click();
  await dialog.getByLabel("Name").fill("Beta Limited");
  await dialog.getByRole("button", { name: "Save client" }).click();
  const client = page.getByRole("region", { name: "Beta Limited" });
  await expect(client).toContainText("Billed in GBP");

  // a project with a comma-decimal rate; archive it and bring it back
  await client.getByRole("button", { name: "Add project" }).click();
  await dialog.getByLabel("Project name").fill("Retainer");
  await dialog.getByLabel("Hourly rate (GBP)").fill("1.234");
  await dialog.getByRole("button", { name: "Add project" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Enter the rate"); // ambiguous: refused
  await dialog.getByLabel("Hourly rate (GBP)").fill("65,50");
  await dialog.getByRole("button", { name: "Add project" }).click();
  const project = client.getByRole("row", { name: /Retainer/ });
  await expect(project).toContainText("£65.50");
  await project.getByRole("button", { name: "Edit Retainer" }).click();
  await dialog.getByLabel("Archived").check();
  await dialog.getByRole("button", { name: "Save project" }).click();
  await expect(project).toContainText("Archived");
  await project.getByRole("button", { name: "Edit Retainer" }).click();
  await dialog.getByLabel("Archived").uncheck();
  await dialog.getByRole("button", { name: "Save project" }).click();
  await expect(project).not.toContainText("Archived");

  // log time, correct it, delete a mistake
  await page.getByRole("link", { name: "Time", exact: true }).click();
  const add = page.getByRole("region", { name: "Add time by hand" });
  for (const [duration, description] of [["2", "Workshop"], ["45m", "Logged by mistake"]]) {
    await add.getByLabel("Project").selectOption({ label: "Retainer" });
    await add.getByLabel("Duration").fill(duration);
    await add.getByLabel("Description").fill(description);
    await add.getByRole("button", { name: "Add entry" }).dblclick(); // must not log it twice
    await expect(page.getByRole("row", { name: new RegExp(description) })).toHaveCount(1);
  }
  const workshop = page.getByRole("row", { name: /Workshop/ });
  await workshop.getByRole("button", { name: /^Edit/ }).click();
  await dialog.getByLabel("Duration").fill("2:30");
  await dialog.getByRole("button", { name: "Save entry" }).click();
  await expect(workshop).toContainText("2h 30m");

  const mistake = page.getByRole("row", { name: /Logged by mistake/ });
  await mistake.getByRole("button", { name: /^Edit/ }).click();
  page.once("dialog", (confirm) => confirm.accept());
  await dialog.getByRole("button", { name: "Delete entry" }).click();
  await expect(mistake).toHaveCount(0);

  // a draft picks up the new default tax; deleting it frees the time again
  await draftForBeta(page);
  await expect(page.getByLabel("Tax %")).toHaveValue("18.5");
  await expect(page.getByLabel("Line 1 quantity")).toHaveValue("2.5");
  const totals = page.locator(".totals");
  await expect(totals).toContainText("£163.75"); // 2.5 x 65.50
  await expect(totals).toContainText("£30.29"); // 18.5% of 163.75 = 30.29375
  await expect(totals).toContainText("£194.04");
  await page.getByLabel("Discount %").fill("10");
  await expect(totals).toContainText("-£16.38"); // 16.375 rounds half up
  await expect(totals).toContainText("£174.63"); // (163.75 - 16.38) x 1.185
  await page.getByLabel("Tax %").fill("abc");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("alert")).toContainText("percentages between 0 and 100");

  page.once("dialog", (confirm) => confirm.accept());
  await page.getByRole("button", { name: "Delete draft" }).click();
  await expect(page.getByRole("heading", { name: "Invoices" })).toBeVisible();
  await page.getByRole("link", { name: "Time", exact: true }).click();
  await expect(workshop.getByRole("button", { name: /^Edit/ })).toBeVisible(); // editable again

  // send, pay, undo the payment
  await draftForBeta(page);
  page.once("dialog", (confirm) => confirm.accept());
  await page.getByRole("button", { name: "Mark as sent" }).click();
  await expect(page.getByRole("heading", { name: /^Invoice INV-\d{4}$/ })).toBeVisible();
  await page.getByRole("button", { name: "Mark as paid" }).click();
  await expect(page.locator(".stamp")).toHaveText("Paid");
  await page.getByRole("button", { name: "Mark as unpaid" }).click();
  await expect(page.locator(".stamp")).toHaveText("Sent");

  // the list filters by status, and billed time is locked
  await page.getByRole("link", { name: "All invoices" }).click();
  await page.getByRole("button", { name: /^Sent/ }).click();
  await expect(page.getByRole("row", { name: /Beta Limited/ })).toContainText("£194.04");
  await page.getByRole("button", { name: /^Paid/ }).click();
  await expect(page.getByRole("row", { name: /Beta Limited/ })).toHaveCount(0);
  await page.getByRole("link", { name: "Time", exact: true }).click();
  await expect(workshop.getByRole("button", { name: /^Edit/ })).toHaveCount(0);
  await expect(workshop.getByRole("link", { name: /^INV-/ })).toBeVisible();

  // a client with history cannot be deleted by accident
  await page.getByRole("link", { name: "Clients", exact: true }).click();
  await page.getByRole("button", { name: "Edit client Beta Limited" }).click();
  page.once("dialog", (confirm) => confirm.accept());
  await dialog.getByRole("button", { name: "Delete client" }).click();
  await expect(dialog.getByRole("alert")).toContainText("projects and invoices first");
});

/** New invoice for Beta Limited from all of its unbilled time. */
async function draftForBeta(page: import("playwright/test").Page) {
  await page.getByRole("link", { name: "Invoices", exact: true }).click();
  await page.getByRole("link", { name: "New invoice" }).click();
  await page.getByLabel("Client").selectOption({ label: "Beta Limited (GBP)" });
  await page.getByRole("button", { name: "Create draft with 2h 30m" }).click();
  await expect(page.getByRole("heading", { name: "Draft invoice" })).toBeVisible();
}
