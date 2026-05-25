from flask import Blueprint, render_template, request, redirect, session, url_for
from models import get_db
from datetime import datetime

auth_bp = Blueprint("auth", __name__)

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE id = %s",
        (user_id,)
    )

    user = cur.fetchone()
    conn.close()
    return user

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE username = %s AND password = %s",
            (username, password)
        )

        user = cur.fetchone()
        conn.close()
        
        if user:
            print("USER COMPANY:", user["company_id"])
        else:
            print("USER NOT FOUND")

        if not user:
            return render_template("login.html", error="Неверный логин или пароль")

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"] or "cashier"
        session["company_id"] = user["company_id"]
        session["is_super_admin"] = user["is_super_admin"] or 0
        session["is_creator"] = user["is_creator"] if "is_creator" in user.keys() else 0

        # 👑 Супер админ
        if user["is_super_admin"]:
            return redirect("/companies")

        # 🏢 Админ компании
        if user["role"] == "admin":
            return redirect("/company/profile")

        # 👤 Кассир
        return redirect("/profile")

    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@auth_bp.route("/users", methods=["GET", "POST"])
def users():
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403

    conn = get_db()
    
    cur = conn.cursor()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "cashier").strip()
        company_id = request.form.get("company_id") or session.get("company_id")
        is_super_admin = 1 if request.form.get("is_super_admin") == "1" else 0

        cur.execute("""
            INSERT INTO users (username, password, role, company_id, is_super_admin, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            username,
            password,
            role,
            company_id if company_id else None,
            is_super_admin,
            datetime.now()
        ))
        conn.commit()
        conn.close()
        return redirect("/users")

    cur.execute("""
        SELECT users.*, companies.name as company_name
        FROM users
        LEFT JOIN companies ON users.company_id = companies.id
        ORDER BY users.id DESC
    """)

    users = cur.fetchall()

    cur.execute("""
        SELECT * FROM companies
        ORDER BY id DESC
    """)

    companies = cur.fetchall()

    conn.close()

    return render_template("users.html", users=users, companies=companies)
    
@auth_bp.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect("/login")

    return render_template("profile.html")
    
@auth_bp.route("/users/delete/<int:user_id>")
def delete_user(user_id):
    if not session.get("user_id"):
        return redirect("/login")

    if not session.get("is_super_admin"):
        return "Доступ запрещен", 403

    conn = get_db()
    
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE id = %s",
        (user_id,)
    )

    user = cur.fetchone()

    if not user:
        conn.close()
        return "Пользователь не найден"

    # ❌ Creator вообще нельзя трогать
    if user["is_creator"]:
        conn.close()
        return "Создатель системы не может быть удален"

    # ❌ нельзя удалить самого себя (даже creator не сможет)
    if user_id == session.get("user_id"):
        conn.close()
        return "Нельзя удалить самого себя"

    # ❌ супер-админ не может удалять других владельцев
    if user["is_super_admin"] and not session.get("is_creator"):
        conn.close()
        return "Нельзя удалить владельца системы"

    # ✅ удаление
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()

    return redirect("/users")
    
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_db()
        
        cur = conn.cursor()

        # 🔐 пользователь
        username = request.form["username"]
        password = request.form["password"]

        # 🏢 компания (твоя форма)
        name = request.form["name"]
        director = request.form.get("director")
        bin = request.form.get("bin")
        address = request.form.get("address")
        phone = request.form.get("phone")
        iik = request.form.get("iik")
        bik = request.form.get("bik")
        bank = request.form.get("bank")
        kbe = request.form.get("kbe")
        knp = request.form.get("knp")

        # 1. создаём компанию
        cur.execute("""
            INSERT INTO companies (
                name, director, bin, address, phone,
                iik, bik, bank, kbe, knp, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            name,
            director,
            bin,
            address,
            phone,
            iik,
            bik,
            bank,
            kbe,
            knp,
            True
        ))

        company_id = cur.fetchone()["id"]

        # 2. создаём владельца
        cur.execute("""
            INSERT INTO users (username, password, role, company_id)
            VALUES (%s, %s, %s, %s)
        """, (username, password, "admin", company_id))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")