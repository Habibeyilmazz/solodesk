from solodesk.money import (
    decimal_str,
    format_money,
    line_amount,
    minutes_to_hundredths,
    round_div,
    totals,
)


def test_round_div_rounds_half_up():
    assert round_div(5, 10) == 1
    assert round_div(4, 10) == 0
    assert round_div(15, 10) == 2
    assert round_div(0, 7) == 0


def test_minutes_become_hours_with_two_decimals():
    assert minutes_to_hundredths(90) == 150
    assert minutes_to_hundredths(20) == 33
    assert minutes_to_hundredths(40) == 67
    assert minutes_to_hundredths(1) == 2


def test_line_amount_is_quantity_times_price():
    assert line_amount(150, 150_000) == 225_000  # 1.5 h at 1,500.00
    assert line_amount(33, 9_999) == 3_300  # 0.33 x 99.99 = 32.9967 -> 33.00
    assert line_amount(1, 50) == 1  # 0.01 x 0.50 = 0.005 -> 0.01


def test_totals_discount_before_tax():
    t = totals([100_000, 50_000], discount_bp=1000, tax_rate_bp=2000)
    assert (t.subtotal_minor, t.discount_minor, t.tax_minor, t.total_minor) == (
        150_000,
        15_000,
        27_000,
        162_000,
    )


def test_totals_never_lose_a_minor_unit():
    # 0.1 + 0.2 style sums are exact in integers; 1/3 style rates round once, half up
    t = totals([10, 20], discount_bp=0, tax_rate_bp=1850)
    assert t.tax_minor == 6  # 30 x 18.5% = 5.55 -> 6
    assert t.total_minor == t.subtotal_minor - t.discount_minor + t.tax_minor


def test_totals_of_nothing():
    assert totals([], 500, 2000).total_minor == 0


def test_formatting():
    assert format_money(1_234_567, "TRY") == "₺12,345.67"
    assert format_money(5, "USD") == "$0.05"
    assert format_money(-150, "EUR") == "-€1.50"
    assert decimal_str(1_234_567) == "12345.67"
    assert decimal_str(-5) == "-0.05"
