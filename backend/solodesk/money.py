"""Money arithmetic on integer minor units (kuruş, cents, pence). No floats anywhere."""

from dataclasses import dataclass

CURRENCIES = ("TRY", "USD", "EUR", "GBP")
SYMBOLS = {"TRY": "₺", "USD": "$", "EUR": "€", "GBP": "£"}


def round_div(n: int, d: int) -> int:
    """n / d rounded half up, for non-negative n and positive d."""
    return (2 * n + d) // (2 * d)


def minutes_to_hundredths(minutes: int) -> int:
    """Tracked minutes as hours with two decimals: 90 -> 150 (1.50 h)."""
    return round_div(minutes * 100, 60)


def line_amount(quantity_hundredths: int, unit_price_minor: int) -> int:
    return round_div(quantity_hundredths * unit_price_minor, 100)


@dataclass(frozen=True)
class Totals:
    subtotal_minor: int
    discount_minor: int
    tax_minor: int
    total_minor: int


def totals(amounts: list[int], discount_bp: int, tax_rate_bp: int) -> Totals:
    """Discount applies to the subtotal, tax to what is left. Rates are basis points."""
    subtotal = sum(amounts)
    discount = round_div(subtotal * discount_bp, 10_000)
    tax = round_div((subtotal - discount) * tax_rate_bp, 10_000)
    return Totals(subtotal, discount, tax, subtotal - discount + tax)


def decimal_str(minor: int) -> str:
    """1234567 -> '12345.67' (for CSV)."""
    sign = "-" if minor < 0 else ""
    return f"{sign}{abs(minor) // 100}.{abs(minor) % 100:02d}"


def format_money(minor: int, currency: str) -> str:
    """1234567, 'TRY' -> '₺12,345.67'."""
    sign = "-" if minor < 0 else ""
    return f"{sign}{SYMBOLS[currency]}{abs(minor) // 100:,}.{abs(minor) % 100:02d}"
