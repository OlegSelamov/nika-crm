from flask import Blueprint, render_template, request, redirect, session
from models import get_db, pool

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
    pool.putconn(conn)
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
    pool.putconn(conn)
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
    pool.putconn(conn)

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

    pool.putconn(conn)

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
    pool.putconn(conn)

    return redirect("/companies")
    
@companies_bp.route("/company/profile", methods=["GET", "POST"])
def company_profile():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = session.get("company_id")
    can_manage = bool(
        session.get("is_super_admin")
        or session.get("role") in ("owner", "admin")
    )
    if not company_id:
        return redirect("/profile")

    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            if not can_manage:
                return "Доступ запрещен", 403

            cur.execute("""
                UPDATE companies
                SET name = %s,
                    bin = %s,
                    address = %s,
                    phone = %s,
                    iik = %s,
                    bik = %s,
                    bank = %s,
                    kbe = %s,
                    knp = %s,
                    director = %s,
                    is_vat_payer = %s
                WHERE id = %s
            """, (
                (request.form.get("name") or "").strip(),
                (request.form.get("bin") or "").strip(),
                (request.form.get("address") or "").strip(),
                (request.form.get("phone") or "").strip(),
                (request.form.get("iik") or "").strip(),
                (request.form.get("bik") or "").strip(),
                (request.form.get("bank") or "").strip(),
                (request.form.get("kbe") or "").strip(),
                (request.form.get("knp") or "").strip(),
                (request.form.get("director") or "").strip(),
                request.form.get("is_vat_payer") == "on",
                company_id,
            ))
            conn.commit()
            return redirect("/profile?tab=company&saved=1")

        cur.execute("SELECT * FROM companies WHERE id = %s", (company_id,))
        company = cur.fetchone()
        return render_template("company_profile.html", company=company)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)

