from flask import Blueprint, jsonify, session
from models import get_db, pool
from routes.subscriptions import _check_epay_status, _mark_payment_paid

subscription_status_bp = Blueprint("subscription_status", __name__)

@subscription_status_bp.route("/subscription/payment/reconcile", methods=["POST"])
def reconcile_subscription_payment():
    if not session.get("user_id") or not session.get("company_id"):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    company_id = session.get("company_id")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, provider_invoice_id, status
            FROM subscription_payments
            WHERE company_id = %s
              AND provider = 'halyk_epay'
              AND provider_invoice_id IS NOT NULL
              AND status <> 'paid'
            ORDER BY created_at DESC
            LIMIT 25
        """, (company_id,))
        pending_payments = cur.fetchall()
    finally:
        cur.close()
        pool.putconn(conn)

    # A user may have several failed/retried attempts after a successful one.
    # Check recent invoices until Halyk confirms a CHARGE.
    for payment in pending_payments:
        try:
            status_payload = _check_epay_status(payment["provider_invoice_id"])
            if _mark_payment_paid(payment["id"], status_payload):
                break
        except Exception:
            continue

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT status, billing_period, total_price, period_start, period_end, next_payment_at
            FROM company_subscriptions
            WHERE company_id = %s
            LIMIT 1
        """, (company_id,))
        subscription = cur.fetchone()

        cur.execute("""
            SELECT id, amount, currency, provider, payment_method,
                   provider_payment_id, provider_invoice_id, status,
                   description, paid_at, created_at
            FROM subscription_payments
            WHERE company_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (company_id,))
        payments = cur.fetchall()

        def iso(value):
            return value.isoformat() if value else None

        payload = {
            "ok": True,
            "subscription": {
                "status": subscription["status"] if subscription else None,
                "billing_period": subscription["billing_period"] if subscription else None,
                "total_price": float(subscription["total_price"] or 0) if subscription else 0,
                "period_start": iso(subscription["period_start"]) if subscription else None,
                "period_end": iso(subscription["period_end"]) if subscription else None,
                "next_payment_at": iso(subscription["next_payment_at"]) if subscription else None,
            },
            "payments": [
                {
                    "id": row["id"],
                    "amount": float(row["amount"] or 0),
                    "currency": row["currency"] or "KZT",
                    "provider": row["provider"],
                    "payment_method": row["payment_method"],
                    "provider_payment_id": row["provider_payment_id"],
                    "provider_invoice_id": row["provider_invoice_id"],
                    "status": row["status"],
                    "description": row["description"],
                    "paid_at": iso(row["paid_at"]),
                    "created_at": iso(row["created_at"]),
                }
                for row in payments
            ],
        }
        return jsonify(payload)
    finally:
        cur.close()
        pool.putconn(conn)
