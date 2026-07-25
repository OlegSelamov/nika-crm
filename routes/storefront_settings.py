from flask import Blueprint, render_template, request, redirect, session, flash
from models import get_db, pool

storefront_settings_bp = Blueprint("storefront_settings", __name__)


@storefront_settings_bp.route("/storefront", methods=["GET", "POST"])
def storefront_settings():
    if not session.get("user_id") or not session.get("company_id"):
        return redirect("/login")

    company_id = session["company_id"]
    if session.get("role") not in ("owner", "admin") and not session.get("is_super_admin"):
        return "Доступ запрещён", 403

    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            slug = (request.form.get("slug") or "").strip().lower()
            title = (request.form.get("title") or "").strip()
            description = (request.form.get("description") or "").strip()
            whatsapp = (request.form.get("whatsapp") or "").strip()
            instagram = (request.form.get("instagram") or "").strip()
            enabled = request.form.get("enabled") == "1"
            show_products = request.form.get("show_products") == "1"
            show_services = request.form.get("show_services") == "1"
            allow_orders = request.form.get("allow_orders") == "1"
            allow_booking = request.form.get("allow_booking") == "1"

            if not slug:
                flash("Укажите адрес витрины.", "error")
                return redirect("/storefront")

            cur.execute("""
                INSERT INTO storefront_settings (
                    company_id,slug,title,description,whatsapp,instagram,
                    enabled,show_products,show_services,allow_orders,allow_booking,
                    created_at,updated_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
                ON CONFLICT (company_id)
                DO UPDATE SET
                    slug=EXCLUDED.slug,
                    title=EXCLUDED.title,
                    description=EXCLUDED.description,
                    whatsapp=EXCLUDED.whatsapp,
                    instagram=EXCLUDED.instagram,
                    enabled=EXCLUDED.enabled,
                    show_products=EXCLUDED.show_products,
                    show_services=EXCLUDED.show_services,
                    allow_orders=EXCLUDED.allow_orders,
                    allow_booking=EXCLUDED.allow_booking,
                    updated_at=NOW()
            """, (
                company_id,slug,title or None,description or None,
                whatsapp or None,instagram or None,enabled,
                show_products,show_services,allow_orders,allow_booking
            ))
            conn.commit()
            flash("Витрина сохранена.", "success")
            return redirect("/storefront")

        cur.execute("""
            SELECT ss.*, c.name AS company_name
            FROM companies c
            LEFT JOIN storefront_settings ss ON ss.company_id=c.id
            WHERE c.id=%s
        """, (company_id,))
        settings = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE item_type='service') AS services,
                   COUNT(*) FILTER (WHERE COALESCE(item_type,'product')<>'service') AS products
            FROM items WHERE company_id=%s
        """, (company_id,))
        catalog_stats = cur.fetchone()

        return render_template(
            "storefront/settings.html",
            settings=settings,
            catalog_stats=catalog_stats
        )
    finally:
        cur.close()
        pool.putconn(conn)
