import json
from io import BytesIO
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    current_app,
    jsonify,
    make_response,
    request,
    send_file,
    session,
)

from models import get_db, pool
from utils.timezone import now_kz
from routes.auth import load_user_module_codes
from routes.tasks import (
    TASK_PRIORITIES,
    TASK_STATUSES,
    _ensure_tasks_table,
)
from routes.expenses import (
    EXPENSE_CATEGORIES,
    PAYMENT_METHODS,
    _delete_expense_from_accounting,
    _ensure_expenses_table,
    _sync_expense_to_accounting,
)
from routes.accounting import (
    _debt_view,
    _document_view,
    _ensure_accounting_tables,
    _operation_view,
    _sync_accounting,
    _tax_event_view,
)


mobile_api_bp = Blueprint("mobile_api", __name__, url_prefix="/api/mobile")


def _guard(*, admin=False):
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Требуется авторизация"}), 401
    if not session.get("company_id"):
        return jsonify({"success": False, "error": "Компания не выбрана"}), 400
    if admin and not (
        session.get("is_super_admin")
        or session.get("role") in ("owner", "admin")
    ):
        return jsonify({"success": False, "error": "Недостаточно прав"}), 403
    return None


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clean(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


def _payload():
    return request.get_json(silent=True) or {}


def _date(value, *, required=False):
    raw = str(value or "").strip()
    if not raw and not required:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Некорректная дата")


def _amount(value):
    try:
        result = Decimal(str(value or "").replace(" ", "").replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Введите корректную сумму")
    if result <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    return result.quantize(Decimal("0.01"))


def _task_json(row):
    due_date = row.get("due_date")
    created_at = row.get("created_at")
    status = row.get("status") or "new"
    overdue = bool(
        due_date
        and due_date < now_kz().date()
        and status not in ("done", "cancelled")
    )
    return {
        "id": row["id"],
        "title": row.get("title") or "",
        "description": row.get("description") or "",
        "priority": row.get("priority") or "medium",
        "priority_label": TASK_PRIORITIES.get(row.get("priority"), "Средний"),
        "status": status,
        "status_label": TASK_STATUSES.get(status, "Новая"),
        "due_date": due_date.isoformat() if due_date else "",
        "due_date_label": due_date.strftime("%d.%m.%Y") if due_date else "Без срока",
        "assignee_id": row.get("assigned_user_id"),
        "assignee_name": row.get("assignee_name") or "Не назначен",
        "created_at": created_at.strftime("%d.%m.%Y %H:%M") if created_at else "—",
        "overdue": overdue,
    }


@mobile_api_bp.route("/modules")
def mobile_modules():
    denied = _guard()
    if denied:
        return denied

    user = {
        "id": session.get("user_id"),
        "company_id": session.get("company_id"),
        "role": session.get("role") or "employee",
        "is_super_admin": bool(session.get("is_super_admin")),
    }
    modules = load_user_module_codes(user)
    session["employee_modules"] = modules
    return jsonify({"success": True, "modules": modules})


@mobile_api_bp.route("/health")
def mobile_health():
    denied = _guard()
    if denied:
        return denied
    return jsonify({"success": True, "version": "3.1"})



@mobile_api_bp.route("/profile")
def mobile_profile():
    denied = _guard()
    if denied:
        return denied

    user_id = session["user_id"]
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.username, u.full_name, u.role, u.position, u.phone,
                   u.percent_rate, u.salary, c.name AS company_name
            FROM users u
            LEFT JOIN companies c ON c.id=u.company_id
            WHERE u.id=%s
        """, (user_id,))
        user = cur.fetchone() or {}

        today = now_kz().date()
        month_start = today.replace(day=1)
        cur.execute("""
            SELECT COUNT(*) sales_count, COALESCE(SUM(total_amount),0) revenue,
                   COALESCE(AVG(total_amount),0) average_check
            FROM sales
            WHERE company_id=%s AND user_id=%s AND status='Оплачено'
              AND DATE(created_at) BETWEEN %s AND %s
        """, (company_id, user_id, month_start, today))
        month = cur.fetchone() or {}

        cur.execute("""
            SELECT COUNT(*) sales_count, COALESCE(SUM(total_amount),0) revenue,
                   COALESCE(AVG(total_amount),0) average_check
            FROM sales
            WHERE company_id=%s AND user_id=%s AND status='Оплачено'
              AND DATE(created_at)=%s
        """, (company_id, user_id, today))
        today_stats = cur.fetchone() or {}

        cur.execute("""
            SELECT id, sale_number, total_amount, sale_type, status, created_at
            FROM sales
            WHERE company_id=%s AND user_id=%s
            ORDER BY id DESC LIMIT 10
        """, (company_id, user_id))
        recent_sales = cur.fetchall()

        cur.execute("""
            SELECT id, title, description, priority, status, due_date
            FROM tasks
            WHERE company_id=%s AND assigned_user_id=%s
            ORDER BY id DESC LIMIT 8
        """, (company_id, user_id))
        tasks = cur.fetchall()

        percent_rate = float(user.get("percent_rate") or 0)
        month_revenue = float(month.get("revenue") or 0)
        base_salary = float(user.get("salary") or 0)
        month_reward = month_revenue * percent_rate / 100

        return jsonify(_clean({
            "success": True,
            "user": user,
            "today": today_stats,
            "month": month,
            "salary": {
                "base": base_salary,
                "reward": month_reward,
                "payable": base_salary + month_reward,
                "percent_rate": percent_rate,
            },
            "recent_sales": recent_sales,
            "tasks": tasks,
        }))
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/school/leaders", methods=["GET", "POST"])
def mobile_school_leaders():
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            data = _payload()
            full_name = str(data.get("full_name") or "").strip()
            class_name = str(data.get("class_name") or "").strip()
            room = str(data.get("room") or "").strip()
            phone = str(data.get("phone") or "").strip()
            if not full_name:
                return jsonify({"success": False, "error": "Укажите ФИО"}), 400
            class_id = None
            if class_name:
                cur.execute("""
                    INSERT INTO school_classes(company_id,name,sort_order)
                    VALUES(%s,%s,100)
                    ON CONFLICT(company_id,name) DO UPDATE SET is_active=TRUE
                    RETURNING id
                """, (company_id, class_name))
                class_id = cur.fetchone()["id"]
            cur.execute("""
                INSERT INTO school_class_leaders(company_id,class_id,full_name,room,phone)
                VALUES(%s,%s,%s,%s,%s)
                RETURNING id
            """, (company_id,class_id,full_name,room,phone))
            conn.commit()

        cur.execute("""
            SELECT l.id,l.full_name,l.room,l.phone,l.class_id,c.name class_name
            FROM school_class_leaders l
            LEFT JOIN school_classes c ON c.id=l.class_id
            WHERE l.company_id=%s
            ORDER BY c.sort_order,c.name,l.full_name
        """, (company_id,))
        leaders = cur.fetchall()
        cur.execute("""
            SELECT id,name FROM school_classes
            WHERE company_id=%s AND is_active=TRUE
            ORDER BY sort_order,name
        """, (company_id,))
        classes = cur.fetchall()
        return jsonify(_clean({"success": True, "leaders": leaders, "classes": classes}))
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/school/leaders/<int:leader_id>", methods=["PATCH", "DELETE"])
def mobile_school_leader(leader_id):
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "DELETE":
            cur.execute("DELETE FROM school_class_leaders WHERE id=%s AND company_id=%s", (leader_id,company_id))
        else:
            data = _payload()
            full_name = str(data.get("full_name") or "").strip()
            class_name = str(data.get("class_name") or "").strip()
            room = str(data.get("room") or "").strip()
            phone = str(data.get("phone") or "").strip()
            if not full_name:
                return jsonify({"success": False, "error": "Укажите ФИО"}), 400
            class_id = None
            if class_name:
                cur.execute("""
                    INSERT INTO school_classes(company_id,name,sort_order)
                    VALUES(%s,%s,100)
                    ON CONFLICT(company_id,name) DO UPDATE SET is_active=TRUE
                    RETURNING id
                """, (company_id,class_name))
                class_id = cur.fetchone()["id"]
            cur.execute("""
                UPDATE school_class_leaders
                SET full_name=%s,class_id=%s,room=%s,phone=%s,updated_at=NOW()
                WHERE id=%s AND company_id=%s
            """, (full_name,class_id,room,phone,leader_id,company_id))
        conn.commit()
        return jsonify({"success": True})
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/school/meals", methods=["GET", "POST"])
def mobile_school_meals():
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    raw_date = request.args.get("date") if request.method == "GET" else (_payload().get("date"))
    try:
        meal_date = datetime.strptime(str(raw_date or date.today().isoformat()), "%Y-%m-%d").date()
    except ValueError:
        meal_date = date.today()

    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            data = _payload()
            rows = data.get("rows") or []
            for row in rows:
                class_id = int(row.get("class_id"))
                plan = int(row.get("plan_count") or 0)
                fact = int(row.get("fact_count") or 0)
                free = int(row.get("free_count") or 0)
                paid = int(row.get("paid_count") or 0)
                note = str(row.get("note") or "").strip()
                cur.execute("""
                    SELECT free_price,paid_price FROM school_meal_prices
                    WHERE company_id=%s AND effective_from<=%s
                    ORDER BY effective_from DESC LIMIT 1
                """, (company_id,meal_date))
                prices = cur.fetchone() or {"free_price": 0, "paid_price": 0}
                cur.execute("""
                    INSERT INTO school_meals(
                        company_id,class_id,meal_date,plan_count,fact_count,
                        free_count,paid_count,free_price,paid_price,note,created_by
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(company_id,class_id,meal_date) DO UPDATE SET
                        plan_count=EXCLUDED.plan_count,fact_count=EXCLUDED.fact_count,
                        free_count=EXCLUDED.free_count,paid_count=EXCLUDED.paid_count,
                        note=EXCLUDED.note,updated_at=NOW()
                """, (company_id,class_id,meal_date,plan,fact,free,paid,
                      prices["free_price"],prices["paid_price"],note,session["user_id"]))
            conn.commit()

        cur.execute("""
            SELECT free_price,paid_price FROM school_meal_prices
            WHERE company_id=%s AND effective_from<=%s
            ORDER BY effective_from DESC LIMIT 1
        """, (company_id,meal_date))
        prices = cur.fetchone() or {"free_price": 0, "paid_price": 0}
        cur.execute("""
            SELECT c.id class_id,c.name class_name,l.full_name leader_name,
                   m.id meal_id,COALESCE(m.plan_count,0) plan_count,
                   COALESCE(m.fact_count,0) fact_count,
                   COALESCE(m.free_count,0) free_count,
                   COALESCE(m.paid_count,0) paid_count,
                   COALESCE(m.note,'') note
            FROM school_classes c
            LEFT JOIN school_class_leaders l ON l.class_id=c.id AND l.company_id=c.company_id
            LEFT JOIN school_meals m ON m.class_id=c.id AND m.company_id=c.company_id AND m.meal_date=%s
            WHERE c.company_id=%s AND c.is_active=TRUE
            ORDER BY c.sort_order,c.name
        """, (meal_date,company_id))
        rows = cur.fetchall()
        totals = {
            "plan": sum(int(r["plan_count"] or 0) for r in rows),
            "fact": sum(int(r["fact_count"] or 0) for r in rows),
            "free": sum(int(r["free_count"] or 0) for r in rows),
            "paid": sum(int(r["paid_count"] or 0) for r in rows),
        }
        return jsonify(_clean({
            "success": True, "date": meal_date, "prices": prices,
            "rows": rows, "totals": totals
        }))
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/school/prices", methods=["POST"])
def mobile_school_prices():
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    data = _payload()
    effective_from = datetime.strptime(str(data.get("date") or date.today().isoformat()), "%Y-%m-%d").date()
    free_price = _amount(data.get("free_price") or 0)
    paid_price = _amount(data.get("paid_price") or 0)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO school_meal_prices(company_id,free_price,paid_price,effective_from)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT(company_id,effective_from)
            DO UPDATE SET free_price=EXCLUDED.free_price,paid_price=EXCLUDED.paid_price
        """, (company_id,free_price,paid_price,effective_from))
        conn.commit()
        return jsonify({"success": True})
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/tasks", methods=["GET", "POST"])
def mobile_tasks():
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_tasks_table(cur)
        if request.method == "POST":
            data = _payload()
            title = str(data.get("title") or "").strip()
            description = str(data.get("description") or "").strip()
            priority = str(data.get("priority") or "medium")
            assigned_user_id = data.get("assigned_user_id") or None
            due_date = _date(data.get("due_date"))
            if not title:
                return jsonify({"success": False, "error": "Укажите название задачи"}), 400
            if priority not in TASK_PRIORITIES:
                priority = "medium"
            if assigned_user_id:
                cur.execute(
                    "SELECT id FROM users WHERE id=%s AND company_id=%s",
                    (assigned_user_id, company_id),
                )
                if not cur.fetchone():
                    return jsonify({"success": False, "error": "Сотрудник не найден"}), 400
            cur.execute("""
                INSERT INTO tasks (
                    company_id, created_by, assigned_user_id, title,
                    description, priority, status, due_date, created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,'new',%s,%s)
                RETURNING id
            """, (
                company_id,
                session.get("user_id"),
                assigned_user_id,
                title,
                description or None,
                priority,
                due_date,
                now_kz(),
            ))
            task_id = cur.fetchone()["id"]
            conn.commit()
            return jsonify({"success": True, "id": task_id})

        conn.commit()
        cur.execute("""
            SELECT t.*, COALESCE(u.full_name,u.username) AS assignee_name
            FROM tasks t
            LEFT JOIN users u ON u.id=t.assigned_user_id
            WHERE t.company_id=%s
            ORDER BY
                CASE t.status WHEN 'in_progress' THEN 1 WHEN 'new' THEN 2
                     WHEN 'done' THEN 3 ELSE 4 END,
                CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2
                     WHEN 'medium' THEN 3 ELSE 4 END,
                t.due_date NULLS LAST, t.id DESC
            LIMIT 300
        """, (company_id,))
        tasks = [_task_json(row) for row in cur.fetchall()]
        cur.execute("""
            SELECT id, COALESCE(full_name,username) AS name
            FROM users WHERE company_id=%s ORDER BY name
        """, (company_id,))
        users = [dict(row) for row in cur.fetchall()]
        summary = {
            "total": len(tasks),
            "new": sum(1 for item in tasks if item["status"] == "new"),
            "in_progress": sum(1 for item in tasks if item["status"] == "in_progress"),
            "done": sum(1 for item in tasks if item["status"] == "done"),
            "overdue": sum(1 for item in tasks if item["overdue"]),
        }
        return jsonify({
            "success": True,
            "items": tasks,
            "users": users,
            "summary": summary,
            "statuses": TASK_STATUSES,
            "priorities": TASK_PRIORITIES,
        })
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        conn.rollback()
        print("MOBILE TASKS ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось обработать задачи"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/tasks/<int:task_id>", methods=["PATCH", "DELETE"])
def mobile_task(task_id):
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_tasks_table(cur)
        if request.method == "DELETE":
            cur.execute(
                "DELETE FROM tasks WHERE id=%s AND company_id=%s RETURNING id",
                (task_id, company_id),
            )
            if not cur.fetchone():
                return jsonify({"success": False, "error": "Задача не найдена"}), 404
            conn.commit()
            return jsonify({"success": True})

        data = _payload()
        status = str(data.get("status") or "")
        if status and status not in TASK_STATUSES:
            return jsonify({"success": False, "error": "Некорректный статус"}), 400
        cur.execute(
            "SELECT * FROM tasks WHERE id=%s AND company_id=%s",
            (task_id, company_id),
        )
        old = cur.fetchone()
        if not old:
            return jsonify({"success": False, "error": "Задача не найдена"}), 404
        title = str(data.get("title", old.get("title") or "")).strip()
        priority = str(data.get("priority", old.get("priority") or "medium"))
        final_status = status or old.get("status") or "new"
        if not title:
            return jsonify({"success": False, "error": "Укажите название задачи"}), 400
        if priority not in TASK_PRIORITIES:
            priority = "medium"
        due_date = _date(data.get("due_date")) if "due_date" in data else old.get("due_date")
        cur.execute("""
            UPDATE tasks SET title=%s, description=%s, priority=%s, status=%s,
                assigned_user_id=%s, due_date=%s,
                completed_at=%s, updated_at=%s
            WHERE id=%s AND company_id=%s RETURNING id
        """, (
            title,
            str(data.get("description", old.get("description") or "")).strip() or None,
            priority,
            final_status,
            data.get("assigned_user_id", old.get("assigned_user_id")) or None,
            due_date,
            now_kz() if final_status == "done" else None,
            now_kz(),
            task_id,
            company_id,
        ))
        conn.commit()
        return jsonify({"success": True})
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        conn.rollback()
        print("MOBILE TASK ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось изменить задачу"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


def _expense_json(row):
    return {
        "id": row["id"],
        "category": row.get("category") or "",
        "description": row.get("description") or "",
        "amount": _number(row.get("amount")),
        "payment_method": row.get("payment_method") or "",
        "comment": row.get("comment") or "",
        "date": row.get("date").isoformat() if row.get("date") else "",
        "date_label": row.get("date").strftime("%d.%m.%Y") if row.get("date") else "—",
        "source_type": row.get("source_type"),
        "is_automatic": bool(row.get("source_type")),
    }


@mobile_api_bp.route("/expenses", methods=["GET", "POST"])
def mobile_expenses():
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_expenses_table(cur)
        if request.method == "POST":
            data = _payload()
            category = str(data.get("category") or "").strip()
            description = str(data.get("description") or "").strip()
            payment_method = str(data.get("payment_method") or "").strip()
            if category not in EXPENSE_CATEGORIES:
                raise ValueError("Выберите категорию")
            if not description:
                raise ValueError("Укажите описание расхода")
            if payment_method not in PAYMENT_METHODS:
                raise ValueError("Выберите способ оплаты")
            cur.execute("""
                INSERT INTO expenses (
                    company_id,user_id,category,description,amount,
                    payment_method,comment,date,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (
                company_id,
                session.get("user_id"),
                category,
                description[:160],
                _amount(data.get("amount")),
                payment_method,
                str(data.get("comment") or "")[:500],
                _date(data.get("date"), required=True),
                now_kz(),
            ))
            expense_id = cur.fetchone()["id"]
            _sync_expense_to_accounting(cur, expense_id, company_id)
            conn.commit()
            return jsonify({"success": True, "id": expense_id})

        conn.commit()
        cur.execute("""
            SELECT * FROM expenses WHERE company_id=%s
            ORDER BY date DESC,id DESC LIMIT 300
        """, (company_id,))
        rows = cur.fetchall()
        items = [_expense_json(row) for row in rows]
        today = now_kz().date()
        month_start = today.replace(day=1)
        today_total = sum(item["amount"] for item in items if item["date"] == today.isoformat())
        month_total = sum(
            item["amount"] for item in items
            if item["date"] and month_start.isoformat() <= item["date"] <= today.isoformat()
        )
        return jsonify({
            "success": True,
            "items": items,
            "categories": EXPENSE_CATEGORIES,
            "payment_methods": sorted(PAYMENT_METHODS),
            "summary": {"today": today_total, "month": month_total, "count": len(items)},
        })
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        conn.rollback()
        print("MOBILE EXPENSES ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось обработать расходы"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/expenses/<int:expense_id>", methods=["PATCH", "DELETE"])
def mobile_expense(expense_id):
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_expenses_table(cur)
        cur.execute(
            "SELECT * FROM expenses WHERE id=%s AND company_id=%s",
            (expense_id, company_id),
        )
        old = cur.fetchone()
        if not old:
            return jsonify({"success": False, "error": "Расход не найден"}), 404
        if old.get("source_type"):
            return jsonify({"success": False, "error": "Автоматический расход меняется в исходном разделе"}), 409
        if request.method == "DELETE":
            cur.execute("DELETE FROM expenses WHERE id=%s AND company_id=%s", (expense_id, company_id))
            _delete_expense_from_accounting(cur, expense_id, company_id)
            conn.commit()
            return jsonify({"success": True})

        data = _payload()
        category = str(data.get("category", old.get("category")) or "")
        payment_method = str(data.get("payment_method", old.get("payment_method")) or "")
        description = str(data.get("description", old.get("description")) or "").strip()
        if category not in EXPENSE_CATEGORIES or payment_method not in PAYMENT_METHODS or not description:
            raise ValueError("Проверьте обязательные поля")
        cur.execute("""
            UPDATE expenses SET category=%s,description=%s,amount=%s,
                payment_method=%s,comment=%s,date=%s,updated_at=%s
            WHERE id=%s AND company_id=%s
        """, (
            category,
            description[:160],
            _amount(data.get("amount", old.get("amount"))),
            payment_method,
            str(data.get("comment", old.get("comment") or ""))[:500],
            _date(data.get("date"), required=True) if "date" in data else old.get("date"),
            now_kz(),
            expense_id,
            company_id,
        ))
        _sync_expense_to_accounting(cur, expense_id, company_id)
        conn.commit()
        return jsonify({"success": True})
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        conn.rollback()
        print("MOBILE EXPENSE ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось изменить расход"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/accounting", methods=["GET"])
def mobile_accounting():
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        conn.commit()
        today = now_kz().date()
        cur.execute("""
            SELECT * FROM accounting_operations WHERE company_id=%s
            ORDER BY operation_date DESC,id DESC LIMIT 150
        """, (company_id,))
        operations = []
        for row in cur.fetchall():
            item = _clean(_operation_view(row))
            item.update({
                "source_type": row.get("source_type"),
                "source_id": row.get("source_id"),
                "has_document": row.get("source_type") in ("sale", "sale_refund"),
            })
            operations.append(item)
        cur.execute("""
            SELECT * FROM accounting_documents WHERE company_id=%s
            ORDER BY document_date DESC,id DESC LIMIT 150
        """, (company_id,))
        documents = []
        for row in cur.fetchall():
            item = _clean(_document_view(row))
            item.update({
                "source_type": row.get("source_type"),
                "source_id": row.get("source_id"),
                "has_preview": bool(row.get("source_id") or row.get("stored_filename")),
            })
            documents.append(item)
        cur.execute("""
            SELECT * FROM accounting_tax_events WHERE company_id=%s
            ORDER BY CASE WHEN status='paid' THEN 1 ELSE 0 END,due_date,id LIMIT 50
        """, (company_id,))
        taxes = [_clean(_tax_event_view(row, today)) for row in cur.fetchall()]
        cur.execute("""
            SELECT * FROM accounting_debts WHERE company_id=%s
            ORDER BY CASE WHEN status='paid' THEN 1 ELSE 0 END,due_date,id DESC LIMIT 50
        """, (company_id,))
        debts = [_clean(_debt_view(row, today)) for row in cur.fetchall()]
        income = sum(_number(item["amount"]) for item in operations if item["type"] == "income")
        expense = sum(_number(item["amount"]) for item in operations if item["type"] == "expense")
        refunds = sum(_number(item["amount"]) for item in operations if item["type"] == "refund")
        debt_total = sum(_number(item["amount"]) for item in debts if item.get("status") != "paid")
        return jsonify({
            "success": True,
            "summary": {
                "income": income,
                "expense": expense,
                "refunds": refunds,
                "balance": income - expense - refunds,
                "debt_total": debt_total,
                "documents": len(documents),
            },
            "operations": operations,
            "documents": documents,
            "taxes": taxes,
            "debts": debts,
        })
    except Exception as exc:
        conn.rollback()
        print("MOBILE ACCOUNTING ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось загрузить бухгалтерию"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


def _payment_label(sale):
    sale_type = sale.get("sale_type") or "cash"
    if sale_type == "invoice":
        return "Расчётный счёт"
    if _number(sale.get("kaspi_amount")) > 0 or sale_type == "kaspi":
        return "Kaspi POS"
    if _number(sale.get("card_amount")) > 0 or sale_type == "card":
        return "Банковская карта"
    return "Наличные"


def _nested_value(data, *paths):
    for path in paths:
        current = data
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if current not in (None, ""):
            return current
    return ""


def _sale_document(cur, company_id, sale_id, kind):
    cur.execute("""
        SELECT
            s.*,
            COALESCE(c.company_name,c.full_name,'Частное лицо') AS client_name,
            c.iin AS client_iin,
            c.phone AS client_phone,
            c.address AS client_address,
            co.name AS company_name,
            co.bin AS company_bin,
            co.address AS company_address,
            co.phone AS company_phone
        FROM sales s
        LEFT JOIN clients c ON c.id=s.client_id AND c.company_id=s.company_id
        LEFT JOIN companies co ON co.id=s.company_id
        WHERE s.id=%s AND s.company_id=%s
    """, (sale_id, company_id))
    sale = cur.fetchone()
    if not sale:
        return None

    cur.execute("""
        SELECT name,quantity,price,total,unit,gtin,ntin
        FROM sale_items WHERE sale_id=%s ORDER BY id
    """, (sale_id,))
    items = [{
        "name": row.get("name") or "Без названия",
        "quantity": _number(row.get("quantity")),
        "price": _number(row.get("price")),
        "total": _number(row.get("total")),
        "unit": row.get("unit") or "шт",
        "gtin": row.get("gtin") or "",
        "ntin": row.get("ntin") or "",
    } for row in cur.fetchall()]

    titles = {
        "check": "Кассовый чек",
        "refund_check": "Чек возврата",
        "invoice": "Счёт на оплату",
        "waybill": "Накладная",
        "act": "Акт выполненных работ",
        "invoice_facture": "Счёт-фактура",
    }
    pdf_types = {
        "check": "check",
        "refund_check": "refund-check",
        "invoice": "invoice",
        "waybill": "nakladnaya",
        "act": "act",
        "invoice_facture": "schet-factura",
    }
    filename_prefixes = {
        "check": "check",
        "refund_check": "refund-check",
        "invoice": "schet-na-oplatu",
        "waybill": "nakladnaya",
        "act": "akt-vypolnennyh-rabot",
        "invoice_facture": "schet-factura",
    }
    pdf_type = pdf_types.get(kind)
    site_paths = {
        "check": "check",
        "refund_check": "refund-check",
        "invoice": "invoice",
        "waybill": "nakladnaya",
        "act": "act",
        "invoice_facture": "schet-factura",
    }
    site_path = site_paths.get(kind)
    document_date = (
        sale.get("refunded_at")
        if kind == "refund_check" and sale.get("refunded_at")
        else sale.get("created_at")
    )
    fiscal = {
        "ticket_number": sale.get("rekassa_ticket_number") or "",
        "document_number": sale.get("rekassa_document_number") or "",
        "shift_number": sale.get("rekassa_shift_number") or "",
        "rnm": sale.get("rekassa_rnm") or "",
        "znm": sale.get("rekassa_znm") or "",
        "qr": sale.get("rekassa_qr") or "",
        "transaction_id": sale.get("kaspi_transaction_id") or "",
    }
    if kind == "refund_check":
        raw_refund_data = sale.get("refund_receipt_data") or {}
        if isinstance(raw_refund_data, str):
            try:
                raw_refund_data = json.loads(raw_refund_data)
            except (TypeError, ValueError):
                raw_refund_data = {}
        rekassa_data = raw_refund_data.get("rekassa") or {}
        fiscal = {
            "ticket_number": _nested_value(
                rekassa_data,
                ("ticketNumber",),
                ("data", "ticket", "ticketNumber"),
            ),
            "document_number": _nested_value(
                rekassa_data,
                ("printedDocumentNumber",),
                ("data", "ticket", "printedDocumentNumber"),
            ),
            "shift_number": _nested_value(
                rekassa_data,
                ("shiftNumber",),
                ("data", "ticket", "shiftNumber"),
            ),
            "rnm": _nested_value(
                rekassa_data,
                ("rnm",),
                ("data", "service", "regInfo", "kkm", "fnsKkmId"),
            ) or sale.get("rekassa_rnm") or "",
            "znm": _nested_value(
                rekassa_data,
                ("znm",),
                ("data", "service", "regInfo", "kkm", "serialNumber"),
            ) or sale.get("rekassa_znm") or "",
            "qr": _nested_value(
                rekassa_data,
                ("fdoQrCode",),
                ("data", "ticket", "fdoQrCode"),
            ),
            "transaction_id": raw_refund_data.get(
                "payment_refund_transaction_id"
            ) or "",
        }
    return _clean({
        "kind": kind,
        "title": titles.get(kind, "Документ"),
        "source_id": sale_id,
        "file_url": f"/docs/{site_path}/{sale_id}" if site_path else "",
        "pdf_path": (
            f"/api/mobile/accounting/pdf/{pdf_type}/{sale_id}"
            if pdf_type else ""
        ),
        "file_name": f"{filename_prefixes.get(kind, 'document')}-{sale_id}.pdf",
        "number": str(sale.get("sale_number") or sale.get("id")),
        "date": document_date.strftime("%d.%m.%Y %H:%M") if document_date else "—",
        "original_date": (
            sale.get("created_at").strftime("%d.%m.%Y %H:%M")
            if sale.get("created_at") else "—"
        ),
        "is_refunded": bool(sale.get("is_refunded")),
        "status": "Возврат" if kind == "refund_check" else sale.get("status") or "Проведён",
        "payment_method": _payment_label(sale),
        "total": _number(sale.get("total_amount")),
        "company": {
            "name": sale.get("company_name") or "Организация",
            "bin": sale.get("company_bin") or "",
            "address": sale.get("company_address") or "",
            "phone": sale.get("company_phone") or "",
        },
        "client": {
            "name": sale.get("client_name") or "Частное лицо",
            "iin": sale.get("client_iin") or "",
            "address": sale.get("client_address") or "",
            "phone": sale.get("client_phone") or "",
        },
        "items": items,
        "fiscal": fiscal,
    })


def _pdf_target_from_url(value):
    path = str(value or "").split("?", 1)[0].rstrip("/")
    if not path:
        return None

    mappings = {
        "check": "check",
        "refund-check": "refund_check",
        "invoice": "invoice",
        "nakladnaya": "waybill",
        "act": "act",
        "schet-factura": "invoice_facture",
    }
    for route_name, kind in mappings.items():
        marker = f"/docs/{route_name}/"
        if marker not in path:
            continue
        sale_id = path.rsplit(marker, 1)[-1]
        if sale_id.isdigit():
            return kind, int(sale_id)

    segments = path.strip("/").split("/")
    if len(segments) >= 4 and segments[-4:-2] == ["docs", "pdf"]:
        route_name, sale_id = segments[-2], segments[-1]
        kind = mappings.get(route_name)
        if kind and sale_id.isdigit():
            return kind, int(sale_id)
    return None


@mobile_api_bp.route("/accounting/pdf/<document_type>/<int:sale_id>")
def mobile_accounting_pdf(document_type, sale_id):
    """PDF из того же HTML-шаблона, который используется на сайте."""
    denied = _guard()
    if denied:
        return denied

    documents = {
        "check": ("check", "check"),
        "refund-check": ("refund_check", "refund-check"),
        "invoice": ("invoice", "schet-na-oplatu"),
        "nakladnaya": ("nakladnaya", "nakladnaya"),
        "schet-factura": ("schet_factura", "schet-factura"),
        "act": ("act", "akt-vypolnennyh-rabot"),
    }
    document = documents.get(document_type)
    if not document:
        return jsonify({"success": False, "error": "Неизвестный тип документа"}), 404

    try:
        from weasyprint import HTML
        from routes import sales as sales_routes
    except ImportError:
        return jsonify({
            "success": False,
            "error": "На сервере не установлен модуль формирования PDF (WeasyPrint)",
        }), 503

    renderer_name, filename_prefix = document
    try:
        renderer = getattr(sales_routes, renderer_name)
        rendered = make_response(renderer(sale_id))
        if rendered.status_code >= 400:
            return rendered

        pdf = HTML(
            string=rendered.get_data(as_text=True),
            base_url=request.url_root,
            media_type="print",
        ).write_pdf()
        return send_file(
            BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{filename_prefix}-{sale_id}.pdf",
            max_age=0,
        )
    except Exception:
        current_app.logger.exception(
            "Не удалось сформировать мобильный PDF %s для продажи %s",
            document_type,
            sale_id,
        )
        return jsonify({
            "success": False,
            "error": "Не удалось сформировать PDF документа",
        }), 500


@mobile_api_bp.route("/sales/<int:sale_id>/refund-receipt")
def mobile_refund_receipt(sale_id):
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT sale_type,is_refunded
            FROM sales WHERE id=%s AND company_id=%s
        """, (sale_id, company_id))
        sale = cur.fetchone()
        if not sale:
            return jsonify({"success": False, "error": "Продажа не найдена"}), 404
        if sale.get("sale_type") == "invoice":
            return jsonify({
                "success": False,
                "error": "Для продажи по счёту чек возврата не формируется",
            }), 409
        if not sale.get("is_refunded"):
            return jsonify({
                "success": False,
                "error": "Сначала оформите возврат продажи",
            }), 409

        document = _sale_document(cur, company_id, sale_id, "refund_check")
        return jsonify({"success": True, "document": document})
    except Exception as exc:
        conn.rollback()
        print("MOBILE REFUND RECEIPT ERROR:", exc)
        return jsonify({
            "success": False,
            "error": "Не удалось загрузить чек возврата",
        }), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/accounting/operations/<int:operation_id>/documents")
def mobile_accounting_operation_documents(operation_id):
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT * FROM accounting_operations
            WHERE id=%s AND company_id=%s
        """, (operation_id, company_id))
        operation = cur.fetchone()
        if not operation:
            return jsonify({"success": False, "error": "Операция не найдена"}), 404

        source_type = operation.get("source_type")
        source_id = operation.get("source_id")
        url_target = _pdf_target_from_url(operation.get("document_url"))
        if not source_id and url_target:
            source_id = url_target[1]
        if not source_id:
            return jsonify({
                "success": True,
                "documents": [],
                "message": "Для этой операции документ не сформирован",
            })

        if source_type == "sale_refund" or operation.get("operation_type") == "refund":
            kind = "refund_check"
        elif url_target:
            kind = url_target[0]
        else:
            cur.execute(
                "SELECT sale_type FROM sales WHERE id=%s AND company_id=%s",
                (source_id, company_id),
            )
            sale = cur.fetchone()
            kind = "invoice" if sale and sale.get("sale_type") == "invoice" else "check"

        document = _sale_document(cur, company_id, source_id, kind)
        return jsonify({
            "success": True,
            "documents": [document] if document else [],
        })
    except Exception as exc:
        conn.rollback()
        print("MOBILE ACCOUNTING OPERATION DOCUMENT ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось сформировать документ"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/accounting/documents/<int:document_id>/preview")
def mobile_accounting_document_preview(document_id):
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT * FROM accounting_documents
            WHERE id=%s AND company_id=%s
        """, (document_id, company_id))
        row = cur.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Документ не найден"}), 404

        kind_map = {
            "check": "check",
            "invoice": "invoice",
            "waybill": "waybill",
            "act": "act",
            "invoice_facture": "invoice_facture",
        }
        url_target = _pdf_target_from_url(row.get("file_url"))
        kind = kind_map.get(row.get("document_type"))
        source_id = row.get("source_id")
        if not source_id and url_target:
            source_id = url_target[1]
        if not kind and url_target:
            kind = url_target[0]
        if source_id and kind:
            document = _sale_document(cur, company_id, source_id, kind)
        else:
            stored_filename = row.get("stored_filename") or ""
            original_filename = row.get("original_filename") or stored_filename
            stored_is_pdf = original_filename.lower().endswith(".pdf")
            file_url = row.get("file_url") or ""
            url_is_pdf = file_url.split("?", 1)[0].lower().endswith(".pdf")
            document = _clean({
                "kind": "manual",
                "title": row.get("title") or "Документ",
                "number": row.get("document_number") or str(row.get("id")),
                "date": row.get("document_date").strftime("%d.%m.%Y") if row.get("document_date") else "—",
                "status": row.get("status") or "Добавлен",
                "total": _number(row.get("amount")),
                "company": {},
                "client": {"name": row.get("counterparty") or "—"},
                "items": [],
                "comment": row.get("comment") or "",
                "file_url": file_url,
                "pdf_path": (
                    f"/accounting/files/{stored_filename}"
                    if stored_filename and stored_is_pdf
                    else file_url if url_is_pdf else ""
                ),
                "file_name": (
                    original_filename
                    if stored_is_pdf
                    else file_url.rsplit("/", 1)[-1] if url_is_pdf else ""
                ),
            })
        return jsonify({"success": True, "document": document})
    except Exception as exc:
        conn.rollback()
        print("MOBILE ACCOUNTING DOCUMENT PREVIEW ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось открыть документ"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/accounting/sync", methods=["POST"])
def mobile_accounting_sync():
    denied = _guard(admin=True)
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_accounting_tables(cur)
        _sync_accounting(cur, company_id)
        conn.commit()
        return jsonify({"success": True})
    except Exception as exc:
        conn.rollback()
        print("MOBILE ACCOUNTING SYNC ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось обновить бухгалтерию"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/accounting/<kind>/<int:item_id>/paid", methods=["POST"])
def mobile_accounting_paid(kind, item_id):
    denied = _guard(admin=True)
    if denied:
        return denied
    table = {
        "debts": "accounting_debts",
        "taxes": "accounting_tax_events",
    }.get(kind)
    if not table:
        return jsonify({"success": False, "error": "Неизвестный тип"}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE {table} SET status='paid',paid_at=%s,updated_at=%s "
            "WHERE id=%s AND company_id=%s RETURNING id",
            (now_kz(), now_kz(), item_id, session["company_id"]),
        )
        if not cur.fetchone():
            return jsonify({"success": False, "error": "Запись не найдена"}), 404
        conn.commit()
        return jsonify({"success": True})
    finally:
        cur.close()
        pool.putconn(conn)


def _employee_json(row):
    return {
        "id": row["id"],
        "username": row.get("username") or "",
        "full_name": row.get("full_name") or "",
        "phone": row.get("phone") or "",
        "position": row.get("position") or "",
        "role": row.get("role") or "employee",
        "percent_rate": _number(row.get("percent_rate")),
        "is_online": bool(row.get("is_online")),
        "last_seen_at": row.get("last_seen_at").isoformat() if row.get("last_seen_at") else "",
    }


@mobile_api_bp.route("/employees", methods=["GET", "POST"])
def mobile_employees():
    denied = _guard(admin=True)
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            data = _payload()
            username = str(data.get("username") or "").strip()
            password = str(data.get("password") or "").strip()
            full_name = str(data.get("full_name") or "").strip()
            role = str(data.get("role") or "employee")
            if not username or not password or not full_name:
                return jsonify({"success": False, "error": "Заполните ФИО, логин и пароль"}), 400
            if role not in ("admin", "employee"):
                role = "employee"
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cur.fetchone():
                return jsonify({"success": False, "error": "Такой логин уже существует"}), 409
            cur.execute("""
                INSERT INTO users (
                    username,password,role,position,company_id,full_name,
                    phone,percent_rate,is_super_admin,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s) RETURNING id
            """, (
                username,
                password,
                role,
                str(data.get("position") or "").strip(),
                company_id,
                full_name,
                str(data.get("phone") or "").strip(),
                _number(data.get("percent_rate")),
                now_kz(),
            ))
            employee_id = cur.fetchone()["id"]
            conn.commit()
            return jsonify({"success": True, "id": employee_id})

        cur.execute("""
            SELECT u.*,
                CASE WHEN u.last_seen_at IS NOT NULL
                       AND u.last_seen_at >= NOW()-INTERVAL '3 minutes'
                     THEN TRUE ELSE FALSE END AS is_online
            FROM users u WHERE u.company_id=%s ORDER BY u.id DESC
        """, (company_id,))
        return jsonify({
            "success": True,
            "items": [_employee_json(row) for row in cur.fetchall()],
            "can_manage": True,
        })
    except Exception as exc:
        conn.rollback()
        print("MOBILE EMPLOYEES ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось обработать сотрудников"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/employees/<int:employee_id>", methods=["PATCH", "DELETE"])
def mobile_employee(employee_id):
    denied = _guard(admin=True)
    if denied:
        return denied
    if employee_id == session.get("user_id") and request.method == "DELETE":
        return jsonify({"success": False, "error": "Нельзя удалить свою учётную запись"}), 409
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE id=%s AND company_id=%s", (employee_id, company_id))
        old = cur.fetchone()
        if not old:
            return jsonify({"success": False, "error": "Сотрудник не найден"}), 404
        if old.get("role") == "owner" and employee_id != session.get("user_id"):
            return jsonify({"success": False, "error": "Владельца нельзя изменить"}), 403
        if request.method == "DELETE":
            cur.execute("DELETE FROM users WHERE id=%s AND company_id=%s", (employee_id, company_id))
            conn.commit()
            return jsonify({"success": True})
        data = _payload()
        role = str(data.get("role", old.get("role") or "employee"))
        if role not in ("admin", "employee", "owner"):
            role = "employee"
        password = str(data.get("password") or "").strip()
        cur.execute("""
            UPDATE users SET full_name=%s,phone=%s,position=%s,role=%s,
                percent_rate=%s,password=CASE WHEN %s='' THEN password ELSE %s END
            WHERE id=%s AND company_id=%s
        """, (
            str(data.get("full_name", old.get("full_name") or "")).strip(),
            str(data.get("phone", old.get("phone") or "")).strip(),
            str(data.get("position", old.get("position") or "")).strip(),
            role,
            _number(data.get("percent_rate", old.get("percent_rate"))),
            password,
            password,
            employee_id,
            company_id,
        ))
        conn.commit()
        return jsonify({"success": True})
    finally:
        cur.close()
        pool.putconn(conn)


def _order_status_label(value):
    return {
        "new": "Новый", "accepted": "Принят", "assembling": "Собирается",
        "ready": "Готов", "completed": "Выполнен", "cancelled": "Отменён",
    }.get(value, value or "Новый")


def _booking_status_label(value):
    return {
        "new": "Новая", "confirmed": "Подтверждена", "completed": "Выполнена",
        "cancelled": "Отменена", "rejected": "Отклонена",
    }.get(value, value or "Новая")


@mobile_api_bp.route("/storefront", methods=["GET", "PATCH"])
def mobile_storefront():
    denied = _guard(admin=True)
    if denied:
        return denied
    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "PATCH":
            data = _payload()
            slug = str(data.get("slug") or "").strip().lower()
            if not slug:
                return jsonify({"success": False, "error": "Укажите адрес витрины"}), 400
            cur.execute("""
                INSERT INTO storefront_settings (
                    company_id,slug,title,description,enabled,show_products,
                    show_services,allow_orders,allow_booking,delivery_enabled,
                    pickup_enabled,work_start,work_end,slot_interval_minutes,
                    delivery_price,min_order_amount,brand_color,card_style,
                    hero_style,show_stock,show_categories,created_at,updated_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,TRUE,'09:00','18:00',
                    30,0,0,'#6366f1','rounded','gradient',TRUE,TRUE,NOW(),NOW()
                )
                ON CONFLICT(company_id) DO UPDATE SET
                    slug=EXCLUDED.slug,title=EXCLUDED.title,
                    description=EXCLUDED.description,enabled=EXCLUDED.enabled,
                    show_products=EXCLUDED.show_products,
                    show_services=EXCLUDED.show_services,
                    allow_orders=EXCLUDED.allow_orders,
                    allow_booking=EXCLUDED.allow_booking,updated_at=NOW()
            """, (
                company_id,
                slug,
                str(data.get("title") or "").strip() or None,
                str(data.get("description") or "").strip() or None,
                bool(data.get("enabled")),
                bool(data.get("show_products", True)),
                bool(data.get("show_services", True)),
                bool(data.get("allow_orders", True)),
                bool(data.get("allow_booking", True)),
            ))
            conn.commit()
            return jsonify({"success": True})

        cur.execute("SELECT * FROM storefront_settings WHERE company_id=%s", (company_id,))
        settings = cur.fetchone() or {}
        cur.execute("""
            SELECT id,customer_name,phone,total_amount,order_status,created_at,
                (SELECT COUNT(*) FROM online_order_items oi WHERE oi.order_id=o.id) positions_count
            FROM online_orders o WHERE company_id=%s
            ORDER BY CASE WHEN order_status='new' THEN 0 ELSE 1 END,id DESC LIMIT 200
        """, (company_id,))
        orders = [{
            "id": row["id"], "customer_name": row.get("customer_name") or "",
            "phone": row.get("phone") or "", "total_amount": _number(row.get("total_amount")),
            "status": row.get("order_status") or "new",
            "status_label": _order_status_label(row.get("order_status")),
            "created_at": row.get("created_at").strftime("%d.%m.%Y %H:%M") if row.get("created_at") else "",
            "positions_count": int(row.get("positions_count") or 0),
        } for row in cur.fetchall()]
        cur.execute("""
            SELECT b.id,b.customer_name,b.phone,b.booking_date,b.booking_time,
                   b.status,i.name AS service_name
            FROM bookings b LEFT JOIN items i ON i.id=b.item_id
            WHERE b.company_id=%s
            ORDER BY CASE WHEN b.status='new' THEN 0 ELSE 1 END,
                     b.booking_date,b.booking_time LIMIT 200
        """, (company_id,))
        bookings = [{
            "id": row["id"], "customer_name": row.get("customer_name") or "",
            "phone": row.get("phone") or "", "service_name": row.get("service_name") or "Услуга",
            "date": row.get("booking_date").strftime("%d.%m.%Y") if row.get("booking_date") else "",
            "time": row.get("booking_time").strftime("%H:%M") if row.get("booking_time") else "",
            "status": row.get("status") or "new",
            "status_label": _booking_status_label(row.get("status")),
        } for row in cur.fetchall()]
        public_url = f"/s/{settings.get('slug')}" if settings.get("slug") else ""
        return jsonify({
            "success": True,
            "settings": {
                "slug": settings.get("slug") or "",
                "title": settings.get("title") or "",
                "description": settings.get("description") or "",
                "enabled": bool(settings.get("enabled")),
                "show_products": bool(settings.get("show_products", True)),
                "show_services": bool(settings.get("show_services", True)),
                "allow_orders": bool(settings.get("allow_orders", True)),
                "allow_booking": bool(settings.get("allow_booking", True)),
                "public_url": public_url,
            },
            "orders": orders,
            "bookings": bookings,
            "summary": {
                "new_orders": sum(1 for item in orders if item["status"] == "new"),
                "new_bookings": sum(1 for item in bookings if item["status"] == "new"),
                "orders": len(orders),
                "bookings": len(bookings),
            },
        })
    except Exception as exc:
        conn.rollback()
        print("MOBILE STOREFRONT ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось загрузить онлайн-витрину"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/storefront/<kind>/<int:item_id>/status", methods=["POST"])
def mobile_storefront_status(kind, item_id):
    denied = _guard(admin=True)
    if denied:
        return denied
    status = str(_payload().get("status") or "")
    if kind == "orders":
        table, column = "online_orders", "order_status"
        allowed = {"new", "accepted", "assembling", "ready", "completed", "cancelled"}
    elif kind == "bookings":
        table, column = "bookings", "status"
        allowed = {"new", "confirmed", "completed", "cancelled", "rejected"}
    else:
        return jsonify({"success": False, "error": "Неизвестный тип"}), 400
    if status not in allowed:
        return jsonify({"success": False, "error": "Некорректный статус"}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE {table} SET {column}=%s,updated_at=%s "
            "WHERE id=%s AND company_id=%s RETURNING id",
            (status, now_kz(), item_id, session["company_id"]),
        )
        if not cur.fetchone():
            return jsonify({"success": False, "error": "Запись не найдена"}), 404
        conn.commit()
        return jsonify({"success": True})
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/cto")
def mobile_cto():
    denied = _guard()
    if denied:
        return denied
    return jsonify({
        "success": True,
        "items": [
            {"code": "register", "title": "Регистрация ККМ", "icon": "receipt"},
            {"code": "reregister", "title": "Перерегистрация", "icon": "sync"},
            {"code": "deregister", "title": "Снятие с учёта", "icon": "remove"},
            {"code": "ofd", "title": "Подключение ОФД", "icon": "cloud"},
            {"code": "repair", "title": "Ремонт", "icon": "repair"},
            {"code": "visit", "title": "Выезд специалиста", "icon": "car"},
        ],
    })


def _pagination():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = max(10, min(50, int(request.args.get("limit", 30))))
    except (TypeError, ValueError):
        limit = 30
    return page, limit, (page - 1) * limit


@mobile_api_bp.route("/sale/clients")
def mobile_sale_clients():
    """Небольшие страницы клиентов для нативного окна продажи."""
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    query = str(request.args.get("q") or "").strip()
    page, limit, offset = _pagination()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id,full_name,company_name,phone,iin,address
            FROM clients
            WHERE company_id=%s
              AND COALESCE(is_deleted,FALSE)=FALSE
              AND (
                  %s=''
                  OR COALESCE(full_name,'') ILIKE %s
                  OR COALESCE(company_name,'') ILIKE %s
                  OR COALESCE(phone,'') ILIKE %s
                  OR COALESCE(iin,'') ILIKE %s
              )
            ORDER BY
              CASE WHEN LOWER(BTRIM(COALESCE(company_name,full_name,'')))='частное лицо'
                   THEN 0 ELSE 1 END,
              id DESC
            LIMIT %s OFFSET %s
        """, (
            company_id,
            query,
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            limit + 1,
            offset,
        ))
        rows = [dict(row) for row in cur.fetchall()]
        has_more = len(rows) > limit

        cur.execute("""
            SELECT id,full_name,company_name,phone,iin,address
            FROM clients
            WHERE company_id=%s
              AND COALESCE(is_deleted,FALSE)=FALSE
              AND (
                LOWER(BTRIM(COALESCE(company_name,'')))='частное лицо'
                OR LOWER(BTRIM(COALESCE(full_name,'')))='частное лицо'
              )
            ORDER BY id LIMIT 1
        """, (company_id,))
        private_client = cur.fetchone()
        return jsonify({
            "success": True,
            "items": rows[:limit],
            "page": page,
            "has_more": has_more,
            "default_client": dict(private_client) if private_client else None,
        })
    except Exception as exc:
        conn.rollback()
        print("MOBILE SALE CLIENTS ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось загрузить клиентов"}), 500
    finally:
        cur.close()
        pool.putconn(conn)


@mobile_api_bp.route("/sale/items")
def mobile_sale_items():
    """Постраничный каталог товаров и услуг без загрузки всей базы."""
    denied = _guard()
    if denied:
        return denied
    company_id = session["company_id"]
    query = str(request.args.get("q") or "").strip()
    page, limit, offset = _pagination()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT
                i.id,i.name,i.retail_price,i.barcode,i.unit,i.gtin,i.ntin,
                COALESCE(i.item_type,'product') AS item_type,
                CASE
                    WHEN COALESCE(i.item_type,'product')='service' THEN 0
                    ELSE COALESCE((
                        SELECT SUM(
                            CASE
                                WHEN sm.movement_type IN ('income','refund') THEN sm.quantity
                                WHEN sm.movement_type IN ('sale','writeoff') THEN -sm.quantity
                                ELSE 0
                            END
                        )
                        FROM stock_movements sm
                        WHERE sm.company_id=i.company_id
                          AND sm.item_id=i.id
                    ),0)
                END AS quantity
            FROM items i
            WHERE i.company_id=%s
              AND (
                  %s=''
                  OR COALESCE(i.name,'') ILIKE %s
                  OR COALESCE(i.barcode,'') ILIKE %s
              )
            ORDER BY
                CASE WHEN %s<>'' AND i.barcode=%s THEN 0 ELSE 1 END,
                i.id DESC
            LIMIT %s OFFSET %s
        """, (
            company_id,
            query,
            f"%{query}%",
            f"{query}%",
            query,
            query,
            limit + 1,
            offset,
        ))
        rows = [dict(row) for row in cur.fetchall()]
        has_more = len(rows) > limit
        return jsonify({
            "success": True,
            "items": _clean(rows[:limit]),
            "page": page,
            "has_more": has_more,
        })
    except Exception as exc:
        conn.rollback()
        print("MOBILE SALE ITEMS ERROR:", exc)
        return jsonify({"success": False, "error": "Не удалось загрузить каталог"}), 500
    finally:
        cur.close()
        pool.putconn(conn)
