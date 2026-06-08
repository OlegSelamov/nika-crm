from flask import Blueprint, render_template

accounting_bp = Blueprint("accounting", __name__)

@accounting_bp.route("/accounting")
def accounting():
    return render_template("accounting.html")