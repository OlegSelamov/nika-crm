import os

import requests
from flask import jsonify, request, session

from routes.items import items_bp


NKT_APPLICATIONS_URL = "https://nationalcatalog.kz/personal-account/personal-applications"
NKT_LOOKUP_URL = "https://e-catalog.gov.kz/api/integration/ofd/search_ofd/"


def _first_product(payload):
    if not payload:
        return None
    if isinstance(payload, list):
        return payload[0] if payload else None
    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get("results"), list):
        return payload["results"][0] if payload["results"] else None

    data = payload.get("data")
    if isinstance(data, list):
        return data[0] if data else None
    if isinstance(data, dict):
        return data

    # Some versions of the integration endpoint return the product itself.
    product_keys = {"name_ru", "name", "gtin", "ntin_code", "ntin"}
    if product_keys.intersection(payload.keys()):
        return payload
    return None


@items_bp.route("/api/nkt/lookup/<path:code>", methods=["GET"])
def api_nkt_lookup(code):
    """Check a product in NKT without making registration mandatory for Nika."""
    if not session.get("company_id"):
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    code = str(code or "").strip()
    if not code:
        return jsonify({"success": False, "error": "Укажите штрихкод, GTIN или NTIN"}), 400

    token = os.getenv("NCT_API_TOKEN")
    if not token:
        return jsonify({
            "success": False,
            "available": False,
            "error": "Проверка НКТ временно не настроена",
            "registration_url": NKT_APPLICATIONS_URL,
        }), 503

    try:
        response = requests.get(
            NKT_LOOKUP_URL,
            params={"tin": code},
            headers={"Authorization": f"JWT {token}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        product = _first_product(payload)

        if not product:
            return jsonify({
                "success": True,
                "found": False,
                "registration_url": NKT_APPLICATIONS_URL,
            })

        ntin = str(product.get("ntin_code") or product.get("ntin") or "").strip()
        gtin = str(product.get("gtin") or "").strip()
        name = str(product.get("name_ru") or product.get("name") or "").strip()

        # Empty objects or service messages are not a product match.
        if not any((ntin, gtin, name)):
            return jsonify({
                "success": True,
                "found": False,
                "registration_url": NKT_APPLICATIONS_URL,
            })

        return jsonify({
            "success": True,
            "found": True,
            "name": name,
            "gtin": gtin,
            "ntin": ntin,
            "measure": product.get("measure") or "",
            "is_marked": bool(product.get("is_markedeac", False)),
            "registration_url": NKT_APPLICATIONS_URL,
        })
    except Exception as exc:
        print("NKT LOOKUP ERROR:", exc)
        return jsonify({
            "success": False,
            "available": False,
            "error": "Не удалось проверить товар в НКТ",
            "registration_url": NKT_APPLICATIONS_URL,
        }), 502


@items_bp.after_app_request
def inject_nkt_item_helper(response):
    if request.method != "GET":
        return response
    if request.path != "/items/add" and not (
        request.path.startswith("/items/") and request.path.endswith("/edit")
    ):
        return response
    if "text/html" not in response.headers.get("Content-Type", "").lower():
        return response

    try:
        html = response.get_data(as_text=True)
        marker = "nkt_item_helper.js?v=20260911-1"
        if marker not in html and "</body>" in html:
            html = html.replace(
                "</body>",
                f'<script src="/static/js/{marker}"></script>\n</body>',
                1,
            )
            response.set_data(html)
    except Exception as exc:
        print("NKT ITEM HELPER INJECT ERROR:", exc)
    return response
