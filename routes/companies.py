from flask import Blueprint, render_template, request, redirect, session
from models import get_db

companies_bp = Blueprint("companies", __name__) 

# 📋 список
@companies_bp.route("/companies")
def companies():
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403
        
    conn = get_db()
    
    cur = conn.cursor()
    
    cur.execute("SELECT * FROM companies")

    data = cur.fetchall()
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
    
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO companies (
            name, bin, address, phone,
            iik, bik, bank, kbe, knp, director
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
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

    company_id = cur.fetchone()["id"]

    # 🔥 привязываем текущего пользователя к этой компании
    cur.execute(
        "UPDATE users SET company_id = %s WHERE id = %s",
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
    
    cur = conn.cursor()

    cur.execute("UPDATE companies SET is_active = FALSE")
    cur.execute(
        "UPDATE companies SET is_active = TRUE WHERE id = %s",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/companies")
    
# 🔥 API активной организации
@companies_bp.route("/api/company/active")
def active_company():
    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM companies
        WHERE is_active = TRUE
        LIMIT 1
    """)

    company = cur.fetchone()

    conn.close()

    return dict(company) if company else {}
    
@companies_bp.route("/companies/delete/<int:id>")
def delete_company(id):
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute("DELETE FROM companies WHERE id = %s", (id,))

    conn.commit()
    conn.close()

    return redirect("/companies")
    
@companies_bp.route("/company/profile")
def company_profile():
    if not session.get("user_id"):
        return redirect("/login")

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM companies WHERE id = %s",
        (session.get("company_id"),)
    )

    company = cur.fetchone()

    conn.close()

    return render_template("company_profile.html", company=company)