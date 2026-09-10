import os
import socket
from copy import deepcopy
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_file = os.getenv("NIKA_ENV_FILE", ".env")
if not os.path.isabs(env_file):
    env_file = os.path.join(BASE_DIR, env_file)
load_dotenv(env_file, override=True)
APP_MODE = os.getenv("APP_MODE", "test")

# The VPS has a broken IPv6 route to api.openai.com while IPv4 works normally.
# Apply the workaround directly here before importing any route that creates
# an OpenAI/httpx client. Only api.openai.com is affected.
_original_getaddrinfo = socket.getaddrinfo

def _openai_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    try:
        hostname = host.decode("ascii", "ignore") if isinstance(host, bytes) else str(host or "")
    except Exception:
        hostname = ""

    if hostname.rstrip(".").lower() == "api.openai.com" and family in (0, socket.AF_UNSPEC):
        family = socket.AF_INET

    return _original_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _openai_ipv4_getaddrinfo

from flask import Flask, render_template, request, redirect, session, g, jsonify
from routes.dashboard import dashboard_bp
from routes.clients import clients_bp
from routes.tasks import tasks_bp
from routes.items import items_bp
from routes.sales import sales_bp
from routes.rekassa_comrun import pay_sale_comrun, fiscalize_sale_comrun
from routes.kaspi_pos import kaspi_pos_bp
from models import init_db, get_db, pool
from routes.sales import sales_api
from routes.companies import companies_bp
from routes.agent import agent_bp
from routes.ai import ai_bp
from routes.voice import voice_bp
from routes.auth import auth_bp
from routes.stock import stock_bp
from routes.webkassa import webkassa_bp
from routes.settings import settings_bp
from routes.reports import reports_bp
from routes.expenses import expenses_bp
from routes.cto import cto_bp
from routes.accounting import accounting_bp
from routes.rekassa import rekassa_bp
from routes.subscriptions import subscriptions_bp
from routes.subscription_status import subscription_status_bp
from subscriptions import load_subscription_context
from routes.communications import communications_bp
from routes.admin import admin_bp
from routes.onboarding import onboarding_bp
from routes.storefront import storefront_bp
from routes.storefront_settings import storefront_settings_bp
from routes.storefront_manage import storefront_manage_bp
from routes.storefront_notifications import storefront_notifications_bp
from routes.whatsapp import whatsapp_bp
from routes.mobile_api import mobile_api_bp
from routes.esf import esf_bp
import routes.esf as esf_module
from routes.bcc import bcc_bp
from routes.school import school_bp
from datetime import timedelta

# Keep non-sent ESF drafts in sync with the current client contract.
# Old drafts may have been stored before contract_number/contract_date were filled.
_original_esf_document_view = esf_module._document_view

def _esf_document_view_with_current_contract(row, fallback_payload):
    if row and not row.get("external_id") and isinstance(fallback_payload, dict):
        merged_row = dict(row)
        saved_payload = deepcopy(row.get("payload") or {})
        delivery = saved_payload.setdefault("delivery", {})
        current_delivery = fallback_payload.get("delivery") or {}
        if not str(delivery.get("contract_num") or "").strip():
            delivery["contract_num"] = current_delivery.get("contract_num") or ""
        if not str(delivery.get("contract_date") or "").strip():
            delivery["contract_date"] = current_delivery.get("contract_date") or ""
        merged_row["payload"] = saved_payload
        row = merged_row
    return _original_esf_document_view(row, fallback_payload)

esf_module._document_view = _esf_document_view_with_current_contract

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"), static_folder=os.path.join(BASE_DIR, "static"))
app.secret_key = os.getenv("SECRET_KEY", "nika_super_secret_key")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["APP_MODE"] = APP_MODE

