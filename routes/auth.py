from flask import Blueprint, render_template, request, redirect, session, url_for, jsonify
from models import get_db, pool
from utils.timezone import now_kz
from datetime import timedelta

auth_bp = Blueprint("auth", __name__)

ONLINE_TIMEOUT_MINUTES = 3
HEARTBEAT_INTERVAL_SECONDS = 45

# Тарифы лендинга. Код сохраняется в companies.tariff, а цена — в подписке.
# Не принимаем произвольные значения из URL/формы.
REGISTRATION_PLANS = {
    "start": {"name": "Старт", "price": 9900},
    "business": {"name": "Бизнес", "price": 19900},
    "pro": {"name": "Профи", "price": 29900},
}
DEFAULT_REGISTRATION_PLAN = "business"


def normalize_registration_plan(value):
    code = (value or "").strip().lower()
    return code if code in REGISTRATION_PLANS else DEFAULT_REGISTRATION_PLAN


@auth_bp.before_app_request
def update_user_presence():
    """Обновляет время активности авторизованного пользователя без записи в БД на каждый запрос."""
    user_id = session.get("user_id")
    if not user_id:
        return

    current_time = now_kz()
    last_heartbeat_raw = session.get("presence_heartbeat_at")

    if last_heartbeat_raw:
        try:
            last_heartbeat = current_time.fromisoformat(last_heartbeat_raw)
            if (current_time - last_heartbeat).total_seconds() < HEARTBEAT_INTERVAL_SECONDS:
                return
        except (TypeError, ValueError):
            pass

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET last_seen_at = %s WHERE id = %s",
            (current_time, user_id)
        )
        conn.commit()
        session["presence_heartbeat_at"] = current_time.isoformat()
    except Exception:
        conn.rollback()
    finally:
        cur.close()
        pool.putconn(conn)

def load_user_module_codes(user):
    """Возвращает коды модулей, доступных конкретному пользователю."""
    if not user:
        return []

    conn = get_db()
    cur = conn.cursor()

    try:
        # Супер-админ видит все активные модули.
        if bool(user.get("is_super_admin")):
            cur.execute("""
                SELECT code
                FROM modules
                WHERE is_active = TRUE
                ORDER BY sort_order, id
            """)
            return [row["code"] for row in cur.fetchall()]

        company_id = user.get("company_id")
        if not company_id:
            return ["profile"]

        # Администратор компании видит все подключённые компании модули.
        if user.get("role") in ("admin", "owner"):
            cur.execute("""
                SELECT m.code
                FROM modules m
                JOIN company_modules cm ON cm.module_id = m.id
                WHERE cm.company_id = %s
                  AND cm.enabled = TRUE
                  AND m.is_active = TRUE
                ORDER BY m.sort_order, m.id
            """, (company_id,))
            return [row["code"] for row in cur.fetchall()]

        # Обычный сотрудник видит только явно разрешённые ему модули.
        cur.execute("""
            SELECT m.code
            FROM modules m
            JOIN company_modules cm
              ON cm.module_id = m.id
             AND cm.company_id = %s
             AND cm.enabled = TRUE
            JOIN employee_module_permissions emp
              ON emp.module_id = m.id
             AND emp.employee_id = %s
             AND emp.allowed = TRUE
            WHERE m.is_active = TRUE
            ORDER BY m.sort_order, m.id
        """, (company_id, user["id"]))

        codes = [row["code"] for row in cur.fetchall()]

        # Профиль оставляем безопасным запасным разделом.
        if "profile" not in codes:
            codes.insert(0, "profile")

        return codes

    finally:
        cur.close()
        pool.putconn(conn)



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


