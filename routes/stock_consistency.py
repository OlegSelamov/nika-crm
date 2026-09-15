import re
from decimal import Decimal

from flask import jsonify, redirect, request, session

from models import get_db, pool
from routes.stock import stock_bp


_EDIT_ITEM_RE = re.compile(r"^/items/(\d+)/edit$")
_API_ITEM_RE = re.compile(r"^/api/items/(\d+)$")
_IDENTIFIER_FIELDS = (
    ("barcode", "штрихкод"),
    ("gtin", "GTIN"),
    ("ntin", "NTIN"),
)


def _clean(value):
    return str(value or "").strip()


def _ledger_expression(item_alias="i"):
    return f"""
        COALESCE((
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
    """


def _repair_quantity_cache(cur, company_id=None):
    ledger = _ledger_expression("i")
    company_sql = "AND i.company_id = %s" if company_id is not None else ""
    params = (company_id,) if company_id is not None else ()
    cur.execute(f"""
        UPDATE items i
        SET quantity = {ledger}
        WHERE COALESCE(i.item_type, 'product') = 'product'
          {company_sql}
          AND COALESCE(i.quantity, 0) IS DISTINCT FROM {ledger}
    """, params)
    return cur.rowcount


def _duplicate_group_count(cur, company_id=None):
    company_sql = "AND company_id = %s" if company_id is not None else ""
    params = (company_id, company_id, company_id) if company_id is not None else ()
    cur.execute(f"""
        WITH identifiers AS (
            SELECT company_id, 'barcode' AS field, TRIM(barcode) AS value
            FROM items
            WHERE COALESCE(item_type, 'product') = 'product'
              AND NULLIF(TRIM(COALESCE(barcode, '')), '') IS NOT NULL
              {company_sql}
            UNION ALL
            SELECT company_id, 'gtin' AS field, TRIM(gtin) AS value
            FROM items
            WHERE COALESCE(item_type, 'product') = 'product'
              AND NULLIF(TRIM(COALESCE(gtin, '')), '') IS NOT NULL
              {company_sql}
            UNION ALL
            SELECT company_id, 'ntin' AS field, TRIM(ntin) AS value
            FROM items
            WHERE COALESCE(item_type, 'product') = 'product'
              AND NULLIF(TRIM(COALESCE(ntin, '')), '') IS NOT NULL
              {company_sql}
        )
        SELECT COUNT(*) AS total
        FROM (
            SELECT company_id, field, value
            FROM identifiers
            GROUP BY company_id, field, value
            HAVING COUNT(*) > 1
        ) duplicate_groups
    """, params)
    row = cur.fetchone() or {}
    return int(row.get("total") or 0)


