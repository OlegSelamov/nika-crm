from flask import Blueprint, render_template, request, redirect, session
from models import get_db
import sqlite3

companies_bp = Blueprint("companies", __name__)

DB_NAME = "database.db" 

# 📋 список
@companies_bp.route("/companies")
def companies():
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403
        
    conn = get_db()
    conn.row_factory = sqlite3.Row
    data = conn.execute("SELECT * FROM companies").fetchall()
    conn.close()
    return render_template("companies.html", companies=data)

# ➕ добавление
@companies_bp.route("/companies/add", methods=["POST"])
def add_company():
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403
        
    conn = get_db()
    conn.row_factory = sqlite3.Row
    conn.execute("""
        INSERT INTO companies (name, bin, address, phone, iik, bik, bank, kbe, knp, director)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form["name"],
        request.form["bin"],
        request.form["address"],
        request.form["phone"],
        request.form.get("iik"),
        request.form.get("bik"),
        request.form.get("bank"),
        request.form.get("kbe"),
        request.form.get("knp"),
        request.form.get("director"),
    ))
    
    # получаем ID созданной компании
    company_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 🔥 привязываем текущего пользователя к этой компании
    conn.execute(
        "UPDATE users SET company_id = ? WHERE id = ?",
        (company_id, session["user_id"])
    )
    
    conn.commit()
    conn.close()
    return redirect("/companies")

# ⭐ сделать активной
@companies_bp.route("/companies/activate/<int:id>")
def activate_company(id):
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403
        
    conn = get_db()
    conn.row_factory = sqlite3.Row

    conn.execute("UPDATE companies SET is_active = 0")
    conn.execute("UPDATE companies SET is_active = 1 WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/companies")
    
# 🔥 API активной организации
@companies_bp.route("/api/company/active")
def active_company():
    conn = get_db()
    conn.row_factory = sqlite3.Row

    company = conn.execute("""
        SELECT * FROM companies
        WHERE is_active = 1
        LIMIT 1
    """).fetchone()

    conn.close()

    return dict(company) if company else {}
    
@companies_bp.route("/companies/delete/<int:id>")
def delete_company(id):
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403

    conn = get_db()

    conn.execute("DELETE FROM companies WHERE id = ?", (id,))

    conn.commit()
    conn.close()

    return redirect("/companies")
    
@companies_bp.route("/company/profile")
def company_profile():
    if not session.get("user_id"):
        return redirect("/login")

    conn = get_db()

    company = conn.execute(
        "SELECT * FROM companies WHERE id = ?",
        (session.get("company_id"),)
    ).fetchone()

    conn.close()

    return render_template("company_profile.html", company=company)