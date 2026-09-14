from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP


def as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}


def calculate_weighted_average(current_stock, current_average, incoming_quantity, incoming_price):
    stock = max(Decimal(str(current_stock or 0)), Decimal("0"))
    average = max(Decimal(str(current_average or 0)), Decimal("0"))
    quantity = Decimal(str(incoming_quantity or 0))
    price = Decimal(str(incoming_price or 0))

    if quantity <= 0:
        raise ValueError("Количество должно быть больше нуля")
    if price < 0:
        raise ValueError("Закупочная цена не может быть отрицательной")

    if stock <= 0 or average <= 0:
        result = price
    else:
        result = ((stock * average) + (quantity * price)) / (stock + quantity)

    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_retail_price(purchase_price, markup_percent):
    price = Decimal(str(purchase_price or 0))
    markup = Decimal(str(markup_percent or 0))
    if price <= 0 or markup <= 0:
        return None
    return (price * (Decimal("1") + markup / Decimal("100"))).quantize(
        Decimal("1"),
        rounding=ROUND_CEILING,
    )


def apply_income_pricing(cur, *, company_id, item_id, quantity, price, update_retail=False):
    """
    Lock the product row and update its moving-average cost before inserting
    the new stock movement. The caller must insert the movement and commit in
    the same transaction.
    """
    cur.execute(
        """
        SELECT
            i.id,
            i.name,
            COALESCE(i.purchase_price, 0) AS purchase_price,
            COALESCE(i.last_purchase_price, i.purchase_price, 0) AS last_purchase_price,
            COALESCE(i.retail_price, 0) AS retail_price,
            COALESCE((
                SELECT c.markup_percent
                FROM categories c
                WHERE c.company_id = i.company_id
                  AND LOWER(COALESCE(c.name, '')) = LOWER(COALESCE(i.category, ''))
                ORDER BY c.id
                LIMIT 1
            ), 0) AS markup_percent,
            COALESCE((
                SELECT SUM(
                    CASE
                        WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                        WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                        ELSE 0
                    END
                )
                FROM stock_movements sm
                WHERE sm.company_id = i.company_id
                  AND sm.item_id = i.id
            ), 0) AS current_stock
        FROM items i
        WHERE i.id = %s
          AND i.company_id = %s
          AND COALESCE(i.item_type, 'product') = 'product'
        FOR UPDATE
        """,
        (item_id, company_id),
    )
    item = cur.fetchone()
    if not item:
        raise ValueError("Товар не найден")

    average_cost = calculate_weighted_average(
        item["current_stock"],
        item["purchase_price"],
        quantity,
        price,
    )
    suggested_retail = calculate_retail_price(price, item["markup_percent"])
    retail_price = (
        suggested_retail
        if update_retail and suggested_retail is not None
        else Decimal(str(item["retail_price"] or 0))
    )

    cur.execute(
        """
        UPDATE items
        SET purchase_price = %s,
            last_purchase_price = %s,
            retail_price = %s
        WHERE id = %s AND company_id = %s
        """,
        (average_cost, price, retail_price, item_id, company_id),
    )

    return {
        "item_name": item["name"],
        "previous_average_cost": Decimal(str(item["purchase_price"] or 0)),
        "average_cost": average_cost,
        "last_purchase_price": Decimal(str(price or 0)),
        "previous_retail_price": Decimal(str(item["retail_price"] or 0)),
        "retail_price": retail_price,
        "markup_percent": Decimal(str(item["markup_percent"] or 0)),
        "retail_updated": bool(update_retail and suggested_retail is not None),
    }
