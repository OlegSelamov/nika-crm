from flask import Blueprint, render_template

expenses_bp = Blueprint("expenses", __name__)

@expenses_bp.route("/expenses")
def expenses():
    return render_template("expenses.html")