def install_stock_consistency():
    """Make stock_movements the source of truth and keep items.quantity as a cache."""
    conn = get_db()
    cur = conn.cursor()
    try:
        # Multiple Gunicorn workers may import this module together. Serialize the
        # lightweight migration so trigger creation/backfill happens once at a time.
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("nika:stock-consistency:install",))

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_movements_company_item
            ON stock_movements (company_id, item_id)
        """)

        cur.execute("""
            CREATE OR REPLACE FUNCTION nika_recalc_item_quantity(
                p_company_id INTEGER,
                p_item_id INTEGER
            ) RETURNS VOID AS $$
            BEGIN
                UPDATE items i
                SET quantity = COALESCE((
                    SELECT SUM(
                        CASE
                            WHEN sm.movement_type IN ('income', 'refund') THEN sm.quantity
                            WHEN sm.movement_type IN ('sale', 'writeoff') THEN -sm.quantity
                            ELSE 0
                        END
                    )
                    FROM stock_movements sm
                    WHERE sm.company_id = p_company_id
                      AND sm.item_id = p_item_id
                ), 0)
                WHERE i.company_id = p_company_id
                  AND i.id = p_item_id
                  AND COALESCE(i.item_type, 'product') = 'product';
            END;
            $$ LANGUAGE plpgsql
        """)

        cur.execute("""
            CREATE OR REPLACE FUNCTION nika_stock_movement_sync_item_quantity()
            RETURNS TRIGGER AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    PERFORM nika_recalc_item_quantity(OLD.company_id, OLD.item_id);
                    RETURN OLD;
                END IF;

                IF TG_OP = 'UPDATE'
                   AND (OLD.company_id IS DISTINCT FROM NEW.company_id
                        OR OLD.item_id IS DISTINCT FROM NEW.item_id) THEN
                    PERFORM nika_recalc_item_quantity(OLD.company_id, OLD.item_id);
                END IF;

                PERFORM nika_recalc_item_quantity(NEW.company_id, NEW.item_id);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)

        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_trigger
                    WHERE tgname = 'trg_nika_stock_movement_sync_quantity'
                      AND tgrelid = 'stock_movements'::regclass
                      AND NOT tgisinternal
                ) THEN
                    CREATE TRIGGER trg_nika_stock_movement_sync_quantity
                    AFTER INSERT OR UPDATE OR DELETE ON stock_movements
                    FOR EACH ROW
                    EXECUTE FUNCTION nika_stock_movement_sync_item_quantity();
                END IF;
            END $$
        """)

        # Database-level protection covers web, Flutter, imports and any future API.
        # Advisory transaction locks close the race where two devices create the
        # same identifier at exactly the same time.
        cur.execute("""
            CREATE OR REPLACE FUNCTION nika_guard_item_identifiers()
            RETURNS TRIGGER AS $$
            DECLARE
                v_value TEXT;
                v_duplicate_id INTEGER;
                v_check_all BOOLEAN;
            BEGIN
                IF COALESCE(NEW.item_type, 'product') <> 'product' OR NEW.company_id IS NULL THEN
                    RETURN NEW;
                END IF;

                v_check_all := TG_OP = 'INSERT'
                    OR (TG_OP = 'UPDATE' AND (
                        COALESCE(OLD.item_type, 'product') <> 'product'
                        OR OLD.company_id IS DISTINCT FROM NEW.company_id
                    ));

                IF v_check_all OR (TG_OP = 'UPDATE' AND TRIM(COALESCE(OLD.barcode, '')) IS DISTINCT FROM TRIM(COALESCE(NEW.barcode, ''))) THEN
                    v_value := TRIM(COALESCE(NEW.barcode, ''));
                    IF v_value <> '' THEN
                        PERFORM pg_advisory_xact_lock(hashtextextended('nika:item:' || NEW.company_id || ':barcode:' || v_value, 0));
                        SELECT id INTO v_duplicate_id
                        FROM items
                        WHERE company_id = NEW.company_id
                          AND id <> COALESCE(NEW.id, 0)
                          AND COALESCE(item_type, 'product') = 'product'
                          AND TRIM(COALESCE(barcode, '')) = v_value
                        ORDER BY id
                        LIMIT 1;
                        IF v_duplicate_id IS NOT NULL THEN
                            RAISE EXCEPTION 'Товар с таким штрихкодом уже существует (ID %)', v_duplicate_id
                                USING ERRCODE = '23505';
                        END IF;
                    END IF;
                END IF;

                v_duplicate_id := NULL;
                IF v_check_all OR (TG_OP = 'UPDATE' AND TRIM(COALESCE(OLD.gtin, '')) IS DISTINCT FROM TRIM(COALESCE(NEW.gtin, ''))) THEN
                    v_value := TRIM(COALESCE(NEW.gtin, ''));
                    IF v_value <> '' THEN
                        PERFORM pg_advisory_xact_lock(hashtextextended('nika:item:' || NEW.company_id || ':gtin:' || v_value, 0));
                        SELECT id INTO v_duplicate_id
                        FROM items
                        WHERE company_id = NEW.company_id
                          AND id <> COALESCE(NEW.id, 0)
                          AND COALESCE(item_type, 'product') = 'product'
                          AND TRIM(COALESCE(gtin, '')) = v_value
                        ORDER BY id
                        LIMIT 1;
                        IF v_duplicate_id IS NOT NULL THEN
                            RAISE EXCEPTION 'Товар с таким GTIN уже существует (ID %)', v_duplicate_id
                                USING ERRCODE = '23505';
                        END IF;
                    END IF;
                END IF;

                v_duplicate_id := NULL;
                IF v_check_all OR (TG_OP = 'UPDATE' AND TRIM(COALESCE(OLD.ntin, '')) IS DISTINCT FROM TRIM(COALESCE(NEW.ntin, ''))) THEN
                    v_value := TRIM(COALESCE(NEW.ntin, ''));
                    IF v_value <> '' THEN
                        PERFORM pg_advisory_xact_lock(hashtextextended('nika:item:' || NEW.company_id || ':ntin:' || v_value, 0));
                        SELECT id INTO v_duplicate_id
                        FROM items
                        WHERE company_id = NEW.company_id
                          AND id <> COALESCE(NEW.id, 0)
                          AND COALESCE(item_type, 'product') = 'product'
                          AND TRIM(COALESCE(ntin, '')) = v_value
                        ORDER BY id
                        LIMIT 1;
                        IF v_duplicate_id IS NOT NULL THEN
                            RAISE EXCEPTION 'Товар с таким NTIN уже существует (ID %)', v_duplicate_id
                                USING ERRCODE = '23505';
                        END IF;
                    END IF;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)

        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_trigger
                    WHERE tgname = 'trg_nika_guard_item_identifiers'
                      AND tgrelid = 'items'::regclass
                      AND NOT tgisinternal
                ) THEN
                    CREATE TRIGGER trg_nika_guard_item_identifiers
                    BEFORE INSERT OR UPDATE ON items
                    FOR EACH ROW
                    EXECUTE FUNCTION nika_guard_item_identifiers();
                END IF;
            END $$
        """)

        repaired = _repair_quantity_cache(cur)
        duplicate_groups = _duplicate_group_count(cur)
        conn.commit()
        if repaired:
            print("STOCK CONSISTENCY REPAIRED ITEMS:", repaired)
        if duplicate_groups:
            print("STOCK CONSISTENCY DUPLICATE GROUPS:", duplicate_groups)
    except Exception as exc:
        conn.rollback()
        print("STOCK CONSISTENCY INSTALL ERROR:", exc)
    finally:
        try:
            cur.close()
        except Exception:
            pass
        pool.putconn(conn)


def _find_duplicate(company_id, *, barcode="", gtin="", ntin="", exclude_id=None):
    values = {
        "barcode": _clean(barcode),
        "gtin": _clean(gtin),
        "ntin": _clean(ntin),
    }
    active = [(field, label, values[field]) for field, label in _IDENTIFIER_FIELDS if values[field]]
    if not active:
        return None

    params = [company_id]
    exclude_sql = ""
    if exclude_id is not None:
        exclude_sql = "AND id <> %s"
        params.append(exclude_id)

    where_parts = []
    for field, _label, value in active:
        where_parts.append(f"TRIM(COALESCE({field}, '')) = %s")
        params.append(value)

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT id, name, barcode, gtin, ntin
            FROM items
            WHERE company_id = %s
              AND COALESCE(item_type, 'product') = 'product'
              {exclude_sql}
              AND ({' OR '.join(where_parts)})
            ORDER BY id
            LIMIT 1
        """, tuple(params))
        item = cur.fetchone()
        if not item:
            return None
        for field, label, value in active:
            if _clean(item.get(field)) == value:
                return {
                    "id": item["id"],
                    "name": item.get("name") or "Товар",
                    "field": field,
                    "field_label": label,
                    "value": value,
                }
        return None
    finally:
        cur.close()
        pool.putconn(conn)


@stock_bp.before_app_request
def friendly_item_duplicate_guard():
    """Return a readable duplicate error before the database trigger has to."""
    if request.method not in ("POST", "PATCH"):
        return None

    edit_match = _EDIT_ITEM_RE.match(request.path)
    api_match = _API_ITEM_RE.match(request.path)
    is_web_create = request.path == "/items/add" and request.method == "POST"
    is_api_create = request.path == "/api/items/create" and request.method == "POST"
    is_web_edit = bool(edit_match) and request.method == "POST"
    is_api_edit = bool(api_match) and request.method == "PATCH"
    if not (is_web_create or is_api_create or is_web_edit or is_api_edit):
        return None

    company_id = session.get("company_id")
    if not company_id:
        return None

    payload = (request.get_json(silent=True) or {}) if request.is_json else request.form
    exclude_id = int(edit_match.group(1)) if edit_match else (int(api_match.group(1)) if api_match else None)

    item_type = payload.get("item_type")
    if item_type is None and exclude_id is not None:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT COALESCE(item_type, 'product') AS item_type FROM items WHERE id = %s AND company_id = %s",
                (exclude_id, company_id),
            )
            row = cur.fetchone()
            item_type = row.get("item_type") if row else "product"
        finally:
            cur.close()
            pool.putconn(conn)

    if item_type == "service":
        return None

    duplicate = _find_duplicate(
        company_id,
        barcode=payload.get("barcode"),
        gtin=payload.get("gtin"),
        ntin=payload.get("ntin"),
        exclude_id=exclude_id,
    )
    if not duplicate:
        return None

    if request.path.startswith("/api/") or request.is_json:
        return jsonify({
            "success": False,
            "error": f"Товар с таким {duplicate['field_label']} уже существует",
            "code": "duplicate_item_identifier",
            "duplicate": duplicate,
        }), 409

    return redirect(
        f"/items/{duplicate['id']}/edit?duplicate=1&duplicate_field={duplicate['field']}"
    )


