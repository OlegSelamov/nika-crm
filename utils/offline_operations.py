import json
from datetime import datetime, timezone


def ensure_offline_operations(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS offline_operations (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            operation_id TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            entity_id BIGINT,
            result_json TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            UNIQUE (company_id, operation_id)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_offline_operations_company_created
        ON offline_operations(company_id, created_at DESC)
    """)


def load_offline_operation(cur, company_id, operation_id):
    operation_id = str(operation_id or "").strip()
    if not company_id or not operation_id:
        return None

    ensure_offline_operations(cur)
    cur.execute("""
        SELECT company_id, operation_id, operation_type, entity_id,
               result_json, created_at, updated_at
        FROM offline_operations
        WHERE company_id = %s AND operation_id = %s
        LIMIT 1
    """, (company_id, operation_id))
    row = cur.fetchone()
    if not row:
        return None

    result = dict(row)
    raw = result.pop("result_json", None)
    if raw:
        try:
            result["result"] = json.loads(raw)
        except (TypeError, ValueError):
            result["result"] = None
    else:
        result["result"] = None
    return result


def save_offline_operation(
    cur,
    *,
    company_id,
    operation_id,
    operation_type,
    entity_id=None,
    result=None,
):
    operation_id = str(operation_id or "").strip()
    if not company_id or not operation_id:
        return

    ensure_offline_operations(cur)
    result_json = (
        json.dumps(result, ensure_ascii=False, default=str)
        if result is not None
        else None
    )
    cur.execute("""
        INSERT INTO offline_operations (
            company_id, operation_id, operation_type, entity_id,
            result_json, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (company_id, operation_id)
        DO UPDATE SET
            entity_id = COALESCE(EXCLUDED.entity_id, offline_operations.entity_id),
            result_json = COALESCE(EXCLUDED.result_json, offline_operations.result_json),
            updated_at = NOW()
    """, (
        company_id,
        operation_id,
        operation_type,
        entity_id,
        result_json,
    ))


def offline_operation_age_seconds(operation):
    created_at = (operation or {}).get("created_at")
    if not created_at:
        return 10**9
    try:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        now = datetime.now(created_at.tzinfo)
        return max((now - created_at).total_seconds(), 0)
    except Exception:
        return 10**9