# Lightweight production migration for the item media gallery.
# Gunicorn does not call init_db(), so this must run during app import too.
try:
    _media_schema_conn = get_db()
    _media_schema_cur = _media_schema_conn.cursor()
    _media_schema_cur.execute("""
        ALTER TABLE item_images
        ADD COLUMN IF NOT EXISTS is_main BOOLEAN NOT NULL DEFAULT FALSE
    """)
    _media_schema_cur.execute("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS is_vat_payer BOOLEAN NOT NULL DEFAULT FALSE
    """)
    _media_schema_cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS start_page TEXT DEFAULT 'profile'")
    _media_schema_cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS compact_mode BOOLEAN NOT NULL DEFAULT FALSE")
    _media_schema_cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE")
    _media_schema_cur.execute("""
        CREATE TABLE IF NOT EXISTS company_document_settings (
            company_id INTEGER PRIMARY KEY,
            custom_numbering_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            invoice_next_number INTEGER NOT NULL DEFAULT 1,
            nakladnaya_next_number INTEGER NOT NULL DEFAULT 1,
            act_next_number INTEGER NOT NULL DEFAULT 1,
            schet_factura_next_number INTEGER NOT NULL DEFAULT 1,
            show_signature BOOLEAN NOT NULL DEFAULT FALSE,
            show_stamp BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _media_schema_cur.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS invoice_number INTEGER")
    _media_schema_cur.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS nakladnaya_number INTEGER")
    _media_schema_cur.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS act_number INTEGER")
    _media_schema_cur.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS schet_factura_number INTEGER")
    _media_schema_cur.execute("""
        CREATE TABLE IF NOT EXISTS school_students (
            id SERIAL PRIMARY KEY, company_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,
            full_name TEXT NOT NULL, iin TEXT, phone TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    _media_schema_cur.execute("""
        CREATE TABLE IF NOT EXISTS school_attendance (
            id BIGSERIAL PRIMARY KEY, company_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL REFERENCES school_students(id) ON DELETE CASCADE,
            attendance_date DATE NOT NULL, is_present BOOLEAN NOT NULL DEFAULT TRUE,
            note TEXT, marked_by INTEGER, updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, student_id, attendance_date)
        )
    """)
    _media_schema_cur.execute("""
        CREATE TABLE IF NOT EXISTS school_schedule (
            id SERIAL PRIMARY KEY, company_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,
            weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
            lesson_number INTEGER NOT NULL CHECK (lesson_number > 0),
            subject TEXT NOT NULL, teacher TEXT, room TEXT, start_time TIME, end_time TIME,
            created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, class_id, weekday, lesson_number)
        )
    """)
    _media_schema_cur.execute("""
        CREATE TABLE IF NOT EXISTS school_lesson_topics (
            id BIGSERIAL PRIMARY KEY, company_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,
            lesson_date DATE NOT NULL, lesson_number INTEGER NOT NULL CHECK (lesson_number > 0),
            subject TEXT, topic TEXT NOT NULL, homework TEXT, teacher TEXT, created_by INTEGER,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, class_id, lesson_date, lesson_number)
        )
    """)

    _media_schema_cur.execute("ALTER TABLE school_lesson_topics ADD COLUMN IF NOT EXISTS methodic_url TEXT")
    _media_schema_cur.execute("ALTER TABLE school_lesson_topics ADD COLUMN IF NOT EXISTS methodic_name TEXT")
    _media_schema_cur.execute("ALTER TABLE school_lesson_topics ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'planned'")
    _media_schema_cur.execute("ALTER TABLE school_lesson_topics ADD COLUMN IF NOT EXISTS conducted_at TIMESTAMP")
    _media_schema_cur.execute("ALTER TABLE school_lesson_topics ADD COLUMN IF NOT EXISTS conducted_by INTEGER")

    _media_schema_conn.commit()
    _media_schema_cur.close()
    pool.putconn(_media_schema_conn)
except Exception as _media_schema_error:
    try:
        _media_schema_conn.rollback()
        pool.putconn(_media_schema_conn)
    except Exception:
        pass
    print("ITEM MEDIA SCHEMA MIGRATION ERROR:", _media_schema_error)

app.register_blueprint(dashboard_bp)
app.register_blueprint(clients_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(items_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(kaspi_pos_bp)
app.register_blueprint(sales_api)
app.register_blueprint(companies_bp)
app.register_blueprint(agent_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(voice_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(stock_bp)
app.register_blueprint(webkassa_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(expenses_bp)
app.register_blueprint(cto_bp)
app.register_blueprint(accounting_bp)
app.register_blueprint(rekassa_bp)
app.register_blueprint(subscriptions_bp)
app.register_blueprint(subscription_status_bp)
app.register_blueprint(communications_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(onboarding_bp)
app.register_blueprint(storefront_bp)
app.register_blueprint(storefront_settings_bp)
app.register_blueprint(storefront_manage_bp)
app.register_blueprint(storefront_notifications_bp)
app.register_blueprint(whatsapp_bp)
app.register_blueprint(mobile_api_bp)
app.register_blueprint(esf_bp)
app.register_blueprint(bcc_bp)
app.register_blueprint(school_bp)

# Keep the public URLs unchanged, but replace only the sale/fiscalization
# handlers with the COMRUN-aware flow. This avoids duplicate Flask routes and
# preserves compatibility with web, desktop and mobile clients.
app.view_functions["sales.pay_sale"] = pay_sale_comrun
app.view_functions["rekassa.retry_rekassa_fiscalization"] = fiscalize_sale_comrun

MODULE_PATHS = (
    ("/school", "school"),
    ("/api/mobile/accounting", "accounting"),
    ("/api/mobile/expenses", "expenses"),
    ("/api/mobile/tasks", "tasks"),
    ("/api/mobile/cto", "cto"),
    ("/storefront", "storefront"),
    ("/accounting", "accounting"),
    ("/analytics", "analytics"),
    ("/reports", "reports"),
    ("/expenses", "expenses"),
    ("/clients", "clients"),
    ("/tasks", "tasks"),
    ("/items", "catalog"),
    ("/categories", "catalog"),
    ("/stock", "warehouse"),
    ("/sales", "sales"),
    ("/api/sales", "sales"),
    ("/cto", "cto"),
)

@app.before_request
def check_company_access():
    load_subscription_context()
    if session.get("is_super_admin"):
        return None
    allowed_paths = ("/", "/login", "/logout", "/register", "/onboarding", "/subscription", "/static/", "/s/", "/whatsapp/webhook")
    if any(request.path == path or request.path.startswith(path) for path in allowed_paths):
        return None
    if not session.get("user_id") or not session.get("company_id"):
        return None
    subscription = getattr(g, "company_subscription", None)
    if not subscription:
        if request.path.startswith("/api/mobile/"):
            return jsonify({"success": False, "error": "Подписка компании не настроена"}), 403
        return redirect("/subscription")
    if subscription["status"] in ("expired", "pending_payment", "suspended", "cancelled"):
        status = subscription["status"]
        if request.path.startswith("/api/mobile/"):
            if status == "expired":
                message = "Пробный период завершён. Выберите подписку, чтобы продолжить работу."
                code = "subscription_expired"
            elif status == "pending_payment":
                message = "Ожидается оплата подписки. Рабочий доступ будет восстановлен после подтверждения оплаты."
                code = "subscription_payment_required"
            else:
                message = "Подписка компании приостановлена"
                code = "subscription_suspended"
            return jsonify({
                "success": False,
                "error": message,
                "code": code,
                "subscription_status": status,
                "subscription_url": "/subscription",
            }), 403
        query = "payment_required=1" if status == "pending_payment" else "expired=1"
        return redirect(f"/subscription?{query}")
    company_modules = getattr(g, "company_modules", set())
    for path_prefix, module_code in MODULE_PATHS:
        if request.path == path_prefix or request.path.startswith(path_prefix + "/"):
            if module_code not in company_modules:
                if request.path.startswith("/api/mobile/"):
                    return jsonify({"success": False, "error": "Раздел не подключён в подписке компании", "module": module_code}), 403
                return redirect(f"/subscription?required={module_code}&next={request.path}")
            break
    return None

@app.after_request
def inject_storefront_workflow_assets(response):
    if not session.get("user_id"):
        return response
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        return response
    try:
        html = response.get_data(as_text=True)
        if "storefront_workflow.css" not in html and "</head>" in html:
            html = html.replace("</head>", '<link rel="stylesheet" href="/static/css/storefront_workflow.css?v=20260904-1">\n</head>', 1)
        if request.path == "/sales" and "sales_client_desktop.css" not in html and "</head>" in html:
            html = html.replace("</head>", '<link rel="stylesheet" href="/static/css/sales_client_desktop.css?v=20260909-1">\n</head>', 1)
        if "storefront_workflow.js" not in html and "</body>" in html:
            html = html.replace("</body>", '<script src="/static/js/storefront_workflow.js?v=20260904-1"></script>\n</body>', 1)
        if "ai_error_patch.js" not in html and "</body>" in html:
            html = html.replace("</body>", '<script src="/static/js/ai_error_patch.js?v=20260904-1"></script>\n</body>', 1)
        if request.path == "/sales" and "sales_hid_scanner.js" not in html and "</body>" in html:
            html = html.replace("</body>", '<script src="/static/js/sales_hid_scanner.js?v=20260904-3"></script>\n</body>', 1)
        if request.path == "/sales" and "sales_rekassa_comrun.js" not in html and "</body>" in html:
            html = html.replace("</body>", '<script src="/static/js/sales_rekassa_comrun.js?v=20260909-1"></script>\n</body>', 1)
        scanner_pages = {"/items", "/stock", "/stock/income", "/stock/writeoff", "/stock/movements", "/clients"}
        if request.path in scanner_pages and "global_hid_scanner.js" not in html and "</body>" in html:
            html = html.replace("</body>", '<script src="/static/js/global_hid_scanner.js?v=20260904-1"></script>\n</body>', 1)
        response.set_data(html)
    except Exception as exc:
        print("COMMON CRM ASSET INJECT ERROR:", exc)
    return response

@app.context_processor
def inject_subscription_context():
    return {"company_modules": getattr(g, "company_modules", set()), "company_subscription": getattr(g, "company_subscription", None)}

@app.route("/")
def landing():
    if session.get("user_id"):
        return redirect("/analytics")
    return render_template("landing.html")

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=5000, debug=True)