def _to_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


@stock_bp.route("/api/stock/consistency")
def api_stock_consistency():
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    ledger = _ledger_expression("i")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*) AS total
            FROM items
            WHERE company_id = %s
              AND COALESCE(item_type, 'product') = 'product'
        """, (company_id,))
        total_products = int((cur.fetchone() or {}).get("total") or 0)

        cur.execute(f"""
            SELECT
                i.id,
                i.name,
                i.barcode,
                COALESCE(i.quantity, 0) AS cached_quantity,
                {ledger} AS ledger_quantity
            FROM items i
            WHERE i.company_id = %s
              AND COALESCE(i.item_type, 'product') = 'product'
              AND COALESCE(i.quantity, 0) IS DISTINCT FROM {ledger}
            ORDER BY i.id
            LIMIT 200
        """, (company_id,))
        mismatches = []
        for row in cur.fetchall():
            item = dict(row)
            item["cached_quantity"] = _to_number(item.get("cached_quantity"))
            item["ledger_quantity"] = _to_number(item.get("ledger_quantity"))
            mismatches.append(item)

        cur.execute("""
            WITH identifiers AS (
                SELECT id, name, 'barcode' AS field, TRIM(barcode) AS value
                FROM items
                WHERE company_id = %s
                  AND COALESCE(item_type, 'product') = 'product'
                  AND NULLIF(TRIM(COALESCE(barcode, '')), '') IS NOT NULL
                UNION ALL
                SELECT id, name, 'gtin' AS field, TRIM(gtin) AS value
                FROM items
                WHERE company_id = %s
                  AND COALESCE(item_type, 'product') = 'product'
                  AND NULLIF(TRIM(COALESCE(gtin, '')), '') IS NOT NULL
                UNION ALL
                SELECT id, name, 'ntin' AS field, TRIM(ntin) AS value
                FROM items
                WHERE company_id = %s
                  AND COALESCE(item_type, 'product') = 'product'
                  AND NULLIF(TRIM(COALESCE(ntin, '')), '') IS NOT NULL
            )
            SELECT
                field,
                value,
                COUNT(*) AS count,
                ARRAY_AGG(id ORDER BY id) AS item_ids,
                ARRAY_AGG(name ORDER BY id) AS item_names
            FROM identifiers
            GROUP BY field, value
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, field, value
            LIMIT 200
        """, (company_id, company_id, company_id))
        duplicate_groups = [dict(row) for row in cur.fetchall()]

        cur.execute(f"""
            SELECT COUNT(*) AS total
            FROM items i
            WHERE i.company_id = %s
              AND COALESCE(i.item_type, 'product') = 'product'
              AND {ledger} < 0
        """, (company_id,))
        negative_stock = int((cur.fetchone() or {}).get("total") or 0)

        return jsonify({
            "success": True,
            "total_products": total_products,
            "quantity_mismatch_count": len(mismatches),
            "quantity_mismatches": mismatches,
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_groups": duplicate_groups,
            "negative_stock_count": negative_stock,
            "source_of_truth": "stock_movements",
        })
    finally:
        cur.close()
        pool.putconn(conn)


@stock_bp.route("/api/stock/consistency/repair", methods=["POST"])
def api_repair_stock_consistency():
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    conn = get_db()
    cur = conn.cursor()
    try:
        repaired = _repair_quantity_cache(cur, company_id)
        conn.commit()
        return jsonify({
            "success": True,
            "repaired": repaired,
            "message": "Кэш остатков синхронизирован с журналом движений",
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


install_stock_consistency()
