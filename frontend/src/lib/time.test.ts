import assert from "node:assert/strict";
import { test } from "node:test";
import { addDays, durationToInput, formatClock, formatDuration, parseDuration } from "./time.ts";

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
