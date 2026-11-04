from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MEASURED_UNITS = {
    "кг", "килограмм", "килограммы",
    "г", "гр", "грамм", "граммы",
    "л", "литр", "литры",
    "мл", "миллилитр", "миллилитры",
    "час", "ч", "часа", "часов",
}

EXACT_AMOUNT_UNITS = MEASURED_UNITS - {"час", "ч", "часа", "часов"}

FINE_MEASURED_UNITS = {
    "кг", "килограмм", "килограммы",
    "л", "литр", "литры",
}


def normalize_unit(unit):
    return str(unit or "шт").strip().lower()


def _decimal(value, default):
    if value in (None, ""):
        return default
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default
    return number if number.is_finite() else default


def normalize_sale_line(item, unit=None):
    """Return trusted price, quantity and line total for a sale cart row.

    Measured goods are charged in whole tenge. The UI may send ``line_total``
    when the cashier sells for an exact amount (for example, exactly 1000 ₸).
    That amount is accepted only when it is close enough to the catalog
    calculation to be explained by rounding the measured quantity.
    """
    price = _decimal(item.get("price"), Decimal("0"))
    quantity = _decimal(item.get("qty"), Decimal("1"))
    normalized_unit = normalize_unit(unit or item.get("unit"))
    measured = normalized_unit in MEASURED_UNITS
    calculated = price * quantity

    total = calculated.quantize(
        Decimal("1") if measured else Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    requested = item.get("line_total")
    if normalized_unit in EXACT_AMOUNT_UNITS and requested not in (None, ""):
        requested_total = _decimal(requested, total).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
        resolution = Decimal("0.001") if normalized_unit in FINE_MEASURED_UNITS else Decimal("1")
        allowed_difference = max(
            Decimal("1"),
            abs(price) * resolution / Decimal("2") + Decimal("0.01"),
        )
        if requested_total > 0 and abs(requested_total - calculated) <= allowed_difference:
            total = requested_total

    return price, quantity, total


def normalize_discounted_sale_line(item, unit=None):
    """Verify a retail cashier's discount snapshot before recording a sale.

    base_price and discount_percent are sent together by updated POS clients.
    Legacy carts (including food modifiers) still use their recorded price.
    The original quoted price stays fixed for offline replay; never apply the
    discount twice or silently change the amount after a POS charge.
    """
    if "base_price" not in item and "discount_percent" not in item:
        return normalize_sale_line(item, unit)
    if "base_price" not in item or "discount_percent" not in item:
        raise ValueError("У скидки отсутствует исходная цена или процент.")
    base = _decimal(item["base_price"], None)
    discount = _decimal(item["discount_percent"], None)
    submitted_price = _decimal(item.get("price"), None)
    if (base is None or discount is None or submitted_price is None
            or base < 0 or discount < 0 or discount > 100
            or discount != discount.to_integral_value()):
        raise ValueError("Скидка должна быть целым процентом от 0 до 100.")
    expected_price = (base * (Decimal("100") - discount) / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    if abs(expected_price - submitted_price) > Decimal("0.009"):
        raise ValueError("Цена не совпадает со скидкой. Обновите корзину перед оплатой.")
    discounted = dict(item, price=str(expected_price))
    return normalize_sale_line(discounted, unit)
