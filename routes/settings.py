from flask import Blueprint, render_template, session, redirect
from models import get_db, pool

settings_bp = Blueprint("settings", __name__)

@settings_bp.route("/settings")
def settings():

    if not session.get("user_id"):
        return redirect("/login")

    return render_template("settings.html")
    
@settings_bp.route("/settings/integrations")
def integrations():
    return render_template("settings/integrations.html")


@settings_bp.route("/settings/kkm")
def kkm():
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("company_id"):
        return redirect("/dashboard")

    return render_template("settings/kkm.html")


@settings_bp.route("/settings/pos")
def pos():
    return render_template("settings/pos.html")


@settings_bp.route("/settings/catalog")
def catalog():
    return render_template("settings/catalog.html")


@settings_bp.route("/settings/backup")
def backup():
    return render_template("settings/backup.html")
    
@settings_bp.route("/settings/equipment")
def equipment():

    if not session.get("user_id"):
        return redirect("/login")

    return render_template("settings/equipment.html")
    
@settings_bp.route("/settings/printers")
def printers():
    return render_template("settings/printers.html")


@settings_bp.route("/settings/scanners")
def scanners():
    return render_template("settings/scanners.html")


@settings_bp.route("/settings/scales")
def scales():
    return render_template("settings/scales.html")
    
@settings_bp.route("/settings/rekassa")
def rekassa_settings():
    return render_template("rekassa_settings.html")
    
@settings_bp.route("/settings/whatsapp")
def whatsapp_settings():

    if not session.get("user_id"):
        return redirect("/login")

    company_id = session.get("company_id")

    if not company_id:
        return redirect("/dashboard")

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id,
                phone,
                instance_id,
                enabled,
                ai_enabled,
                status,
                updated_at
            FROM whatsapp_integrations
            WHERE company_id = %s
            LIMIT 1
        """, (company_id,))

        whatsapp = cur.fetchone()

    finally:
        pool.putconn(conn)

    return render_template(
        "settings/whatsapp.html",
        whatsapp=whatsapp
    )
