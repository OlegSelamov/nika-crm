"""Migrate existing Nika Business media from local disk to Cloudflare R2.

Run only after configuring MEDIA_BACKEND=r2 and all R2_* environment variables:
    python scripts/migrate_media_to_r2.py

The script is idempotent: already-cloud URLs are skipped.
"""

from pathlib import Path

from models import get_db, pool
from services.media import upload_local_path


def _is_local(value):
    return bool(value) and not str(value).startswith(("http://", "https://"))


def _path(value):
    return Path(str(value).lstrip("/"))


def main():
    conn = get_db()
    cur = conn.cursor()
    moved = 0
    skipped = 0
    try:
        cur.execute("""
            SELECT ii.id, ii.image, i.company_id, ii.item_id
            FROM item_images ii
            JOIN items i ON i.id=ii.item_id
            ORDER BY ii.id
        """)
        for row in cur.fetchall():
            if not _is_local(row["image"]):
                skipped += 1
                continue
            source = _path(row["image"])
            if not source.exists():
                skipped += 1
                continue
            url = upload_local_path(
                source,
                company_id=row["company_id"],
                namespace=f"items/{row['item_id']}",
            )
            cur.execute("UPDATE item_images SET image=%s WHERE id=%s", (url, row["id"]))
            moved += 1

        cur.execute("""
            SELECT company_id, logo_url, cover_url
            FROM storefront_settings
        """)
        for row in cur.fetchall():
            for column, namespace in (("logo_url", "storefront/branding"), ("cover_url", "storefront/branding")):
                value = row.get(column)
                if not _is_local(value):
                    continue
                source = _path(value)
                if not source.exists():
                    continue
                url = upload_local_path(
                    source,
                    company_id=row["company_id"],
                    namespace=namespace,
                    name=column.replace("_url", ""),
                )
                cur.execute(
                    f"UPDATE storefront_settings SET {column}=%s WHERE company_id=%s",
                    (url, row["company_id"]),
                )
                moved += 1

        cur.execute("SELECT id, company_id, image_url FROM storefront_banners")
        for row in cur.fetchall():
            if not _is_local(row["image_url"]):
                continue
            source = _path(row["image_url"])
            if not source.exists():
                continue
            url = upload_local_path(
                source,
                company_id=row["company_id"],
                namespace="storefront/banners",
            )
            cur.execute(
                "UPDATE storefront_banners SET image_url=%s WHERE id=%s",
                (url, row["id"]),
            )
            moved += 1

        conn.commit()
        print(f"Media migration complete. moved={moved}, skipped={skipped}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)


if __name__ == "__main__":
    main()
