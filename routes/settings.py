from flask import Blueprint, render_template, session, redirect

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