@auth_bp.before_app_request
def refresh_current_user_access():
    """
    Синхронизирует роль, компанию и доступные модули с базой данных.

    Благодаря этому включённые/отключённые в подписке модули появляются
    в меню сразу после следующего запроса, без выхода из аккаунта.
    """
    if not session.get("user_id"):
        return

    user = current_user()
    if not user:
        session.clear()
        return redirect("/login")

    user = dict(user)

    session["role"] = user.get("role") or "employee"
    session["company_id"] = user.get("company_id")
    session["is_super_admin"] = bool(user.get("is_super_admin"))
    session["employee_modules"] = load_user_module_codes(user)

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

        if user:
            login_time = now_kz()
            cur.execute(
                "UPDATE users SET last_login_at = %s, last_seen_at = %s WHERE id = %s",
                (login_time, login_time, user["id"])
            )
            conn.commit()
            user = dict(user)
            user["last_login_at"] = login_time
            user["last_seen_at"] = login_time

        cur.close()
        pool.putconn(conn)
        
        if user:
            print("USER COMPANY:", user["company_id"])
        else:
            print("USER NOT FOUND")

        if not user:
            return render_template("login.html", error="Неверный логин или пароль")

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"] or "employee"
        session["company_id"] = user["company_id"]
        session["full_name"] = user["full_name"]
        session["phone"] = user["phone"]
        session["percent_rate"] = user["percent_rate"]
        session["is_super_admin"] = bool(user["is_super_admin"])
        session["is_creator"] = False  # устаревшее поле: права определяются через role
        session["employee_modules"] = load_user_module_codes(user)
        session["presence_heartbeat_at"] = now_kz().isoformat()
        
        session.permanent = True

        # 👑 Супер админ
        if user["is_super_admin"]:
            return redirect("/companies")

        # 🏢 Владелец / администратор компании
        if user["role"] in ("admin", "owner"):
            return redirect("/analytics")

        # 👤 Обычный сотрудник
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

    if user:
        login_time = now_kz()
        cur.execute(
            "UPDATE users SET last_login_at = %s, last_seen_at = %s WHERE id = %s",
            (login_time, login_time, user["id"])
        )
        conn.commit()
        user = dict(user)
        user["last_login_at"] = login_time
        user["last_seen_at"] = login_time

    cur.close()
    pool.putconn(conn)

    if not user:
        return jsonify({
            "success": False,
            "message": "Неверный логин или пароль"
        })
        
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"] or "employee"
    session["company_id"] = user["company_id"]
    session["full_name"] = user["full_name"]
    session["phone"] = user["phone"]
    session["percent_rate"] = user["percent_rate"]
    session["is_super_admin"] = bool(user["is_super_admin"])
    session["is_creator"] = False  # устаревшее поле: права определяются через role
    session["employee_modules"] = load_user_module_codes(user)
    session["presence_heartbeat_at"] = now_kz().isoformat()
    
    session.permanent = True

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
    user_id = session.get("user_id")

    if user_id:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE users SET last_seen_at = NULL WHERE id = %s",
                (user_id,)
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            cur.close()
            pool.putconn(conn)

    session.clear()
    return redirect("/login")

@auth_bp.route("/users", methods=["GET", "POST"])
def users():
    if not session.get("user_id"):
        return redirect("/login")

    is_super_admin = bool(session.get("is_super_admin"))
    is_root_admin = is_super_admin and session.get("username") == "admin"
    current_company_id = session.get("company_id")
    current_role = session.get("role")

    if not is_super_admin and current_role not in ("admin", "owner"):
        return "Доступ запрещен", 403

    conn = get_db()
    cur = conn.cursor()

    try:
        if request.method == "POST":
            user_id_raw = request.form.get("user_id", "").strip()
            editing_user_id = int(user_id_raw) if user_id_raw.isdigit() else None

            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            role = request.form.get("role", "employee").strip()
            position = request.form.get("position", "").strip()
            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            percent_rate = request.form.get("percent_rate") or 0
            selected_module_ids = set(request.form.getlist("module_ids"))

            if not username:
                return "Укажите логин", 400

            if not editing_user_id and not password:
                return "Укажите пароль", 400

            # Проверяем редактируемого пользователя и права на него.
            editing_user = None
            if editing_user_id:
                cur.execute(
                    "SELECT * FROM users WHERE id = %s",
                    (editing_user_id,)
                )
                editing_user = cur.fetchone()

                if not editing_user:
                    return "Пользователь не найден", 404

                is_editing_self = editing_user.get("id") == session.get("user_id")
                target_is_super_admin = bool(editing_user.get("is_super_admin"))

                # Главная системная учётная запись admin может управлять всеми.
                # Обычный супер-администратор может редактировать себя,
                # владельцев компаний и обычных пользователей, но не других SUPER.
                if (
                    target_is_super_admin
                    and not is_editing_self
                    and not is_root_admin
                ):
                    return "Только главная учётная запись admin может редактировать других супер-администраторов", 403

                # Владелец/администратор компании не может редактировать владельца.
                if (
                    editing_user.get("role") == "owner"
                    and not is_super_admin
                    and not is_editing_self
                ):
                    return "Владельца компании нельзя редактировать администратору", 403

                if (
                    not is_super_admin
                    and editing_user.get("company_id") != current_company_id
                ):
                    return "Нельзя редактировать пользователя другой компании", 403

            if is_super_admin:
                company_id = request.form.get("company_id") or None
                requested_super_admin = request.form.get("is_super_admin") == "1"

                if is_root_admin:
                    new_is_super_admin = requested_super_admin
                elif editing_user_id == session.get("user_id"):
                    # Обычный SUPER может редактировать себя, но не снять с себя
                    # системные полномочия через форму.
                    new_is_super_admin = True
                else:
                    # Только корневая учётная запись admin назначает SUPER.
                    new_is_super_admin = bool(
                        editing_user and editing_user.get("is_super_admin")
                    )
            else:
                company_id = current_company_id
                new_is_super_admin = False

                # В компании может быть только один владелец.
                # Обычный владелец/администратор не может назначить второго owner.
                if role == "owner":
                    role = "admin"

            allowed_roles = {"owner", "admin", "employee"}
            if role not in allowed_roles:
                role = "employee"

            if not company_id and not new_is_super_admin:
                return "Для пользователя необходимо выбрать компанию", 400

            # Логин должен быть уникальным.
            if editing_user_id:
                cur.execute(
                    "SELECT id FROM users WHERE username = %s AND id <> %s",
                    (username, editing_user_id)
                )
            else:
                cur.execute(
                    "SELECT id FROM users WHERE username = %s",
                    (username,)
                )

            if cur.fetchone():
                return "Пользователь с таким логином уже существует", 400

            if (
                editing_user_id == session.get("user_id")
                and is_root_admin
            ):
                username = "admin"
                new_is_super_admin = True
                company_id = None

            if editing_user_id:
                if password:
                    cur.execute("""
                        UPDATE users
                        SET username = %s,
                            password = %s,
                            role = %s,
                            position = %s,
                            company_id = %s,
                            full_name = %s,
                            phone = %s,
                            percent_rate = %s,
                            is_super_admin = %s
                        WHERE id = %s
                    """, (
                        username,
                        password,
                        role,
                        position,
                        company_id,
                        full_name,
                        phone,
                        percent_rate,
                        new_is_super_admin,
                        editing_user_id
                    ))
                else:
                    cur.execute("""
                        UPDATE users
                        SET username = %s,
                            role = %s,
                            position = %s,
                            company_id = %s,
                            full_name = %s,
                            phone = %s,
                            percent_rate = %s,
                            is_super_admin = %s
                        WHERE id = %s
                    """, (
                        username,
                        role,
                        position,
                        company_id,
                        full_name,
                        phone,
                        percent_rate,
                        new_is_super_admin,
                        editing_user_id
                    ))

                employee_id = editing_user_id
            else:
                cur.execute("""
                    INSERT INTO users (
                        username,
                        password,
                        role,
                        position,
                        company_id,
                        full_name,
                        phone,
                        percent_rate,
                        is_super_admin,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    username,
                    password,
                    role,
                    position,
                    company_id,
                    full_name,
                    phone,
                    percent_rate,
                    new_is_super_admin,
                    now_kz()
                ))
                employee_id = cur.fetchone()["id"]

            # Полностью обновляем права сотрудника.
            cur.execute(
                "DELETE FROM employee_module_permissions WHERE employee_id = %s",
                (employee_id,)
            )

            if not new_is_super_admin and company_id:
                cur.execute("""
                    SELECT m.id
                    FROM modules m
                    JOIN company_modules cm ON cm.module_id = m.id
                    WHERE cm.company_id = %s
                      AND cm.enabled = TRUE
                      AND m.is_active = TRUE
                """, (company_id,))

                company_module_ids = {
                    str(row["id"]) for row in cur.fetchall()
                }

                for module_id in company_module_ids:
                    cur.execute("""
                        INSERT INTO employee_module_permissions (
                            employee_id,
                            module_id,
                            allowed
                        )
                        VALUES (%s, %s, %s)
                        ON CONFLICT (employee_id, module_id)
                        DO UPDATE SET allowed = EXCLUDED.allowed
                    """, (
                        employee_id,
                        int(module_id),
                        module_id in selected_module_ids
                    ))

            conn.commit()
            return redirect("/users")

        if is_super_admin:
            cur.execute("""
                SELECT users.*, companies.name AS company_name,
                       CASE
                           WHEN users.last_seen_at IS NOT NULL
                            AND users.last_seen_at >= NOW() - INTERVAL '3 minutes'
                           THEN TRUE ELSE FALSE
                       END AS is_online
                FROM users
                LEFT JOIN companies ON users.company_id = companies.id
                ORDER BY users.id DESC
            """)
            users_list = cur.fetchall()

            cur.execute("""
                SELECT *
                FROM companies
                ORDER BY id DESC
            """)
            companies = cur.fetchall()

            cur.execute("""
                SELECT id, code, name, description, category, icon, is_core
                FROM modules
                WHERE is_active = TRUE
                ORDER BY sort_order, name
            """)
            available_modules = cur.fetchall()
        else:
            cur.execute("""
                SELECT users.*, companies.name AS company_name,
                       CASE
                           WHEN users.last_seen_at IS NOT NULL
                            AND users.last_seen_at >= NOW() - INTERVAL '3 minutes'
                           THEN TRUE ELSE FALSE
                       END AS is_online
                FROM users
                LEFT JOIN companies ON users.company_id = companies.id
                WHERE users.company_id = %s
                ORDER BY users.id DESC
            """, (current_company_id,))
            users_list = cur.fetchall()

            cur.execute("""
                SELECT *
                FROM companies
                WHERE id = %s
            """, (current_company_id,))
            companies = cur.fetchall()

            cur.execute("""
                SELECT
                    m.id,
                    m.code,
                    m.name,
                    m.description,
                    m.category,
                    m.icon,
                    m.is_core
                FROM modules m
                JOIN company_modules cm ON cm.module_id = m.id
                WHERE cm.company_id = %s
                  AND cm.enabled = TRUE
                  AND m.is_active = TRUE
                ORDER BY m.sort_order, m.name
            """, (current_company_id,))
            available_modules = cur.fetchall()

        user_ids = [row["id"] for row in users_list]
        permissions_by_user = {}

        if user_ids:
            cur.execute("""
                SELECT employee_id, module_id
                FROM employee_module_permissions
                WHERE employee_id = ANY(%s)
                  AND allowed = TRUE
            """, (user_ids,))

            for row in cur.fetchall():
                permissions_by_user.setdefault(
                    str(row["employee_id"]), []
                ).append(str(row["module_id"]))

        users_edit_data = {}
        for row in users_list:
            row_dict = dict(row)
            users_edit_data[str(row["id"])] = {
                "id": row["id"],
                "username": row.get("username") or "",
                "password": row.get("password") or "",
                "full_name": row.get("full_name") or "",
                "phone": row.get("phone") or "",
                "percent_rate": str(row.get("percent_rate") or 0),
                "role": row.get("role") or "employee",
                "position": row.get("position") or "",
                "last_login_at": row.get("last_login_at").isoformat() if row.get("last_login_at") else "",
                "last_seen_at": row.get("last_seen_at").isoformat() if row.get("last_seen_at") else "",
                "is_online": bool(row.get("is_online")),
                "company_id": str(row.get("company_id") or ""),
                "is_super_admin": bool(row.get("is_super_admin")),
                "is_creator": bool(row.get("is_creator")),
                "module_ids": permissions_by_user.get(str(row["id"]), [])
            }

        return render_template(
            "users.html",
            users=users_list,
            companies=companies,
            available_modules=available_modules,
            can_choose_company=is_super_admin,
            can_create_super_admin=is_super_admin,
            users_edit_data=users_edit_data
        )

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)

@auth_bp.route("/api/users/presence")
def users_presence():
    if not session.get("user_id"):
        return jsonify({"success": False}), 401

    is_super_admin = bool(session.get("is_super_admin"))
    is_root_admin = is_super_admin and session.get("username") == "admin"
    current_company_id = session.get("company_id")
    current_role = session.get("role")

    if not is_super_admin and current_role not in ("admin", "owner"):
        return jsonify({"success": False}), 403

    conn = get_db()
    cur = conn.cursor()
    try:
        if is_super_admin:
            cur.execute("""
                SELECT id, last_login_at, last_seen_at,
                       CASE
                           WHEN last_seen_at IS NOT NULL
                            AND last_seen_at >= NOW() - INTERVAL '3 minutes'
                           THEN TRUE ELSE FALSE
                       END AS is_online
                FROM users
            """)
        else:
            cur.execute("""
                SELECT id, last_login_at, last_seen_at,
                       CASE
                           WHEN last_seen_at IS NOT NULL
                            AND last_seen_at >= NOW() - INTERVAL '3 minutes'
                           THEN TRUE ELSE FALSE
                       END AS is_online
                FROM users
                WHERE company_id = %s
            """, (current_company_id,))

        users_data = []
        for row in cur.fetchall():
            users_data.append({
                "id": row["id"],
                "is_online": bool(row.get("is_online")),
                "last_login_at": row.get("last_login_at").isoformat() if row.get("last_login_at") else None,
                "last_seen_at": row.get("last_seen_at").isoformat() if row.get("last_seen_at") else None
            })

        return jsonify({"success": True, "users": users_data})
    finally:
        cur.close()
        pool.putconn(conn)


@auth_bp.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")
    company_id = session.get("company_id")

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                u.*,
                c.name AS company_name,
                c.bin AS company_bin,
                c.address AS company_address,
                c.phone AS company_phone,
                c.iik AS company_iik,
                c.bik AS company_bik,
                c.bank AS company_bank,
                c.kbe AS company_kbe,
                c.knp AS company_knp,
                c.director AS company_director,
                COALESCE(c.is_vat_payer, FALSE) AS company_is_vat_payer
            FROM users u
            LEFT JOIN companies c ON c.id = u.company_id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()

        if not user:
            return redirect("/logout")

        company = None
        if company_id:
            cur.execute("SELECT * FROM companies WHERE id = %s", (company_id,))
            company = cur.fetchone()

        return render_template(
            "profile.html",
            user=user,
            company=company,
            can_manage_company=bool(
                session.get("is_super_admin")
                or session.get("role") in ("owner", "admin")
            ),
        )
    finally:
        cur.close()
        pool.putconn(conn)


@auth_bp.route("/profile/personal", methods=["POST"])
def save_personal_profile():
    if not session.get("user_id"):
        return redirect("/login")

    full_name = (request.form.get("full_name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    position = (request.form.get("position") or "").strip()

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users
            SET full_name = %s,
                phone = %s,
                position = %s
            WHERE id = %s
        """, (full_name, phone, position, session["user_id"]))
        conn.commit()
        session["full_name"] = full_name
        session["phone"] = phone
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)

    return redirect("/profile?tab=personal&saved=1")


@auth_bp.route("/users/delete/<int:user_id>")
def delete_user(user_id):
    if not session.get("user_id"):
        return redirect("/login")

    is_super_admin = bool(session.get("is_super_admin"))
    is_root_admin = is_super_admin and session.get("username") == "admin"
    current_company_id = session.get("company_id")
    current_role = session.get("role")

    if not is_super_admin and current_role not in ("admin", "owner"):
        return "Доступ запрещен", 403

    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT * FROM users WHERE id = %s",
            (user_id,)
        )
        user = cur.fetchone()

        if not user:
            return "Пользователь не найден", 404

        # Любой пользователь защищён от удаления самого себя.
        if user_id == session.get("user_id"):
            return "Нельзя удалить самого себя", 403

        target_is_super_admin = bool(user.get("is_super_admin"))

        # Других SUPER может удалять только главная учётная запись admin.
        if target_is_super_admin and not is_root_admin:
            return "Только главная учётная запись admin может удалять супер-администраторов", 403

        # Владелец компании доступен для удаления только системному SUPER.
        if user.get("role") == "owner" and not is_super_admin:
            return "Владельца компании может удалить только супер-администратор", 403

        # Владелец/администратор компании управляет только своей компанией.
        if not is_super_admin:
            if user.get("company_id") != current_company_id:
                return "Доступ запрещен", 403

            if target_is_super_admin:
                return "Нельзя удалить супер-администратора", 403

        cur.execute(
            "DELETE FROM employee_module_permissions WHERE employee_id = %s",
            (user_id,)
        )
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()

        return redirect("/users")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
    
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    selected_plan = normalize_registration_plan(
        request.form.get("plan")
        or request.args.get("plan")
        or session.get("selected_plan")
    )
    selected_plan_info = REGISTRATION_PLANS[selected_plan]

    # Сохраняем выбор до завершения регистрации, даже если форма отправляется
    # без query-параметра ?plan=...
    session["selected_plan"] = selected_plan

    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()

        try:
            # Аккаунт владельца
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            # Компания
            name = request.form.get("name", "").strip()
            director = request.form.get("director", "").strip()
            bin = request.form.get("bin", "").strip()
            address = request.form.get("address", "").strip()
            phone = request.form.get("phone", "").strip()
            iik = request.form.get("iik", "").strip()
            bik = request.form.get("bik", "").strip()
            bank = request.form.get("bank", "").strip()
            kbe = request.form.get("kbe", "").strip()
            knp = request.form.get("knp", "").strip()

            if not username or not password or not name:
                return render_template(
                    "register.html",
                    error="Укажите название компании, логин и пароль.",
                    form=request.form,
                    selected_plan=selected_plan,
                    selected_plan_info=selected_plan_info,
                )

            if len(password) < 6:
                return render_template(
                    "register.html",
                    error="Пароль должен содержать минимум 6 символов.",
                    form=request.form,
                    selected_plan=selected_plan,
                    selected_plan_info=selected_plan_info,
                )

            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            if cur.fetchone():
                return render_template(
                    "register.html",
                    error="Такой логин уже используется.",
                    form=request.form,
                    selected_plan=selected_plan,
                    selected_plan_info=selected_plan_info,
                )

            # 1. Компания
            cur.execute("""
                INSERT INTO companies (
                    name, director, bin, address, phone,
                    iik, bik, bank, kbe, knp, tariff, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                RETURNING id
            """, (
                name, director or None, bin or None, address or None, phone or None,
                iik or None, bik or None, bank or None, kbe or None, knp or None,
                selected_plan,
            ))
            company_id = cur.fetchone()["id"]

            # 2. Владелец
            cur.execute("""
                INSERT INTO users (
                    username, password, role, position, company_id,
                    full_name, phone, is_super_admin, created_at
                )
                VALUES (%s, %s, 'owner', 'Владелец', %s, %s, %s, FALSE, %s)
                RETURNING id
            """, (
                username,
                password,
                company_id,
                director or username,
                phone or None,
                now_kz()
            ))
            owner_id = cur.fetchone()["id"]

            cur.execute(
                "UPDATE companies SET owner_id = %s WHERE id = %s",
                (owner_id, company_id)
            )

            # 3. Trial
            cur.execute("""
                INSERT INTO company_subscriptions (
                    company_id, status, billing_period, base_price,
                    trial_ends_at, period_start, next_payment_at
                )
                VALUES (
                    %s, 'trial', 'month', %s,
                    NOW() + INTERVAL '14 days',
                    NOW(),
                    NOW() + INTERVAL '14 days'
                )
                ON CONFLICT (company_id) DO NOTHING
            """, (company_id, selected_plan_info["price"]))

            # 4. Базовые модули
            cur.execute("""
                INSERT INTO company_modules (
                    company_id, module_id, enabled, status, price, billing_period
                )
                SELECT %s, id, TRUE, 'trial', monthly_price, 'month'
                FROM modules
                WHERE is_core = TRUE
                   OR code IN ('sales', 'catalog', 'warehouse', 'clients', 'analytics')
                ON CONFLICT (company_id, module_id) DO NOTHING
            """, (company_id,))

            conn.commit()

            # 5. Сразу авторизуем НОВОГО владельца.
            user = {
                "id": owner_id,
                "username": username,
                "role": "owner",
                "company_id": company_id,
                "full_name": director or username,
                "phone": phone or None,
                "percent_rate": 0,
                "is_super_admin": False,
            }

            session.clear()
            session["user_id"] = owner_id
            session["username"] = username
            session["role"] = "owner"
            session["company_id"] = company_id
            session["full_name"] = director or username
            session["phone"] = phone or None
            session["percent_rate"] = 0
            session["is_super_admin"] = False
            session["is_creator"] = False
            session["selected_plan"] = selected_plan
            session["selected_plan_label"] = selected_plan_info["name"]
            session["selected_plan_price"] = selected_plan_info["price"]
            session["employee_modules"] = load_user_module_codes(user)
            session["presence_heartbeat_at"] = now_kz().isoformat()
            
            session.permanent = True

            # После настоящей регистрации продолжаем настройку этой же компании.
            return redirect("/onboarding")

        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            pool.putconn(conn)

    return render_template(
        "register.html",
        selected_plan=selected_plan,
        selected_plan_info=selected_plan_info,
    )
