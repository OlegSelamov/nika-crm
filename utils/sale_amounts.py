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


def discount_sale_rows(item, unit=None):
    """Validate the checkout quote and produce persisted (sometimes split) rows.

    A fixed-tenge discount applies to a *line total*. For integer quantities,
    split a line when needed so every reKassa unit price and sum agrees to the
    tiyn. Splitting never changes the quantity sold or discount paid.
    """
    ordinary_price, ordinary_qty, ordinary_total = normalize_sale_line(item, unit)
    has_base = "base_price" in item
    has_discount = (
        "discount_percent" in item or
        "discount_amount" in item or
        "discount_type" in item
    )
    if not has_base and not has_discount:
        return [{
            "price": ordinary_price, "qty": ordinary_qty, "total": ordinary_total,
            "base_price": None, "discount_amount": Decimal("0"),
            "discount_percent": None, "discount_type": None,
        }]
    if not has_base:
        raise ValueError("У скидки отсутствует исходная цена.")
    base = _decimal(item.get("base_price"), None)
    price = _decimal(item.get("price"), None)
    qty = _decimal(item.get("qty", 1), None)
    if base is None or price is None or qty is None or base < 0 or price < 0 or qty <= 0:
        raise ValueError("Проверьте исходную цену, количество и скидку.")
    kind = str(item.get("discount_type") or "percent").lower()
    if kind not in ("percent", "amount"):
        raise ValueError("Неизвестный вид скидки.")
    measured = normalize_unit(unit or item.get("unit")) in MEASURED_UNITS
    quant = Decimal("1") if measured else Decimal("0.01")
    base_total = (base * qty).quantize(quant, rounding=ROUND_HALF_UP)

    if kind == "percent":
        percent = _decimal(item.get("discount_percent"), None)
        if (percent is None or percent < 0 or percent > 100
                or percent != percent.to_integral_value()):
            raise ValueError("Скидка должна быть целым процентом от 0 до 100.")
        quoted = (base * (Decimal("100") - percent) / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(quoted - price) > Decimal("0.009"):
            raise ValueError("Цена не совпадает со скидкой. Обновите корзину.")
        netprice, quantity, total = normalize_sale_line(dict(item, price=str(quoted)), unit)
        saved = (base_total - total).quantize(Decimal("0.01"))
        return [{
            "price": netprice, "qty": quantity, "total": total,
            "base_price": base, "discount_amount": max(saved, Decimal("0")),
            "discount_percent": percent, "discount_type": "percent",
        }]

    amount = _decimal(item.get("discount_amount"), None)
    if amount is None or amount < 0 or amount > base_total:
        raise ValueError("Скидка в тенге не может превышать стоимость позиции.")
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    desired = (base_total - amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    requested = _decimal(item.get("line_total"), None)
    if requested is None or abs(requested - desired) > Decimal("0.009"):
        raise ValueError("Сумма скидки не совпадает с итогом позиции.")
    quoted = (desired / qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(quoted - price) > Decimal("0.009"):
        # When the unit is weighted, the fiscal total is rounded to the whole
        # tenge. A catalog unit reduction can yield an exact net sum even
        # though desired/quantity is not the original discounted unit rate.
        measured_total = (price * qty).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if not measured or measured_total != desired:
            raise ValueError("Цена не совпадает со скидкой в тенге.")
    # Ordinary multi-unit goods may require two fiscal prices, e.g.
    # 3 × 1 000 ₸ − 50 ₸ = 2 × 983.33 ₸ + 1 × 983.34 ₸.
    if not measured and qty == qty.to_integral_value() and qty > 1:
        count = int(qty)
        cents = int(desired * 100)
        low = cents // count
        high_units = cents - low * count
        rows = []
        for units, unit_cents in ((count - high_units, low), (high_units, low + 1)):
            if not units:
                continue
            unit_price = Decimal(unit_cents) / Decimal("100")
            rowqty = Decimal(units)
            rowtotal = unit_price * rowqty
            rows.append({
                "price": unit_price, "qty": rowqty, "total": rowtotal,
                "base_price": base,
                "discount_amount": max(base * rowqty - rowtotal, Decimal("0")),
                "discount_percent": None, "discount_type": "amount",
            })
        return rows
    return [{
        "price": quoted, "qty": qty, "total": desired,
        "base_price": base, "discount_amount": amount,
        "discount_percent": None, "discount_type": "amount",
    }]


def normalize_discounted_sale_line(item, unit=None):
    """Compatibility wrapper for consumers that only need a priced line."""
    rows = discount_sale_rows(item, unit)
    if len(rows) != 1:
        raise ValueError("Денежную скидку на несколько единиц необходимо разделить по строкам.")
    row = rows[0]
    return row["price"], row["qty"], row["total"]
