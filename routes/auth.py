from flask import Blueprint, render_template, request, redirect, session, url_for
from models import get_db, pool
from utils.timezone import now_kz

auth_bp = Blueprint("auth", __name__)

from flask import jsonify

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE id = %s",
            (user_id,)
        )

        return cur.fetchone()

    finally:
        cur.close()
        pool.putconn(conn)

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
        pool.putconn(conn)
        
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
        session["full_name"] = user["full_name"]
        session["phone"] = user["phone"]
        session["percent_rate"] = user["percent_rate"]
        session["is_super_admin"] = bool(user["is_super_admin"])
        session["is_creator"] = bool(user["is_creator"]) if "is_creator" in user.keys() else False

        # 👑 Супер админ
        if user["is_super_admin"]:
            return redirect("/companies")

        # 🏢 Админ компании
        if user["role"] == "admin":
            return redirect("/company/profile")

        # 👤 Кассир
        return redirect("/profile")

    return render_template("login.html")
    
@auth_bp.route("/api/login", methods=["POST"])
def api_login():

    data = request.get_json()

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM users
        WHERE username = %s
        AND password = %s
        """,
        (username, password)
    )

    user = cur.fetchone()

    pool.putconn(conn)

    if not user:
        return jsonify({
            "success": False,
            "message": "Неверный логин или пароль"
        })
        
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"] or "cashier"
    session["company_id"] = user["company_id"]
    session["full_name"] = user["full_name"]
    session["phone"] = user["phone"]
    session["percent_rate"] = user["percent_rate"]
    session["is_super_admin"] = bool(user["is_super_admin"])
    session["is_creator"] = bool(user["is_creator"]) if "is_creator" in user.keys() else False

    return jsonify({
        "success": True,
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "company_id": user["company_id"],
        "is_super_admin": bool(user["is_super_admin"])
    })

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
        is_super_admin = True if request.form.get("is_super_admin") == "1" else False
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        percent_rate = request.form.get("percent_rate") or 0

        cur.execute("""
            INSERT INTO users (
                username,
                password,
                role,
                company_id,
                full_name,
                phone,
                percent_rate,
                is_super_admin,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            username,
            password,
            role,
            company_id if company_id else None,
            full_name,
            phone,
            percent_rate,
            is_super_admin,
            now_kz()
        ))
        conn.commit()
        pool.putconn(conn)
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

    pool.putconn(conn)

    return render_template("users.html", users=users, companies=companies)
    
@auth_bp.route("/profile")
def profile():

    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")
    company_id = session.get("company_id")

    conn = get_db()
    cur = conn.cursor()

    try:
        # Сотрудник + полная информация о компании
        cur.execute("""
            SELECT
                u.*,
                c.name AS company_name,
                c.bin AS company_bin,
                c.address AS company_address,
                c.phone AS company_phone,
                c.director AS company_director,
                c.tariff AS company_tariff,
                c.paid_until AS company_paid_until
            FROM users u
            LEFT JOIN companies c
                ON c.id = u.company_id
            WHERE u.id = %s
        """, (
            user_id,
        ))

        user = cur.fetchone()

        if not user:
            return redirect("/logout")

        today = now_kz().date()
        month_start = today.replace(day=1)

        # Личная статистика за сегодня
        cur.execute("""
            SELECT
                COUNT(*) AS sales_count,
                COALESCE(SUM(total_amount), 0) AS revenue,
                COALESCE(AVG(total_amount), 0) AS average_check
            FROM sales
            WHERE company_id = %s
              AND user_id = %s
              AND status = 'Оплачено'
              AND DATE(created_at) = %s
        """, (
            company_id,
            user_id,
            today,
        ))

        today_stats = cur.fetchone()

        # Личная статистика за текущий месяц
        cur.execute("""
            SELECT
                COUNT(*) AS sales_count,
                COALESCE(SUM(total_amount), 0) AS revenue,
                COALESCE(AVG(total_amount), 0) AS average_check
            FROM sales
            WHERE company_id = %s
              AND user_id = %s
              AND status = 'Оплачено'
              AND DATE(created_at) BETWEEN %s AND %s
        """, (
            company_id,
            user_id,
            month_start,
            today,
        ))

        month_stats = cur.fetchone()

        percent_rate = float(user.get("percent_rate") or 0)
        today_revenue = float(today_stats.get("revenue") or 0)
        month_revenue = float(month_stats.get("revenue") or 0)

        today_reward = today_revenue * percent_rate / 100
        month_reward = month_revenue * percent_rate / 100

        # Возвраты текущего сотрудника за месяц
        cur.execute("""
            SELECT
                COUNT(*) AS refund_count,
                COALESCE(SUM(total_amount), 0) AS refund_total
            FROM sales
            WHERE company_id = %s
              AND user_id = %s
              AND (
                    status = 'Возврат'
                    OR COALESCE(is_refunded, FALSE) = TRUE
              )
              AND DATE(created_at) BETWEEN %s AND %s
        """, (
            company_id,
            user_id,
            month_start,
            today,
        ))

        refund_stats = cur.fetchone()

        # Последние личные продажи
        cur.execute("""
            SELECT
                id,
                sale_number,
                total_amount,
                sale_type,
                status,
                created_at
            FROM sales
            WHERE company_id = %s
              AND user_id = %s
            ORDER BY id DESC
            LIMIT 10
        """, (
            company_id,
            user_id,
        ))

        recent_sales = cur.fetchall()

        return render_template(
            "profile.html",
            user=user,
            today_stats=today_stats,
            month_stats=month_stats,
            refund_stats=refund_stats,
            today_reward=today_reward,
            month_reward=month_reward,
            recent_sales=recent_sales,
            today=today,
            month_start=month_start
        )

    finally:
        cur.close()
        pool.putconn(conn)

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
        pool.putconn(conn)
        return "Пользователь не найден"

    # ❌ Creator вообще нельзя трогать
    if user["is_creator"]:
        pool.putconn(conn)
        return "Создатель системы не может быть удален"

    # ❌ нельзя удалить самого себя (даже creator не сможет)
    if user_id == session.get("user_id"):
        pool.putconn(conn)
        return "Нельзя удалить самого себя"

    # ❌ супер-админ не может удалять других владельцев
    if user["is_super_admin"] and not session.get("is_creator"):
        pool.putconn(conn)
        return "Нельзя удалить владельца системы"

    # ✅ удаление
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    pool.putconn(conn)

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
        
        # cur.execute("""
        #     INSERT INTO integrations (
        #         company_id,
        #         created_at
        #     )
        #     VALUES (%s, %s)
        # """, (
        #     company_id,
        #     now_kz()
        # ))

        # 2. создаём владельца
        cur.execute("""
            INSERT INTO users (username, password, role, company_id)
            VALUES (%s, %s, %s, %s)
        """, (username, password, "admin", company_id))

        conn.commit()
        pool.putconn(conn)

        return redirect("/login")

    return render_template("register.html")