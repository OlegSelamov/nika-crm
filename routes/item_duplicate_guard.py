import re

from flask import jsonify, redirect, request, session

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


def _find_duplicate(company_id, *, barcode="", gtin="", ntin="", exclude_id=None):
    values = {
        "barcode": _clean(barcode),
        "gtin": _clean(gtin),
        "ntin": _clean(ntin),
    }
    active = [(field, label, value) for field, label in _DUPLICATE_FIELDS if (value := values[field])]
    if not active:
        return None

    where_parts = []
    params = [company_id]
    for field, _label, value in active:
        where_parts.append(f"TRIM(COALESCE({field}, '')) = %s")
        params.append(value)

    exclude_sql = ""
    if exclude_id:
        exclude_sql = "AND id <> %s"
        params.append(int(exclude_id))

    conn = get_db()
    cur = conn.cursor()
    try:
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
        pool.putconn(conn)


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
    """Final server-side guard in case UI checks are bypassed or two devices submit at once."""
    if request.method != "POST" or not session.get("company_id"):
        return None

    edit_match = _EDIT_ITEM_RE.match(request.path)
    if request.path != "/items/add" and not edit_match:
        return None

    item_type = "service" if request.form.get("item_type") == "service" else "product"
    if item_type != "product":
        return None

    exclude_id = int(edit_match.group(1)) if edit_match else None
    duplicate = _find_duplicate(
        session.get("company_id"),
        barcode=request.form.get("barcode"),
        gtin=request.form.get("gtin"),
        ntin=request.form.get("ntin"),
        exclude_id=exclude_id,
    )
    if not duplicate:
        return None

    return redirect(
        f"/items/{duplicate['id']}/edit?duplicate=1&duplicate_field={duplicate['field']}"
    )


@items_bp.after_app_request
def inject_item_duplicate_guard(response):
    if request.method != "GET":
        return response
    if request.path != "/items/add" and not _EDIT_ITEM_RE.match(request.path):
        return response
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        return response

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
    return response
