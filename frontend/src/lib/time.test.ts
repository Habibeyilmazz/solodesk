import assert from "node:assert/strict";
import { test } from "node:test";
import { addDays, addMonths, daysToCover, durationToInput, formatClock, formatDuration, parseDuration } from "./time.ts";

test("parseDuration accepts the usual ways of writing time", () => {
  assert.equal(parseDuration("1:30"), 90);
  assert.equal(parseDuration("0:05"), 5);
  assert.equal(parseDuration("1.5"), 90);
  assert.equal(parseDuration("1,25"), 75);
  assert.equal(parseDuration("2"), 120);
  assert.equal(parseDuration("90m"), 90);
  assert.equal(parseDuration("45 min"), 45);
  assert.equal(parseDuration("2h"), 120);
  assert.equal(parseDuration("2h 15m"), 135);
  assert.equal(parseDuration("24"), 1440);
});

test("parseDuration rejects nonsense and out-of-range values", () => {
  for (const bad of ["", "0", "0:00", "1:75", "25", "abc", "-1", "1h30", "2000m"]) {
    assert.equal(parseDuration(bad), null, bad);
  }
});

test("formatting durations", () => {
  assert.equal(formatDuration(135), "2h 15m");
  assert.equal(formatDuration(45), "45m");
  assert.equal(formatDuration(120), "2h");
  assert.equal(durationToInput(135), "2:15");
  assert.equal(formatClock(3723), "01:02:03");
});

test("addDays crosses month ends", () => {
  assert.equal(addDays("2026-02-27", 2), "2026-03-01");
  assert.equal(addDays("2026-01-01", -1), "2025-12-31");
});

test("daysToCover reaches back to a date in whole pages", () => {
  assert.equal(daysToCover("2026-11-20", 30, "2026-11-22"), 30); // inside the first page
  assert.equal(daysToCover("2026-10-23", 30, "2026-11-22"), 30); // exactly 30 days back
  assert.equal(daysToCover("2026-10-22", 30, "2026-11-22"), 60);
  assert.equal(daysToCover("2026-03-30", 30, "2026-11-22"), 240); // across the DST change
  assert.equal(daysToCover("2026-12-01", 30, "2026-11-22"), 30); // future dates: one page
});

test("addMonths clamps to the month's end, like the server", () => {
  assert.equal(addMonths("2026-01-31", 1), "2026-02-28");
  assert.equal(addMonths("2028-01-31", 1), "2028-02-29");
  assert.equal(addMonths("2026-01-31", 3), "2026-04-30");
  assert.equal(addMonths("2026-11-15", 3), "2027-02-15");
  assert.equal(addMonths("2026-12-01", 12), "2027-12-01");
});
