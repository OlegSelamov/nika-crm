from flask import Blueprint, jsonify, request, session

from models import get_db, pool
from services.fiscal_service import provider_context, fiscalize_sale


fiscal_bp = Blueprint("fiscal", __name__)


def _company_id():
    return session.get("company_id")


def _auth_error():
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Требуется войти в систему"}), 401
    if not _company_id():
        return jsonify({"success": False, "error": "Активная организация не выбрана"}), 403
    return None


def _context():
    conn = get_db()
    try:
        return provider_context(conn, _company_id())
    finally:
        pool.putconn(conn)


def _unsupported(context, capability):
    return jsonify({
        "success": False,
        "configured": True,
        "provider": context["provider"],
        "provider_name": context["provider_name"],
        "code": "FISCAL_CAPABILITY_UNSUPPORTED",
        "error": f"{context['provider_name']} не поддерживает функцию «{capability}» через Nika",
    }), 409


@fiscal_bp.route("/api/fiscal/status", methods=["GET"])
def fiscal_status():
    error = _auth_error()
    if error:
        return error

    context = _context()
    if not context["configured"]:
        return jsonify({
            "success": True,
            "configured": False,
            "provider": None,
            "provider_name": None,
            "capabilities": context["capabilities"],
            "shift_open": False,
            "shift_number": None,
        })

    if context["provider"] == "rekassa":
        from routes.rekassa import _load_company_rekassa, _register_state, _safe_shift_state
        rekassa_context, rekassa_error = _load_company_rekassa()
        if rekassa_error:
            return rekassa_error
        state, state_error = _register_state(rekassa_context)
        if state_error:
            return state_error
        data = _safe_shift_state(state, rekassa_context)
        data.update({
            "success": True,
            "configured": True,
            "provider": context["provider"],
            "provider_name": context["provider_name"],
            "capabilities": context["capabilities"],
        })
        return jsonify(data)

    return jsonify({
        "success": True,
        "configured": True,
        "provider": context["provider"],
        "provider_name": context["provider_name"],
        "capabilities": context["capabilities"],
        "shift_open": False,
        "shift_number": None,
    })


@fiscal_bp.route("/api/fiscal/shifts", methods=["GET"])
def fiscal_shifts():
    error = _auth_error()
    if error:
        return error
    context = _context()
    if not context["configured"]:
        return jsonify({"success": True, "configured": False, "history": [], "has_more": False})
    if not context["capabilities"].get("shifts"):
        return _unsupported(context, "смены")
    if context["provider"] == "rekassa":
        from routes.rekassa import shifts_history
        return shifts_history()
    return jsonify({"success": True, "configured": True, "history": [], "has_more": False})


@fiscal_bp.route("/api/fiscal/shifts/<int:shift_number>/report", methods=["GET"])
def fiscal_shift_report(shift_number):
    error = _auth_error()
    if error:
        return error
    context = _context()
    if not context["configured"]:
        return jsonify({"success": False, "configured": False, "error": "Фискальная касса не подключена"}), 409
    if context["provider"] == "rekassa":
        from routes.rekassa import shift_report
        return shift_report(shift_number)
    return _unsupported(context, "Z-отчёт")


@fiscal_bp.route("/api/fiscal/reports/x", methods=["POST"])
def fiscal_x_report():
    error = _auth_error()
    if error:
        return error
    context = _context()
    if not context["configured"]:
        return jsonify({"success": False, "configured": False, "error": "Фискальная касса не подключена"}), 409
    if not context["capabilities"].get("x_report"):
        return _unsupported(context, "X-отчёт")
    if context["provider"] == "rekassa":
        from routes.rekassa import x_report
        return x_report()
    return _unsupported(context, "X-отчёт")


@fiscal_bp.route("/api/fiscal/shifts/close", methods=["POST"])
def fiscal_close_shift():
    error = _auth_error()
    if error:
        return error
    context = _context()
    if not context["configured"]:
        return jsonify({"success": False, "configured": False, "error": "Фискальная касса не подключена"}), 409
    if not context["capabilities"].get("z_report"):
        return _unsupported(context, "закрытие смены")
    if context["provider"] == "rekassa":
        from routes.rekassa import close_shift
        return close_shift()
    return _unsupported(context, "закрытие смены")


@fiscal_bp.route("/api/fiscal/sales/<int:sale_id>/fiscalize", methods=["POST"])
def fiscalize_existing_sale(sale_id):
    error = _auth_error()
    if error:
        return error

    company_id = _company_id()
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, rekassa_ticket_id FROM sales WHERE id=%s AND company_id=%s FOR UPDATE",
                (sale_id, company_id),
            )
            sale = cur.fetchone()
        finally:
            cur.close()

        if not sale:
            conn.rollback()
            return jsonify({"success": False, "error": "Продажа не найдена"}), 404

        # Existing reKassa field is kept for backwards compatibility. Future
        # providers will use neutral fiscal metadata when their adapters land.
        if sale.get("rekassa_ticket_id"):
            conn.commit()
            return jsonify({
                "success": True,
                "fiscalized": True,
                "message": "Чек уже фискализирован",
                "ticket_id": sale.get("rekassa_ticket_id"),
            })

        result = fiscalize_sale(conn, sale_id, company_id)
        if result.get("skipped"):
            conn.commit()
            return jsonify({
                "success": True,
                "fiscalized": False,
                "skipped": True,
                "configured": False,
                "provider": None,
            })

        if not result.get("fiscalized"):
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE sales SET rekassa_status=%s WHERE id=%s",
                    (("ERROR: " + str(result.get("message") or "Ошибка фискализации"))[:500], sale_id),
                )
            finally:
                cur.close()
            conn.commit()
            return jsonify({
                "success": False,
                "fiscalized": False,
                "configured": True,
                "provider": result.get("provider"),
                "provider_name": result.get("provider_name"),
                "code": result.get("code"),
                "error": result.get("message"),
                "action_url": result.get("action_url"),
                "details": result.get("details"),
            }), 409 if result.get("code") == "FISCAL_OFD_PAYMENT_REQUIRED" else 422

        return jsonify({
            "success": True,
            "fiscalized": True,
            "configured": True,
            "provider": result.get("provider"),
            "provider_name": result.get("provider_name"),
            "ticket_id": result.get("ticket_id"),
            "ticket_number": result.get("ticket_number"),
            "shift_number": result.get("shift_number"),
        })
    except Exception as exc:
        conn.rollback()
        print("FISCAL RETRY ERROR:", repr(exc))
        return jsonify({"success": False, "fiscalized": False, "error": "Не удалось повторить фискализацию"}), 500
    finally:
        pool.putconn(conn)
