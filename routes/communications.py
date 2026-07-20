from datetime import timedelta

from flask import Blueprint, jsonify, request, session

from models import get_db, pool
from utils.timezone import now_kz


communications_bp = Blueprint("communications", __name__)


def _require_login():
    return bool(session.get("user_id"))


def _row_value(row, key, index):
    if hasattr(row, "keys"):
        return row[key]
    return row[index]


def _ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            notification_type VARCHAR(40) DEFAULT 'system',
            title TEXT NOT NULL,
            message TEXT,
            related_id INTEGER,
            link TEXT,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            sender_user_id INTEGER NOT NULL,
            recipient_user_id INTEGER,
            message TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_read_state (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            conversation_type VARCHAR(20) NOT NULL,
            peer_user_id INTEGER,
            last_read_message_id INTEGER DEFAULT 0,
            updated_at TIMESTAMP NOT NULL
        )
    """)

    cur.execute(
        "ALTER TABLE chat_messages "
        "ADD COLUMN IF NOT EXISTS recipient_user_id INTEGER"
    )

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
        ON notifications(user_id, is_read, id DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_company_recipient
        ON chat_messages(company_id, recipient_user_id, id DESC)
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_read_general_unique
        ON chat_read_state(company_id, user_id, conversation_type)
        WHERE peer_user_id IS NULL
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_read_private_unique
        ON chat_read_state(company_id, user_id, conversation_type, peer_user_id)
        WHERE peer_user_id IS NOT NULL
    """)

    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP")


def _mark_conversation_read(cur, company_id, user_id, conversation_type, peer_user_id, last_id):
    if conversation_type == "general":
        cur.execute("""
            UPDATE chat_read_state
            SET last_read_message_id = GREATEST(last_read_message_id, %s),
                updated_at = %s
            WHERE company_id = %s
              AND user_id = %s
              AND conversation_type = 'general'
              AND peer_user_id IS NULL
        """, (last_id, now_kz(), company_id, user_id))

        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO chat_read_state (
                    company_id, user_id, conversation_type,
                    peer_user_id, last_read_message_id, updated_at
                )
                VALUES (%s, %s, 'general', NULL, %s, %s)
            """, (company_id, user_id, last_id, now_kz()))
    else:
        cur.execute("""
            UPDATE chat_read_state
            SET last_read_message_id = GREATEST(last_read_message_id, %s),
                updated_at = %s
            WHERE company_id = %s
              AND user_id = %s
              AND conversation_type = 'private'
              AND peer_user_id = %s
        """, (last_id, now_kz(), company_id, user_id, peer_user_id))

        if cur.rowcount == 0:
            cur.execute("""
                INSERT INTO chat_read_state (
                    company_id, user_id, conversation_type,
                    peer_user_id, last_read_message_id, updated_at
                )
                VALUES (%s, %s, 'private', %s, %s, %s)
            """, (company_id, user_id, peer_user_id, last_id, now_kz()))


@communications_bp.route("/api/notifications")
def notifications():
    if not _require_login():
        return jsonify({"error": "Требуется авторизация"}), 401

    limit = min(max(request.args.get("limit", 30, type=int), 1), 100)
    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tables(cur)
        conn.commit()

        cur.execute("""
            SELECT id, notification_type, title, message,
                   related_id, link, is_read, created_at
            FROM notifications
            WHERE company_id = %s
              AND user_id = %s
            ORDER BY id DESC
            LIMIT %s
        """, (session.get("company_id"), session.get("user_id"), limit))
        rows = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM notifications
            WHERE company_id = %s
              AND user_id = %s
              AND is_read = FALSE
        """, (session.get("company_id"), session.get("user_id")))
        unread_row = cur.fetchone()
        unread_count = _row_value(unread_row, "count", 0)

        items = []
        for row in rows:
            created_at = _row_value(row, "created_at", 7)
            items.append({
                "id": _row_value(row, "id", 0),
                "type": _row_value(row, "notification_type", 1) or "system",
                "title": _row_value(row, "title", 2) or "Уведомление",
                "message": _row_value(row, "message", 3) or "",
                "related_id": _row_value(row, "related_id", 4),
                "link": _row_value(row, "link", 5) or "",
                "is_read": bool(_row_value(row, "is_read", 6)),
                "created_at_label": created_at.strftime("%d.%m.%Y %H:%M")
                if created_at else "—",
            })

        return jsonify({"items": items, "unread_count": unread_count})
    finally:
        cur.close()
        pool.putconn(conn)


@communications_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
def read_notification(notification_id):
    if not _require_login():
        return jsonify({"success": False}), 401

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)
        cur.execute("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE id = %s
              AND company_id = %s
              AND user_id = %s
        """, (notification_id, session.get("company_id"), session.get("user_id")))
        conn.commit()
        return jsonify({"success": True})
    finally:
        cur.close()
        pool.putconn(conn)


@communications_bp.route("/api/notifications/read-all", methods=["POST"])
def read_all_notifications():
    if not _require_login():
        return jsonify({"success": False}), 401

    conn = get_db()
    cur = conn.cursor()
    try:
        _ensure_tables(cur)
        cur.execute("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE company_id = %s
              AND user_id = %s
              AND is_read = FALSE
        """, (session.get("company_id"), session.get("user_id")))
        conn.commit()
        return jsonify({"success": True})
    finally:
        cur.close()
        pool.putconn(conn)


