// Money, quantities and rates are integers end to end: minor units, hundredths, basis points.
// These functions mirror backend/solodesk/money.py so the live preview matches the saved invoice.

export const CURRENCIES = ["TRY", "USD", "EUR", "GBP"] as const;
export type Currency = (typeof CURRENCIES)[number];
const SYMBOLS: Record<Currency, string> = { TRY: "₺", USD: "$", EUR: "€", GBP: "£" };

/**
 * a * b / d rounded half up, for non-negative integers. The product can pass 2^53 (a large
 * subtotal times a rate in basis points), so the arithmetic is done in BigInt.
 */
export function mulDiv(a: number, b: number, d: number): number {
  return Number((2n * BigInt(a) * BigInt(b) + BigInt(d)) / (2n * BigInt(d)));
}

export function lineAmount(quantityHundredths: number, unitPriceMinor: number): number {
  return mulDiv(quantityHundredths, unitPriceMinor, 100);
}

export function totals(amounts: number[], discountBp: number, taxRateBp: number) {
  const subtotal = amounts.reduce((sum, a) => sum + a, 0);
  const discount = mulDiv(subtotal, discountBp, 10_000);
  const tax = mulDiv(subtotal - discount, taxRateBp, 10_000);
  return { subtotal, discount, tax, total: subtotal - discount + tax };
}

/**
 * "1234.56", "1234,5", "12" or "1,234.56" -> 123456, 123450, 1200, 123456.
 * Works on the digits, never on floats. Returns null for anything that is not a non-negative
 * number with at most two decimals, and for "1.234" or "1,234": that could be one thousand or
 * one and a bit, and guessing wrong would be a thousandfold error.
 */
export function parseHundredths(text: string): number | null {
  const s = text.trim().replace(/[\s₺$€£%]/g, "");
  if (!/^\d+([.,]\d+)*$/.test(s)) return null;
  const groups = s.split(/[.,]/);
  const kinds = new Set(s.replace(/\d/g, ""));
  let fraction = "";
  if (groups.length > 1 && (kinds.size === 2 || groups.length === 2)) {
    fraction = groups.pop()!; // the last separator is the decimal point
    if (fraction.length > 2) return null;
  }
  if (groups.slice(1).some((g) => g.length !== 3)) return null; // thousands come in threes
  const whole = groups.join("");
  if (whole.length > 12) return null;
  return Number(whole) * 100 + Number((fraction + "00").slice(0, 2));
}

/** 123456 -> "1234.56": the plain form used in inputs. */
export function hundredthsToInput(value: number): string {
  return `${Math.floor(value / 100)}.${String(value % 100).padStart(2, "0")}`;
}

/** 150 -> "1.5", 200 -> "2": quantities and percentages without trailing zeros. */
export function trimHundredths(value: number): string {
  return hundredthsToInput(value).replace(/\.?0+$/, "");
}

/** 1234567, "TRY" -> "₺12,345.67" */
export function formatMoney(minor: number, currency: string): string {
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100).toLocaleString("en-US");
  const symbol = SYMBOLS[currency as Currency] ?? `${currency} `;
  return `${minor < 0 ? "-" : ""}${symbol}${whole}.${String(abs % 100).padStart(2, "0")}`;
}
