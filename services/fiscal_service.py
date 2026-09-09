import json
import re


PROVIDER_META = {
    "rekassa": {
        "code": "rekassa",
        "name": "reKassa",
        "capabilities": {
            "fiscalize": True,
            "refund": True,
            "shifts": True,
            "x_report": True,
            "z_report": True,
        },
    },
    "webkassa": {
        "code": "webkassa",
        "name": "Webkassa",
        "capabilities": {
            "fiscalize": True,
            "refund": True,
            "shifts": True,
            "x_report": True,
            "z_report": True,
        },
    },
    "local": {
        "code": "local",
        "name": "Стационарная ККМ",
        "capabilities": {
            "fiscalize": True,
            "refund": True,
            "shifts": True,
            "x_report": True,
            "z_report": True,
        },
    },
}

OFD_PAYMENT_REQUIRED = "FISCAL_OFD_PAYMENT_REQUIRED"


def ensure_fiscal_schema(conn):
    """Add provider-neutral integration fields without breaking old installations."""
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE integrations ADD COLUMN IF NOT EXISTS fiscal_provider TEXT")
        cur.execute("ALTER TABLE integrations ADD COLUMN IF NOT EXISTS fiscal_provider_name TEXT")
    finally:
        cur.close()


def _latest_integration(conn, company_id):
    ensure_fiscal_schema(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT * FROM integrations WHERE company_id=%s ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else {}
    finally:
        cur.close()


def _rekassa_configured(data):
    return bool(
        data.get("rekassa_enabled")
        and data.get("rekassa_number")
        and data.get("rekassa_password")
        and data.get("rekassa_crs_id")
    )


def _webkassa_configured(data):
    # These keys are intentionally optional. When the Webkassa settings module
    # is connected later, FiscalService will start recognizing it without any
    # changes in Sales.
    enabled = data.get("webkassa_enabled")
    identity = (
        data.get("webkassa_cashbox_number")
        or data.get("webkassa_cashbox_unique_number")
        or data.get("webkassa_login")
    )
    return bool(enabled and identity)


def provider_context(conn, company_id):
    data = _latest_integration(conn, company_id)
    explicit = str(data.get("fiscal_provider") or "").strip().lower()

    provider = explicit if explicit in PROVIDER_META else None
    if not provider:
        if _rekassa_configured(data):
            provider = "rekassa"
        elif _webkassa_configured(data):
            provider = "webkassa"

    configured = False
    if provider == "rekassa":
        configured = _rekassa_configured(data)
    elif provider == "webkassa":
        configured = _webkassa_configured(data)
    elif provider == "local":
        configured = bool(data.get("fiscal_provider") == "local")

    if not provider or not configured:
        return {
            "configured": False,
            "provider": None,
            "provider_name": None,
            "integration": data,
            "capabilities": {
                "fiscalize": False,
                "refund": False,
                "shifts": False,
                "x_report": False,
                "z_report": False,
            },
        }

    meta = PROVIDER_META[provider]
    return {
        "configured": True,
        "provider": provider,
        "provider_name": data.get("fiscal_provider_name") or meta["name"],
        "integration": data,
        "capabilities": dict(meta["capabilities"]),
    }


def mark_provider(conn, company_id, provider, provider_name=None):
    """Persist the active fiscal provider on the latest integration row."""
    ensure_fiscal_schema(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id FROM integrations WHERE company_id=%s ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        cur.execute(
            "UPDATE integrations SET fiscal_provider=%s, fiscal_provider_name=%s WHERE id=%s",
            (provider, provider_name, row["id"]),
        )
        return True
    finally:
        cur.close()


def clear_provider(conn, company_id):
    ensure_fiscal_schema(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE integrations SET fiscal_provider=NULL, fiscal_provider_name=NULL WHERE company_id=%s",
            (company_id,),
        )
    finally:
        cur.close()


def _ofd_required(result):
    if not isinstance(result, dict):
        return False
    text = json.dumps(result, ensure_ascii=False, default=str).lower()
    text = re.sub(r"[\s_-]+", " ", text)
    return (
        "cash register ofd payment required" in text
        or "ofd payment required" in text
        or ("оплат" in text and ("ofd" in text or "офд" in text))
    )


def _rekassa_error(result):
    if _ofd_required(result):
        from routes.rekassa import REKASSA_URL
        is_test = "test" in str(REKASSA_URL or "").lower()
        return {
            "code": OFD_PAYMENT_REQUIRED,
            "message": "Требуется оплатить ОФД COMRUN",
            "action_url": (
                "https://account.apps-test.rekassa.kz"
                if is_test
                else "https://account.apps.rekassa.kz"
            ),
        }
    return {
        "code": "FISCAL_PROVIDER_ERROR",
        "message": result.get("message") or result.get("error") or "Касса отклонила чек",
        "action_url": None,
    }


def fiscalize_sale(conn, sale_id, company_id):
    """Fiscalize through the active provider. No provider means a silent skip."""
    context = provider_context(conn, company_id)
    if not context["configured"]:
        return {
            "success": True,
            "fiscalized": False,
            "skipped": True,
            "provider": None,
            "provider_name": None,
            "code": "FISCAL_NOT_CONFIGURED",
            "message": None,
        }

    provider = context["provider"]
    if provider == "rekassa":
        from routes.rekassa import rekassa_sell
        result = rekassa_sell(conn, sale_id)
        if result.get("status") == "OK":
            return {
                "success": True,
                "fiscalized": True,
                "skipped": False,
                "provider": provider,
                "provider_name": context["provider_name"],
                "code": None,
                "message": None,
                "ticket_id": result.get("id"),
                "ticket_number": result.get("ticketNumber"),
                "shift_number": result.get("shiftNumber"),
                "raw": result,
            }
        error = _rekassa_error(result)
        return {
            "success": False,
            "fiscalized": False,
            "skipped": False,
            "provider": provider,
            "provider_name": context["provider_name"],
            "details": result.get("details"),
            "http_status": result.get("http_status"),
            **error,
        }

    # Provider is registered but its adapter is not connected yet. This is a
    # provider-specific error, never a generic Sales failure.
    return {
        "success": False,
        "fiscalized": False,
        "skipped": False,
        "provider": provider,
        "provider_name": context["provider_name"],
        "code": "FISCAL_ADAPTER_NOT_READY",
        "message": f"Адаптер {context['provider_name']} ещё не подключён к фискальному слою Nika",
    }
