import { expect, test } from "playwright/test";

// One pass through the job solodesk exists for: client -> project -> time -> invoice -> paid.
test("track time for a client, invoice it and get paid", async ({ page }) => {
  // sign in
  await page.goto("/");
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Wrong password");
  await page.getByLabel("Password").fill("e2e-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Nothing invoiced yet.")).toBeVisible();

  // a client and a project
  await page.getByRole("link", { name: "Clients", exact: true }).click();
  await page.getByRole("button", { name: "New client" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill("Acme Yazılım");
  await dialog.getByLabel("Invoice currency").selectOption("USD");
  await dialog.getByRole("button", { name: "Add client" }).click();
  const client = page.getByRole("region", { name: "Acme Yazılım" });
  await expect(client).toContainText("Billed in USD");

  await client.getByRole("button", { name: "Add project" }).click();
  await dialog.getByLabel("Project name").fill("Website");
  await dialog.getByLabel("Hourly rate (USD)").fill("100");
  await dialog.getByRole("button", { name: "Add project" }).click();
  await expect(client.getByRole("row", { name: /Website/ })).toContainText("$100.00");

  // the timer
  const timer = page.getByRole("region", { name: "Timer" });
  await timer.getByLabel("What are you working on?").fill("Kickoff call");
  await timer.getByRole("button", { name: "Start timer" }).click();
  await expect(timer.getByRole("timer")).toHaveText(/^00:00:0\d$/);
  await expect(timer).toContainText("Kickoff call");
  await timer.getByRole("button", { name: "Stop timer" }).click();
  await expect(timer.getByRole("button", { name: "Start timer" })).toBeVisible();

  // a manual entry
  await page.getByRole("link", { name: "Time", exact: true }).click();
  const add = page.getByRole("region", { name: "Add time by hand" });
  await add.getByLabel("Duration").fill("nonsense");
  await add.getByRole("button", { name: "Add entry" }).click();
  await expect(add.getByRole("alert")).toContainText("Enter a duration");
  await add.getByLabel("Duration").fill("1:30");
  await add.getByLabel("Description").fill("Wireframes");
  await add.getByRole("button", { name: "Add entry" }).click();
  await expect(page.getByRole("row", { name: /Wireframes/ })).toContainText("1h 30m");
  await expect(page.getByRole("row", { name: /Kickoff call/ })).toContainText("1m");

  // invoice the tracked time
  await page.getByRole("link", { name: "Invoices", exact: true }).click();
  await page.getByRole("link", { name: "New invoice" }).click();
  await expect(page.getByRole("row", { name: /Wireframes/ })).toBeVisible();
  await page.getByRole("button", { name: "Create draft with 1h 31m" }).click();
  await expect(page.getByRole("heading", { name: "Draft invoice" })).toBeVisible();
  await expect(page.getByLabel("Line 1 quantity")).toHaveValue("1.52"); // 91 minutes
  await expect(page.getByLabel("Line 1 unit price")).toHaveValue("100.00");

  // add a fixed-price line; the totals follow as you type
  await page.getByRole("button", { name: "Add line" }).click();
  await page.getByLabel("Line 2 description").fill("Hosting, one year");
  await page.getByLabel("Line 2 unit price").fill("48");
  const totals = page.locator(".totals");
  await expect(totals).toContainText("$200.00"); // 152.00 + 48.00
  await expect(totals).toContainText("$40.00"); // 20% tax
  await expect(totals).toContainText("$240.00");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeDisabled();

  // send: the invoice gets its number and locks
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Mark as sent" }).click();
  await expect(page.getByRole("heading", { name: "Invoice INV-0001" })).toBeVisible();
  await expect(page.locator(".stamp")).toHaveText("Sent");

  // the PDF and CSV are real files
  const invoiceId = page.url().split("/").pop();
  const pdf = await page.request.get(`/api/invoices/${invoiceId}/pdf`);
  expect(pdf.headers()["content-type"]).toBe("application/pdf");
  expect((await pdf.body()).subarray(0, 5).toString()).toBe("%PDF-");
  const csv = await (await page.request.get("/api/export/invoices.csv")).text();
  expect(csv).toContain("INV-0001,sent,Acme Yazılım,USD");
  expect(csv).toContain("200.00,0.00,40.00,240.00");

  // get paid
  await page.getByRole("button", { name: "Mark as paid" }).click();
  await expect(page.locator(".stamp")).toHaveText("Paid");

  // the dashboard reflects it
  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(page.getByRole("region", { name: "Revenue, last 12 months" })).toContainText("$200.00");
  await expect(page.getByRole("region", { name: "Unpaid" })).toContainText("$0.00");
  await expect(page.getByRole("region", { name: "Top clients, last 12 months" })).toContainText(
    "Acme Yazılım",
  );
  await expect(page.getByRole("region", { name: "Hours this week" })).toContainText("1h 31m");

  // sign out
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Password")).toBeVisible();
  expect((await page.request.get("/api/clients")).status()).toBe(401);
});
