import assert from "node:assert/strict";
import { test } from "node:test";
import {
  formatMoney,
  hundredthsToInput,
  lineAmount,
  parseHundredths,
  roundDiv,
  totals,
  trimHundredths,
} from "./money.ts";

test("roundDiv rounds half up", () => {
  assert.equal(roundDiv(5, 10), 1);
  assert.equal(roundDiv(4, 10), 0);
  assert.equal(roundDiv(15, 10), 2);
});

test("line amounts and totals match the backend", () => {
  assert.equal(lineAmount(150, 150_000), 225_000);
  assert.equal(lineAmount(33, 9_999), 3_300);
  assert.deepEqual(totals([100_000, 50_000], 1000, 2000), {
    subtotal: 150_000,
    discount: 15_000,
    tax: 27_000,
    total: 162_000,
  });
  assert.equal(totals([10, 20], 0, 1850).tax, 6);
});

test("parseHundredths reads what people type", () => {
  assert.equal(parseHundredths("12"), 1200);
  assert.equal(parseHundredths("12.5"), 1250);
  assert.equal(parseHundredths("12,50"), 1250);
  assert.equal(parseHundredths("0.07"), 7);
  assert.equal(parseHundredths("1,234.56"), 123_456);
  assert.equal(parseHundredths("1.234,56"), 123_456);
  assert.equal(parseHundredths("1.234.567"), 123_456_700);
  assert.equal(parseHundredths("1 500"), 150_000);
  assert.equal(parseHundredths(" ₺1500 "), 150_000);
  assert.equal(parseHundredths("18.5%"), 1850);
  assert.equal(parseHundredths("0.1"), 10);
  assert.equal(parseHundredths("19.99"), 1999); // 19.99 * 100 is 1998.9999999999998 in floats
});

test("parseHundredths rejects what it cannot represent exactly", () => {
  for (const bad of ["", "abc", "-5", "1.234", "1,234", "12.345", "1e3", ".5", "1..2", "1,23,4.5", "1.2.3", "9999999999999"]) {
    assert.equal(parseHundredths(bad), null, bad);
  }
});

test("formatting", () => {
  assert.equal(formatMoney(1_234_567, "TRY"), "₺12,345.67");
  assert.equal(formatMoney(5, "USD"), "$0.05");
  assert.equal(formatMoney(-150, "EUR"), "-€1.50");
  assert.equal(hundredthsToInput(150_000), "1500.00");
  assert.equal(trimHundredths(150), "1.5");
  assert.equal(trimHundredths(200), "2");
  assert.equal(trimHundredths(1850), "18.5");
  assert.equal(trimHundredths(0), "0");
});
