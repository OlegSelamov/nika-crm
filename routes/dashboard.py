from flask import Blueprint, jsonify, redirect, session

from models import get_db, pool
from routes.reports import _get_summary
from utils.timezone import now_kz


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
def dashboard():
    """Совместимый старый адрес: бизнес-показатели теперь живут только в Аналитике."""
    if not session.get("user_id"):
        return redirect("/login")
    return redirect("/analytics")


@dashboard_bp.route("/api/dashboard")
def api_dashboard():
    if not session.get("user_id"):
        return jsonify({"success": False}), 401

    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 400

    conn = get_db()
    cur = conn.cursor()
    today = now_kz().date()

    try:
        summary = _get_summary(cur, company_id, today, today)

        cur.execute("""
            SELECT
                COUNT(*) AS returns_count,
                COALESCE(SUM(total_amount), 0) AS returns_total
            FROM sales
            WHERE company_id = %s
              AND (
                    status = 'Возврат'
                    OR COALESCE(is_refunded, FALSE) = TRUE
                  )
              AND DATE(COALESCE(refunded_at, created_at)) = %s
        """, (company_id, today))
        returns = cur.fetchone() or {}

        # Общие количества оставляем в API для обратной совместимости,
        # но они больше не смешиваются с показателями блока «Сегодня».
        cur.execute("""
            SELECT COUNT(*) AS total
            FROM clients
            WHERE company_id = %s
        """, (company_id,))
        clients = (cur.fetchone() or {}).get("total") or 0

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM items
            WHERE company_id = %s
        """, (company_id,))
        items = (cur.fetchone() or {}).get("total") or 0

        revenue = float(summary.get("revenue") or 0)
        gross_profit = float(summary.get("gross_profit") or 0)
        operating_expenses = float(summary.get("operating_expenses") or 0)
        net_profit = float(summary.get("net_profit") or 0)

        return jsonify({
            "success": True,
            "period": "today",
            "date": today.isoformat(),
            "today": revenue,
            "revenue": revenue,
            "sales_today": int(summary.get("sales_count") or 0),
            "sales_count": int(summary.get("sales_count") or 0),
            "average_check": float(summary.get("average_check") or 0),
            "gross_profit": gross_profit,
            "profit": net_profit,
            "net_profit": net_profit,
            "operating_expenses": operating_expenses,
            "purchase_total": float(summary.get("purchase_total") or 0),
            "purchase_days": int(summary.get("purchase_count") or 0),
            "returns_count": int(returns.get("returns_count") or 0),
            "returns_total": float(returns.get("returns_total") or 0),
            "cash": float(summary.get("cash") or 0),
            "card": float(summary.get("card") or 0),
            "kaspi": float(summary.get("kaspi") or 0),
            "clients": int(clients),
            "items": int(items),
        })
    finally:
        cur.close()
        pool.putconn(conn)
