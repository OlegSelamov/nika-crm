import re


_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def stock_balance_sql(item_alias="i"):
    """Return the canonical stock balance expression for an items table alias."""
    if not _ALIAS_RE.fullmatch(item_alias):
        raise ValueError("Недопустимый SQL-псевдоним товара")
    return f"""
        CASE
            WHEN COALESCE({item_alias}.item_type, 'product') = 'service' THEN 0
            ELSE COALESCE((
                SELECT SUM(
                    CASE
                        WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                        WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                        ELSE 0
                    END
                )
                FROM stock_movements sm
                WHERE sm.company_id = {item_alias}.company_id
                  AND sm.item_id = {item_alias}.id
            ), 0)
        END
    """


def sync_item_quantities(cur, *, company_id=None, item_id=None):
    """
    Refresh the legacy items.quantity cache from the stock movement journal.

    The movement journal is the source of truth.  Keeping this cache aligned is
    still necessary for older exports and integrations that read items.quantity.
    """
    filters = []
    params = []
    if company_id is not None:
        filters.append("i.company_id = %s")
        params.append(company_id)
    if item_id is not None:
        filters.append("i.id = %s")
        params.append(item_id)

    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""
    balance_sql = stock_balance_sql("i")
    cur.execute(
        f"""
        WITH balances AS (
            SELECT
                i.id,
                i.company_id,
                {balance_sql} AS calculated_quantity
            FROM items i
            {where_sql}
        ),
        updated AS (
            UPDATE items target
            SET quantity = balances.calculated_quantity
            FROM balances
            WHERE target.id = balances.id
              AND target.company_id = balances.company_id
              AND target.quantity IS DISTINCT FROM balances.calculated_quantity
            RETURNING target.id
        )
        SELECT COUNT(*) AS updated_count
        FROM updated
        """,
        tuple(params),
    )
    row = cur.fetchone() or {}
    if hasattr(row, "get"):
        return int(row.get("updated_count") or 0)
    return int(row[0] or 0)
