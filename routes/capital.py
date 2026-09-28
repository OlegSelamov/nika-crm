from flask import Blueprint, jsonify, render_template, request, session

from services.capital_lab import (
    CapitalLabError,
    create_signal,
    get_overview,
    open_paper_position,
    close_paper_position,
    reset_paper_account,
    skip_signal,
    sync_open_positions,
    update_risk_limits,
)

capital_bp = Blueprint("capital", __name__, url_prefix="/admin/capital")


def _admin_scope():
    if not session.get("user_id"):
        return None, (jsonify({"success": False, "error": "Требуется войти"}), 401)

    if not session.get("is_super_admin"):
        return None, (jsonify({"success": False, "error": "Доступ только суперадминистратору"}), 403)

    # Platform-level lab: never attach experimental trades to a customer company.
    # Scope 0 is reserved for the private Nika Admin paper-trading laboratory.
    return 0, None


@capital_bp.route("/")
def index():
    company_id, error = _admin_scope()
    if error:
        return error
    return render_template("capital_lab.html", title="Nika Capital Lab")


@capital_bp.route("/api/overview")
def overview():
    company_id, error = _admin_scope()
    if error:
        return error
    try:
        sync_open_positions(company_id)
        return jsonify({"success": True, "data": get_overview(company_id)})
    except CapitalLabError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Ошибка Capital Lab: {exc}"}), 500


@capital_bp.route("/api/analyze", methods=["POST"])
def analyze():
    company_id, error = _admin_scope()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        signal = create_signal(
            company_id,
            payload.get("symbol", "BTCUSDT"),
            payload.get("interval", "1h"),
        )
        return jsonify({"success": True, "signal": signal})
    except CapitalLabError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Ошибка анализа: {exc}"}), 500


@capital_bp.route("/api/signals/<int:signal_id>/open", methods=["POST"])
def open_signal(signal_id):
    company_id, error = _admin_scope()
    if error:
        return error
    try:
        position = open_paper_position(company_id, signal_id)
        return jsonify({"success": True, "position": position})
    except CapitalLabError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Ошибка виртуальной сделки: {exc}"}), 500


@capital_bp.route("/api/signals/<int:signal_id>/skip", methods=["POST"])
def skip(signal_id):
    company_id, error = _admin_scope()
    if error:
        return error
    try:
        skip_signal(company_id, signal_id)
        return jsonify({"success": True})
    except CapitalLabError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@capital_bp.route("/api/positions/<int:position_id>/close", methods=["POST"])
def close_position(position_id):
    company_id, error = _admin_scope()
    if error:
        return error
    try:
        position = close_paper_position(company_id, position_id, reason="manual")
        return jsonify({"success": True, "position": position})
    except CapitalLabError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": f"Ошибка закрытия позиции: {exc}"}), 500


@capital_bp.route("/api/risk", methods=["POST"])
def risk():
    company_id, error = _admin_scope()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        data = update_risk_limits(company_id, payload)
        return jsonify({"success": True, "risk": data})
    except (CapitalLabError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@capital_bp.route("/api/reset", methods=["POST"])
def reset():
    company_id, error = _admin_scope()
    if error:
        return error
    try:
        reset_paper_account(company_id)
        return jsonify({"success": True})
    except CapitalLabError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
