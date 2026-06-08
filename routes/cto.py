from flask import Blueprint, render_template

cto_bp = Blueprint("cto", __name__)

@cto_bp.route("/cto")
def cto():
    return render_template("cto.html")