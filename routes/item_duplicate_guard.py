import hashlib
import re

from flask import g, jsonify, redirect, request, session

from models import get_db, pool
from routes.items import items_bp


_EDIT_ITEM_RE = re.compile(r"^/items/(\d+)/edit$")
_DUPLICATE_FIELDS = (
    ("barcode", "штрихкоду"),
    ("gtin", "GTIN"),
    ("ntin", "NTIN"),
)


def _clean(value):
    return str(value or "").strip()


def _identifier_values(*, barcode="", gtin="", ntin=""):
    values = {
        "barcode": _clean(barcode),
        "gtin": _clean(gtin),
        "ntin": _clean(ntin),
    }
    return [(field, label, values[field]) for field, label in _DUPLICATE_FIELDS if values[field]]


def _lock_key(company_id, field, value):
    raw = f"nika:item:{company_id}:{field}:{value}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big", signed=True)


def _find_duplicate(company_id, *, barcode="", gtin="", ntin="", exclude_id=None, conn=None):
    active = _identifier_values(barcode=barcode, gtin=gtin, ntin=ntin)
    if not active:
        return None

    own_conn = conn is None
    if own_conn:
        conn = get_db()
    cur = conn.cursor()
    try:
        params = [company_id]
        exclude_sql = ""
        if exclude_id:
            exclude_sql = "AND id <> %s"
            params.append(int(exclude_id))

        where_parts = []
        for field, _label, value in active:
            where_parts.append(f"TRIM(COALESCE({field}, '')) = %s")
            params.append(value)

        cur.execute(f"""
            SELECT id, name, barcode, gtin, ntin
            FROM items
            WHERE company_id = %s
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
                    "name": item["name"] or "Товар",
                    "field": field,
                    "field_label": label,
                    "value": value,
                    "barcode": _clean(item.get("barcode")),
                    "gtin": _clean(item.get("gtin")),
                    "ntin": _clean(item.get("ntin")),
                }
        return None
    finally:
        cur.close()
        if own_conn:
            pool.putconn(conn)


def _release_item_locks():
    conn = getattr(g, "_item_duplicate_lock_conn", None)
    keys = getattr(g, "_item_duplicate_lock_keys", None) or []
    if not conn:
        return
    try:
        cur = conn.cursor()
        for key in reversed(keys):
            cur.execute("SELECT pg_advisory_unlock(%s)", (key,))
        conn.commit()
        cur.close()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        pool.putconn(conn)
        g._item_duplicate_lock_conn = None
        g._item_duplicate_lock_keys = []


@items_bp.route("/api/items/check-duplicate", methods=["GET"])
def api_item_duplicate_check():
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    exclude_id = request.args.get("exclude_id", type=int)
    duplicate = _find_duplicate(
        company_id,
        barcode=request.args.get("barcode"),
        gtin=request.args.get("gtin"),
        ntin=request.args.get("ntin"),
        exclude_id=exclude_id,
    )
    return jsonify({
        "success": True,
        "duplicate": bool(duplicate),
        "item": duplicate,
    })


@items_bp.before_app_request
def prevent_duplicate_item_submit():
    """Block duplicate product identifiers even when two devices submit at almost the same time."""
    if request.method != "POST" or not session.get("company_id"):
        return None

    edit_match = _EDIT_ITEM_RE.match(request.path)
    if request.path != "/items/add" and not edit_match:
        return None

    item_type = "service" if request.form.get("item_type") == "service" else "product"
    if item_type != "product":
        return None

    company_id = session.get("company_id")
    barcode = request.form.get("barcode")
    gtin = request.form.get("gtin")
    ntin = request.form.get("ntin")
    active = _identifier_values(barcode=barcode, gtin=gtin, ntin=ntin)
    if not active:
        return None

    # Session-level PostgreSQL advisory locks serialize creates/edits sharing
    # any identifier. This closes the race where two devices pass a normal
    # SELECT check before either INSERT is committed.
    conn = get_db()
    cur = conn.cursor()
    keys = sorted({_lock_key(company_id, field, value) for field, _label, value in active})
    try:
        for key in keys:
            cur.execute("SELECT pg_advisory_lock(%s)", (key,))
        g._item_duplicate_lock_conn = conn
        g._item_duplicate_lock_keys = keys
    except Exception:
        cur.close()
        pool.putconn(conn)
        raise
    finally:
        if not cur.closed:
            cur.close()

    exclude_id = int(edit_match.group(1)) if edit_match else None
    duplicate = _find_duplicate(
        company_id,
        barcode=barcode,
        gtin=gtin,
        ntin=ntin,
        exclude_id=exclude_id,
        conn=conn,
    )
    if not duplicate:
        # Keep locks until the original items.add_item/edit_item request commits.
        return None

    return redirect(
        f"/items/{duplicate['id']}/edit?duplicate=1&duplicate_field={duplicate['field']}"
    )


@items_bp.after_app_request
def inject_item_duplicate_guard(response):
    if request.method == "GET" and (request.path == "/items/add" or _EDIT_ITEM_RE.match(request.path)):
        if "text/html" in response.headers.get("Content-Type", "").lower():
            try:
                html = response.get_data(as_text=True)
                marker = "item_duplicate_guard.js?v=20260911-1"
                if marker not in html and "</body>" in html:
                    html = html.replace(
                        "</body>",
                        f'<script src="/static/js/{marker}"></script>\n</body>',
                        1,
                    )
                    response.set_data(html)
            except Exception as exc:
                print("ITEM DUPLICATE GUARD INJECT ERROR:", exc)

    _release_item_locks()
    return response


@items_bp.teardown_app_request
def release_item_duplicate_locks_on_teardown(_error):
    _release_item_locks()