@communications_bp.route("/api/chat/conversations")
def chat_conversations():
    if not _require_login():
        return jsonify({"error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    user_id = session.get("user_id")
    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tables(cur)
        conn.commit()

        threshold = (now_kz() - timedelta(minutes=3)).replace(tzinfo=None)

        cur.execute("""
            SELECT
                u.id,
                COALESCE(u.full_name, u.username, 'Сотрудник') AS name,
                u.last_seen_at,
                (
                    SELECT COUNT(*)
                    FROM chat_messages cm
                    WHERE cm.company_id = %s
                      AND cm.recipient_user_id = %s
                      AND cm.sender_user_id = u.id
                      AND cm.id > COALESCE((
                          SELECT crs.last_read_message_id
                          FROM chat_read_state crs
                          WHERE crs.company_id = %s
                            AND crs.user_id = %s
                            AND crs.conversation_type = 'private'
                            AND crs.peer_user_id = u.id
                          LIMIT 1
                      ), 0)
                ) AS unread_count
            FROM users u
            WHERE u.company_id = %s
              AND u.id <> %s
            ORDER BY
                CASE WHEN u.last_seen_at >= %s THEN 0 ELSE 1 END,
                COALESCE(u.full_name, u.username)
        """, (
            company_id, user_id,
            company_id, user_id,
            company_id, user_id, threshold,
        ))

        users = []
        private_unread = 0

        for row in cur.fetchall():
            unread_count = int(_row_value(row, "unread_count", 3) or 0)
            private_unread += unread_count
            last_seen = _row_value(row, "last_seen_at", 2)
            users.append({
                "id": _row_value(row, "id", 0),
                "name": _row_value(row, "name", 1),
                "is_online": bool(last_seen and last_seen >= threshold),
                "unread_count": unread_count,
            })

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM chat_messages cm
            WHERE cm.company_id = %s
              AND cm.recipient_user_id IS NULL
              AND cm.sender_user_id <> %s
              AND cm.id > COALESCE((
                  SELECT crs.last_read_message_id
                  FROM chat_read_state crs
                  WHERE crs.company_id = %s
                    AND crs.user_id = %s
                    AND crs.conversation_type = 'general'
                    AND crs.peer_user_id IS NULL
                  LIMIT 1
              ), 0)
        """, (company_id, user_id, company_id, user_id))

        general_row = cur.fetchone()
        general_unread = int(_row_value(general_row, "count", 0) or 0)

        return jsonify({
            "users": users,
            "general_unread": general_unread,
            "total_unread": general_unread + private_unread,
        })
    finally:
        cur.close()
        pool.putconn(conn)


@communications_bp.route("/api/chat/messages", methods=["GET"])
def get_chat_messages():
    if not _require_login():
        return jsonify({"error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    user_id = session.get("user_id")
    conversation_type = request.args.get("type", "general")
    peer_user_id = request.args.get("user_id", type=int)
    limit = min(max(request.args.get("limit", 100, type=int), 1), 200)

    if conversation_type not in ("general", "private"):
        return jsonify({"error": "Некорректный тип чата"}), 400

    if conversation_type == "private" and not peer_user_id:
        return jsonify({"error": "Не выбран сотрудник"}), 400

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tables(cur)
        conn.commit()

        if conversation_type == "general":
            cur.execute("""
                SELECT *
                FROM (
                    SELECT
                        cm.id,
                        cm.sender_user_id,
                        cm.message,
                        cm.created_at,
                        COALESCE(u.full_name, u.username, 'Сотрудник') AS sender_name
                    FROM chat_messages cm
                    LEFT JOIN users u ON u.id = cm.sender_user_id
                    WHERE cm.company_id = %s
                      AND cm.recipient_user_id IS NULL
                    ORDER BY cm.id DESC
                    LIMIT %s
                ) q
                ORDER BY q.id
            """, (company_id, limit))
        else:
            cur.execute("""
                SELECT *
                FROM (
                    SELECT
                        cm.id,
                        cm.sender_user_id,
                        cm.message,
                        cm.created_at,
                        COALESCE(u.full_name, u.username, 'Сотрудник') AS sender_name
                    FROM chat_messages cm
                    LEFT JOIN users u ON u.id = cm.sender_user_id
                    WHERE cm.company_id = %s
                      AND (
                            (cm.sender_user_id = %s AND cm.recipient_user_id = %s)
                         OR (cm.sender_user_id = %s AND cm.recipient_user_id = %s)
                      )
                    ORDER BY cm.id DESC
                    LIMIT %s
                ) q
                ORDER BY q.id
            """, (
                company_id,
                user_id, peer_user_id,
                peer_user_id, user_id,
                limit,
            ))

        rows = cur.fetchall()
        items = []
        last_id = 0

        for row in rows:
            sender_id = _row_value(row, "sender_user_id", 1)
            created_at = _row_value(row, "created_at", 3)
            message_id = _row_value(row, "id", 0)
            last_id = max(last_id, message_id)

            items.append({
                "id": message_id,
                "sender_user_id": sender_id,
                "sender_name": _row_value(row, "sender_name", 4),
                "message": _row_value(row, "message", 2),
                "created_at_label": created_at.strftime("%d.%m.%Y %H:%M")
                if created_at else "—",
                "is_mine": sender_id == user_id,
            })

        if last_id:
            _mark_conversation_read(
                cur,
                company_id,
                user_id,
                conversation_type,
                peer_user_id,
                last_id,
            )
            conn.commit()

        return jsonify({"items": items})
    finally:
        cur.close()
        pool.putconn(conn)


@communications_bp.route("/api/chat/messages", methods=["POST"])
def send_chat_message():
    if not _require_login():
        return jsonify({"success": False, "error": "Требуется авторизация"}), 401

    company_id = session.get("company_id")
    user_id = session.get("user_id")
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    conversation_type = payload.get("type", "general")
    recipient_user_id = payload.get("recipient_user_id")

    if not message:
        return jsonify({"success": False, "error": "Введите сообщение"}), 400

    if len(message) > 2000:
        return jsonify({"success": False, "error": "Сообщение слишком длинное"}), 400

    if conversation_type not in ("general", "private"):
        return jsonify({"success": False, "error": "Некорректный тип чата"}), 400

    if conversation_type == "private":
        try:
            recipient_user_id = int(recipient_user_id)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Выберите сотрудника"}), 400

        if recipient_user_id == user_id:
            return jsonify({"success": False, "error": "Нельзя написать самому себе"}), 400

    else:
        recipient_user_id = None

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tables(cur)

        if recipient_user_id is not None:
            cur.execute("""
                SELECT id
                FROM users
                WHERE id = %s
                  AND company_id = %s
            """, (recipient_user_id, company_id))

            if not cur.fetchone():
                conn.rollback()
                return jsonify({
                    "success": False,
                    "error": "Сотрудник не найден",
                }), 404

        cur.execute("""
            INSERT INTO chat_messages (
                company_id,
                sender_user_id,
                recipient_user_id,
                message,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            company_id,
            user_id,
            recipient_user_id,
            message,
            now_kz(),
        ))

        row = cur.fetchone()
        message_id = _row_value(row, "id", 0)

        _mark_conversation_read(
            cur,
            company_id,
            user_id,
            conversation_type,
            recipient_user_id,
            message_id,
        )

        conn.commit()
        return jsonify({"success": True, "id": message_id})
    finally:
        cur.close()
        pool.putconn(conn)


@communications_bp.route("/api/presence/ping", methods=["POST"])
def presence_ping():
    if not _require_login():
        return jsonify({"success": False}), 401

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tables(cur)
        current = now_kz()

        cur.execute("""
            UPDATE users
            SET last_seen_at = %s
            WHERE id = %s
              AND company_id = %s
        """, (current, session.get("user_id"), session.get("company_id")))

        threshold = (current - timedelta(minutes=3)).replace(tzinfo=None)

        cur.execute("""
            SELECT COUNT(*) AS count
            FROM users
            WHERE company_id = %s
              AND last_seen_at IS NOT NULL
              AND last_seen_at >= %s
        """, (session.get("company_id"), threshold))

        row = cur.fetchone()
        count = _row_value(row, "count", 0)
        conn.commit()

        return jsonify({"success": True, "online_count": count})
    finally:
        cur.close()
        pool.putconn(conn)


@communications_bp.route("/api/presence/users")
def presence_users():
    if not _require_login():
        return jsonify({"error": "Требуется авторизация"}), 401

    conn = get_db()
    cur = conn.cursor()

    try:
        _ensure_tables(cur)
        conn.commit()

        current = now_kz()
        threshold = (current - timedelta(minutes=3)).replace(tzinfo=None)

        cur.execute("""
            SELECT
                id,
                COALESCE(full_name, username, 'Сотрудник') AS name,
                last_seen_at
            FROM users
            WHERE company_id = %s
            ORDER BY
                CASE WHEN last_seen_at >= %s THEN 0 ELSE 1 END,
                COALESCE(full_name, username)
        """, (session.get("company_id"), threshold))

        items = []

        for row in cur.fetchall():
            last_seen = _row_value(row, "last_seen_at", 2)
            items.append({
                "id": _row_value(row, "id", 0),
                "name": _row_value(row, "name", 1),
                "is_online": bool(last_seen and last_seen >= threshold),
                "last_seen_label": last_seen.strftime("%d.%m.%Y %H:%M")
                if last_seen else "Не входил",
            })

        return jsonify({"items": items})
    finally:
        cur.close()
        pool.putconn(conn)