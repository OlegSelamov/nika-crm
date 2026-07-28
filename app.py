import os
from dotenv import load_dotenv

# Загружаем нужное окружение ДО импорта routes и models.
env_file = os.getenv("NIKA_ENV_FILE", ".env.test")
load_dotenv(env_file, override=True)

APP_MODE = os.getenv("APP_MODE", "test")

from flask import Flask, render_template, request, redirect, session, g
from routes.dashboard import dashboard_bp
from routes.clients import clients_bp
from routes.tasks import tasks_bp
from routes.items import items_bp
from routes.sales import sales_bp
from routes.kaspi_pos import kaspi_pos_bp
from models import init_db
from routes.sales import sales_api
from routes.companies import companies_bp
from routes.agent import agent_bp
from routes.voice import voice_bp
from routes.auth import auth_bp
from models import get_db, pool
from routes.stock import stock_bp
from routes.webkassa import webkassa_bp
from routes.settings import settings_bp
from routes.reports import reports_bp
from routes.expenses import expenses_bp
from routes.cto import cto_bp
from routes.accounting import accounting_bp
from routes.rekassa import rekassa_bp
from routes.subscriptions import subscriptions_bp
from subscriptions import load_subscription_context
from routes.communications import communications_bp
from routes.admin import admin_bp
from routes.onboarding import onboarding_bp
from routes.storefront import storefront_bp
from routes.storefront_settings import storefront_settings_bp
from routes.storefront_manage import storefront_manage_bp
from routes.whatsapp import whatsapp_bp
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
app.secret_key = "nika_super_secret_key"

from datetime import timedelta

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

app.config["APP_MODE"] = APP_MODE

# подключаем роуты
app.register_blueprint(dashboard_bp)
app.register_blueprint(clients_bp)
app.register_blueprint(tasks_bp)
app.register_blueprint(items_bp)
app.register_blueprint(sales_bp)
app.register_blueprint(kaspi_pos_bp)
app.register_blueprint(sales_api)
app.register_blueprint(companies_bp)
app.register_blueprint(agent_bp)
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
app.register_blueprint(communications_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(onboarding_bp)
app.register_blueprint(storefront_bp)
app.register_blueprint(storefront_settings_bp)
app.register_blueprint(storefront_manage_bp)
app.register_blueprint(whatsapp_bp)
    
# Какой URL относится к какому платному модулю.
# Более длинные пути ставим выше коротких, чтобы проверка была точной.
MODULE_PATHS = (
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
    # На каждом запросе загружаем подписку и подключённые модули в flask.g.
    load_subscription_context()

    # Системный супер-администратор видит и открывает всё.
    if session.get("is_super_admin"):
        return None

    # Не мешаем открывать публичные страницы до авторизации.
    allowed_paths = (
        "/",
        "/login",
        "/logout",
        "/register",
        "/onboarding",
        "/subscription",
        "/static/",
        "/s/",
        "/whatsapp/webhook",
    )
    if any(
        request.path == path or request.path.startswith(path)
        for path in allowed_paths
    ):
        return None

    # Остальные проверки применяются только к авторизованной компании.
    if not session.get("user_id") or not session.get("company_id"):
        return None

    subscription = getattr(g, "company_subscription", None)

    # Если подписка ещё не создана или заблокирована — отправляем на управление подпиской.
    if not subscription:
        return redirect("/subscription")

    if subscription["status"] in ("expired", "suspended", "cancelled"):
        return redirect("/subscription")

    company_modules = getattr(g, "company_modules", set())

    # Проверяем доступ к разделу даже при ручном вводе URL.
    for path_prefix, module_code in MODULE_PATHS:
        if request.path == path_prefix or request.path.startswith(path_prefix + "/"):
            if module_code not in company_modules:
                return redirect(
                    f"/subscription?required={module_code}&next={request.path}"
                )
            break

    return None


@app.context_processor
def inject_subscription_context():
    return {
        "company_modules": getattr(g, "company_modules", set()),
        "company_subscription": getattr(g, "company_subscription", None),
    }

@app.route("/")
def landing():

    if session.get("user_id"):
        return redirect("/dashboard")

    return render_template("landing.html")
    
if __name__ == "__main__":
    init_db()

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )