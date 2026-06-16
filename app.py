from flask import Flask, render_template
from routes.dashboard import dashboard_bp
from routes.clients import clients_bp
from routes.tasks import tasks_bp
from routes.items import items_bp
from routes.sales import sales_bp
from routes.kaspi_pos import kaspi_pos_bp
from flask import redirect, session
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
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)
app.secret_key = "nika_super_secret_key"

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
    
@app.before_request
def check_company_access():

    # 🔥 супер-админ и creator — НЕ блокируются
    if session.get("is_super_admin") or session.get("is_creator"):
        return

    if not session.get("company_id"):
        return

    conn = get_db()
    cur = None

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM companies WHERE id = %s",
            (session.get("company_id"),)
        )

        company = cur.fetchone()

    finally:
        if cur:
            cur.close()

        pool.putconn(conn)

    if not company:
        return

    #if not company["is_active"]:
        #return "Доступ ограничен. Обратитесь к администратору"

    if company["paid_until"]:
        from datetime import datetime
        if datetime.now() > datetime.fromisoformat(company["paid_until"]):
            return "Доступ приостановлен. Оплатите подписку"
            
@app.route("/")
def landing():

    if session.get("user_id"):
        return redirect("/dashboard")

    return render_template("landing.html")
    
if __name__ == "__main__":
    #init_db()

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )