from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, session

from models import get_db, pool
from utils.timezone import now_kz


tasks_bp = Blueprint("tasks", __name__)

TASK_STATUSES = {
    "new": "Новая",
    "in_progress": "В работе",
    "done": "Выполнена",
    "cancelled": "Отменена",
}

TASK_PRIORITIES = {
    "low": "Низкий",
    "medium": "Средний",
    "high": "Высокий",
    "urgent": "Срочный",
}


def _safe_date_sql(column_name):
    """
    Возвращает SQL-выражение, которое безопасно преобразует DATE или TEXT
    формата YYYY-MM-DD в DATE. Пустые и некорректные значения дают NULL.
    """
    return f"""
        CASE
            WHEN {column_name} IS NULL THEN NULL
            WHEN BTRIM({column_name}::text) = '' THEN NULL
            WHEN {column_name}::text ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}$'
                THEN ({column_name}::text)::date
            ELSE NULL
        END
    """


def _safe_timestamp_sql(column_name):
    """
    Безопасно преобразует TIMESTAMP или текстовую дату/время в TIMESTAMP.
    """
    return f"""
        CASE
            WHEN {column_name} IS NULL THEN NULL
            WHEN BTRIM({column_name}::text) = '' THEN NULL
            WHEN {column_name}::text ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
                THEN ({column_name}::text)::timestamp
            ELSE NULL
        END
    """


def _company_id():
    return session.get("company_id")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Некорректная дата")


def _ensure_tasks_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            company_id INTEGER,
            created_by INTEGER,
            assigned_user_id INTEGER,
            title TEXT,
            description TEXT,
            priority VARCHAR(20) DEFAULT 'medium',
            status VARCHAR(20) DEFAULT 'new',
            due_date DATE,
            completed_at TIMESTAMP,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)

    # Миграция для старой таблицы tasks, если она уже существовала.
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS company_id INTEGER")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by INTEGER")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assigned_user_id INTEGER")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS title TEXT")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS description TEXT")
    cur.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'medium'"
    )
    cur.execute(
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'new'"
    )
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS due_date DATE")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_at TIMESTAMP")
    cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP")

    # Заполняем обязательные значения в старых строках.
    cur.execute("""
        UPDATE tasks
        SET priority = 'medium'
        WHERE priority IS NULL
    """)
    cur.execute("""
        UPDATE tasks
        SET status = 'new'
        WHERE status IS NULL
    """)
    cur.execute("""
        UPDATE tasks
        SET created_at = %s
        WHERE created_at IS NULL
    """, (now_kz(),))

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tasks_company_status
        ON tasks(company_id, status, due_date, id DESC)
    """)


def _task_view(row, today):
    status = row["status"] or "new"
    due_date = row.get("due_date_parsed") if hasattr(row, "get") else row["due_date_parsed"]
    created_at = row.get("created_at_parsed") if hasattr(row, "get") else row["created_at_parsed"]

    overdue = (
        due_date is not None
        and due_date < today
        and status not in ("done", "cancelled")
    )

    return {
        "id": row["id"],
        "title": row["title"] or "",
        "description": row["description"] or "",
        "priority": row["priority"] or "medium",
        "priority_label": TASK_PRIORITIES.get(row["priority"], "Средний"),
        "status": status,
        "status_label": TASK_STATUSES.get(status, "Новая"),
        "due_date": due_date.isoformat() if due_date else "",
        "due_date_label": due_date.strftime("%d.%m.%Y") if due_date else "Без срока",
        "assignee_id": row["assigned_user_id"],
        "assignee_name": row["assignee_name"] or "Не назначен",
        "created_at": created_at.strftime("%d.%m.%Y %H:%M") if created_at else "—",
        "overdue": overdue,
    }


@tasks_bp.route("/tasks")
def tasks():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _company_id()
    if not company_id:
        return "Активная компания не выбрана", 400

    status_filter = request.args.get("status", "all")
    priority_filter = request.args.get("priority", "all")
    search = request.args.get("search", "").strip()

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tasks_table(cur)
        conn.commit()

        conditions = ["t.company_id = %s"]
        params = [company_id]

        if status_filter in TASK_STATUSES:
            conditions.append("t.status = %s")
            params.append(status_filter)

        if priority_filter in TASK_PRIORITIES:
            conditions.append("t.priority = %s")
            params.append(priority_filter)

        if search:
            conditions.append("""
                (
                    LOWER(t.title) LIKE %s
                    OR LOWER(COALESCE(t.description, '')) LIKE %s
                    OR LOWER(COALESCE(u.full_name, '')) LIKE %s
                )
            """)
            term = f"%{search.lower()}%"
            params.extend([term, term, term])

        due_date_sql = _safe_date_sql("t.due_date")
        created_at_sql = _safe_timestamp_sql("t.created_at")

        cur.execute(f"""
            SELECT
                t.*,
                {due_date_sql} AS due_date_parsed,
                {created_at_sql} AS created_at_parsed,
                COALESCE(u.full_name, u.username) AS assignee_name
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_user_id
            WHERE {' AND '.join(conditions)}
            ORDER BY
                CASE t.status
                    WHEN 'in_progress' THEN 1
                    WHEN 'new' THEN 2
                    WHEN 'done' THEN 3
                    ELSE 4
                END,
                CASE t.priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    ELSE 4
                END,
                {due_date_sql} NULLS LAST,
                t.id DESC
        """, params)

        today = now_kz().date()
        task_list = [_task_view(row, today) for row in cur.fetchall()]

        due_date_summary_sql = _safe_date_sql("due_date")

        cur.execute(f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'new') AS new_count,
                COUNT(*) FILTER (WHERE status = 'in_progress') AS progress_count,
                COUNT(*) FILTER (WHERE status = 'done') AS done_count,
                COUNT(*) FILTER (
                    WHERE {due_date_summary_sql} < %s
                      AND status NOT IN ('done', 'cancelled')
                ) AS overdue_count
            FROM tasks
            WHERE company_id = %s
        """, (today, company_id))
        summary = cur.fetchone()

        cur.execute("""
            SELECT id, COALESCE(full_name, username) AS name
            FROM users
            WHERE company_id = %s
            ORDER BY name
        """, (company_id,))
        users = cur.fetchall()

        return render_template(
            "tasks.html",
            tasks=task_list,
            users=users,
            summary=summary,
            status_filter=status_filter,
            priority_filter=priority_filter,
            search=search,
            task_statuses=TASK_STATUSES,
            task_priorities=TASK_PRIORITIES,
        )

    except Exception as exc:
        conn.rollback()
        print("TASKS PAGE ERROR:", exc)
        return "Не удалось загрузить задачи", 500

    finally:
        cur.close()
        pool.putconn(conn)


@tasks_bp.route("/tasks/add", methods=["POST"])
def add_task():
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _company_id()
    if not company_id:
        return "Активная компания не выбрана", 400

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    priority = request.form.get("priority", "medium")
    assigned_user_id = request.form.get("assigned_user_id") or None

    if not title:
        return "Укажите название задачи", 400

    if priority not in TASK_PRIORITIES:
        priority = "medium"

    try:
        due_date = _parse_date(request.form.get("due_date"))
    except ValueError as exc:
        return str(exc), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tasks_table(cur)

        cur.execute("""
            INSERT INTO tasks (
                company_id,
                created_by,
                assigned_user_id,
                title,
                description,
                priority,
                status,
                due_date,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'new', %s, %s)
        """, (
            company_id,
            session.get("user_id"),
            assigned_user_id,
            title,
            description or None,
            priority,
            due_date.isoformat() if due_date else None,
            now_kz(),
        ))

        conn.commit()
        return redirect("/tasks")

    except Exception as exc:
        conn.rollback()
        print("TASK ADD ERROR:", exc)
        return "Не удалось создать задачу", 500

    finally:
        cur.close()
        pool.putconn(conn)


@tasks_bp.route("/tasks/<int:task_id>/edit", methods=["POST"])
def edit_task(task_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _company_id()
    if not company_id:
        return "Активная компания не выбрана", 400

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    priority = request.form.get("priority", "medium")
    status = request.form.get("status", "new")
    assigned_user_id = request.form.get("assigned_user_id") or None

    if not title:
        return "Укажите название задачи", 400

    if priority not in TASK_PRIORITIES:
        priority = "medium"

    if status not in TASK_STATUSES:
        status = "new"

    try:
        due_date = _parse_date(request.form.get("due_date"))
    except ValueError as exc:
        return str(exc), 400

    completed_at = now_kz() if status == "done" else None

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tasks_table(cur)

        cur.execute("""
            UPDATE tasks
            SET
                title = %s,
                description = %s,
                priority = %s,
                status = %s,
                assigned_user_id = %s,
                due_date = %s,
                completed_at = %s,
                updated_at = %s
            WHERE id = %s
              AND company_id = %s
            RETURNING id
        """, (
            title,
            description or None,
            priority,
            status,
            assigned_user_id,
            due_date.isoformat() if due_date else None,
            completed_at,
            now_kz(),
            task_id,
            company_id,
        ))

        if not cur.fetchone():
            conn.rollback()
            return "Задача не найдена", 404

        conn.commit()
        return redirect("/tasks")

    except Exception as exc:
        conn.rollback()
        print("TASK EDIT ERROR:", exc)
        return "Не удалось изменить задачу", 500

    finally:
        cur.close()
        pool.putconn(conn)


@tasks_bp.route("/tasks/<int:task_id>/status", methods=["POST"])
def change_task_status(task_id):
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Требуется авторизация"}), 401

    company_id = _company_id()
    status = request.form.get("status", "")

    if status not in TASK_STATUSES:
        return jsonify({"success": False, "error": "Некорректный статус"}), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tasks_table(cur)

        cur.execute("""
            UPDATE tasks
            SET
                status = %s,
                completed_at = %s,
                updated_at = %s
            WHERE id = %s
              AND company_id = %s
            RETURNING id
        """, (
            status,
            now_kz() if status == "done" else None,
            now_kz(),
            task_id,
            company_id,
        ))

        if not cur.fetchone():
            conn.rollback()
            return jsonify({"success": False, "error": "Задача не найдена"}), 404

        conn.commit()
        return jsonify({"success": True})

    finally:
        cur.close()
        pool.putconn(conn)


@tasks_bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    if not session.get("user_id"):
        return redirect("/login")

    company_id = _company_id()

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tasks_table(cur)

        cur.execute("""
            DELETE FROM tasks
            WHERE id = %s
              AND company_id = %s
        """, (task_id, company_id))

        conn.commit()
        return redirect("/tasks")

    finally:
        cur.close()
        pool.putconn(conn)