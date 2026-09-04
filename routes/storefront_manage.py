import os
import re
from pathlib import Path
from flask import Blueprint, render_template, request, redirect, session, flash, url_for, current_app, jsonify
from werkzeug.utils import secure_filename
from models import get_db, pool
from utils.timezone import now_kz

storefront_manage_bp = Blueprint("storefront_manage", __name__, url_prefix="/storefront")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def _guard():
    if not session.get("user_id") or not session.get("company_id"):
        return redirect("/login")

    modules = session.get("employee_modules", []) or []
    allowed = (
        session.get("is_super_admin")
        or session.get("role") in ("owner", "admin")
        or "storefront" in modules
    )

    if not allowed:
        return ("Доступ запрещён", 403)

    return None


def _valid_slug(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9а-яё_-]+", "-", value, flags=re.I)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def _valid_color(value):
    value = (value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value
    return "#6366f1"


def _save_storefront_image(file_storage, company_id, kind):
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        return None

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Разрешены только PNG, JPG, JPEG и WEBP.")

    folder = Path(current_app.root_path) / "static" / "uploads" / "storefront" / str(company_id)
    folder.mkdir(parents=True, exist_ok=True)

    final_name = f"{kind}.{ext}"
    target = folder / final_name
    file_storage.save(target)

    return f"/static/uploads/storefront/{company_id}/{final_name}"



def _banner_json(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "image_url": row["image_url"],
        "title": row.get("title") or "",
        "subtitle": row.get("subtitle") or "",
        "button_text": row.get("button_text") or "",
        "button_url": row.get("button_url") or "",
        "sort_order": row.get("sort_order") or 0,
        "is_active": bool(row.get("is_active")),
    }


def _save_banner_image(file_storage, company_id):
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        raise ValueError("У баннера не найдено расширение файла.")

    ext = filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Баннер: разрешены только PNG, JPG, JPEG и WEBP.")

    folder = Path(current_app.root_path) / "static" / "uploads" / "storefront" / str(company_id) / "banners"
    folder.mkdir(parents=True, exist_ok=True)

    stamp = now_kz().strftime("%Y%m%d%H%M%S%f")
    final_name = f"banner_{stamp}.{ext}"
    target = folder / final_name
    file_storage.save(target)

    return f"/static/uploads/storefront/{company_id}/banners/{final_name}"


@storefront_manage_bp.route("/", methods=["GET", "POST"])
def settings():
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()

    try:
        if request.method == "POST":
            slug = _valid_slug(request.form.get("slug"))
            if not slug:
                flash("Укажите адрес витрины.", "error")
                return redirect("/storefront/")

            cur.execute("SELECT * FROM storefront_settings WHERE company_id=%s", (company_id,))
            old = cur.fetchone()

            logo_url = old.get("logo_url") if old else None
            cover_url = old.get("cover_url") if old else None

            try:
                new_logo = _save_storefront_image(request.files.get("logo"), company_id, "logo")
                if new_logo:
                    logo_url = new_logo
            except ValueError as e:
                flash(str(e), "error")
                return redirect("/storefront/")

            if request.form.get("remove_logo") == "1":
                logo_url = None

            payload = {
                "title": (request.form.get("title") or "").strip(),
                "description": (request.form.get("description") or "").strip(),
                "whatsapp": (request.form.get("whatsapp") or "").strip(),
                "instagram": (request.form.get("instagram") or "").strip(),
                "enabled": request.form.get("enabled") == "1",
                "show_products": request.form.get("show_products") == "1",
                "show_services": request.form.get("show_services") == "1",
                "allow_orders": request.form.get("allow_orders") == "1",
                "allow_booking": request.form.get("allow_booking") == "1",
                "delivery_enabled": request.form.get("delivery_enabled") == "1",
                "pickup_enabled": request.form.get("pickup_enabled") == "1",
                "show_stock": request.form.get("show_stock") == "1",
                "show_categories": request.form.get("show_categories") == "1",
                "work_start": request.form.get("work_start") or "09:00",
                "work_end": request.form.get("work_end") or "18:00",
                "slot_interval": request.form.get("slot_interval_minutes") or 30,
                "delivery_price": request.form.get("delivery_price") or 0,
                "min_order": request.form.get("min_order_amount") or 0,
                "brand_color": _valid_color(request.form.get("brand_color")),
                "card_style": request.form.get("card_style") if request.form.get("card_style") in {"rounded", "compact", "minimal"} else "rounded",
                "hero_style": request.form.get("hero_style") if request.form.get("hero_style") in {"gradient", "cover", "clean"} else "gradient",
            }

            try:
                cur.execute("""
                    INSERT INTO storefront_settings (
                        company_id, slug, title, description, logo_url, cover_url,
                        whatsapp, instagram, enabled, show_products, show_services,
                        allow_orders, allow_booking, delivery_enabled, pickup_enabled,
                        work_start, work_end, slot_interval_minutes, delivery_price,
                        min_order_amount, brand_color, card_style, hero_style,
                        show_stock, show_categories, created_at, updated_at
                    )
                    VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW()
                    )
                    ON CONFLICT (company_id)
                    DO UPDATE SET
                        slug=EXCLUDED.slug,
                        title=EXCLUDED.title,
                        description=EXCLUDED.description,
                        logo_url=EXCLUDED.logo_url,
                        cover_url=EXCLUDED.cover_url,
                        whatsapp=EXCLUDED.whatsapp,
                        instagram=EXCLUDED.instagram,
                        enabled=EXCLUDED.enabled,
                        show_products=EXCLUDED.show_products,
                        show_services=EXCLUDED.show_services,
                        allow_orders=EXCLUDED.allow_orders,
                        allow_booking=EXCLUDED.allow_booking,
                        delivery_enabled=EXCLUDED.delivery_enabled,
                        pickup_enabled=EXCLUDED.pickup_enabled,
                        work_start=EXCLUDED.work_start,
                        work_end=EXCLUDED.work_end,
                        slot_interval_minutes=EXCLUDED.slot_interval_minutes,
                        delivery_price=EXCLUDED.delivery_price,
                        min_order_amount=EXCLUDED.min_order_amount,
                        brand_color=EXCLUDED.brand_color,
                        card_style=EXCLUDED.card_style,
                        hero_style=EXCLUDED.hero_style,
                        show_stock=EXCLUDED.show_stock,
                        show_categories=EXCLUDED.show_categories,
                        updated_at=NOW()
                """, (
                    company_id, slug, payload["title"] or None, payload["description"] or None,
                    logo_url, cover_url, payload["whatsapp"] or None, payload["instagram"] or None,
                    payload["enabled"], payload["show_products"], payload["show_services"],
                    payload["allow_orders"], payload["allow_booking"], payload["delivery_enabled"],
                    payload["pickup_enabled"], payload["work_start"], payload["work_end"],
                    payload["slot_interval"], payload["delivery_price"], payload["min_order"],
                    payload["brand_color"], payload["card_style"], payload["hero_style"],
                    payload["show_stock"], payload["show_categories"]
                ))
                conn.commit()
            except Exception as e:
                conn.rollback()
                if "storefront_settings_slug_key" in str(e):
                    flash("Такой адрес витрины уже занят.", "error")
                    return redirect("/storefront/")
                raise

            flash("Настройки витрины сохранены.", "success")
            return redirect("/storefront/")

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
            FROM items
            WHERE company_id=%s
        """, (company_id,))
        stats = cur.fetchone()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE order_status='new') AS new_orders,
                COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS today_orders,
                COALESCE(SUM(total_amount) FILTER (WHERE created_at::date=CURRENT_DATE),0) AS today_amount,
                COUNT(*) AS total_orders
            FROM online_orders
            WHERE company_id=%s
        """, (company_id,))
        order_stats = cur.fetchone()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status='new') AS new_bookings,
                COUNT(*) FILTER (WHERE booking_date=CURRENT_DATE) AS today_bookings,
                COUNT(*) AS total_bookings
            FROM bookings
            WHERE company_id=%s
        """, (company_id,))
        booking_stats = cur.fetchone()

        cur.execute("""
            SELECT id, customer_name, phone, total_amount, order_status, created_at
            FROM online_orders
            WHERE company_id=%s
            ORDER BY id DESC
            LIMIT 5
        """, (company_id,))
        recent_orders = cur.fetchall()

        cur.execute("""
            SELECT b.id, b.customer_name, b.phone, b.booking_date, b.booking_time,
                   b.status, i.name AS service_name
            FROM bookings b
            LEFT JOIN items i ON i.id=b.item_id
            WHERE b.company_id=%s
            ORDER BY b.id DESC
            LIMIT 5
        """, (company_id,))
        recent_bookings = cur.fetchall()

        cur.execute("""
            SELECT *
            FROM storefront_banners
            WHERE company_id=%s
            ORDER BY sort_order, id
        """, (company_id,))
        banners = cur.fetchall()

        return render_template(
            "storefront_manage/settings.html",
            settings=settings,
            stats=stats,
            order_stats=order_stats,
            booking_stats=booking_stats,
            recent_orders=recent_orders,
            recent_bookings=recent_bookings,
            banners=banners,
        )
    finally:
        cur.close()
        pool.putconn(conn)




@storefront_manage_bp.route("/save-ajax", methods=["POST"])
def save_ajax():
    denied = _guard()
    if denied:
        return jsonify({"ok": False, "error": "Доступ запрещён"}), 403

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM storefront_settings WHERE company_id=%s", (company_id,))
        old = cur.fetchone()

        slug = _valid_slug(request.form.get("slug"))
        if not slug:
            return jsonify({"ok": False, "error": "Укажите адрес витрины."}), 400

        logo_url = old.get("logo_url") if old else None

        try:
            new_logo = _save_storefront_image(request.files.get("logo"), company_id, "logo")
            if new_logo:
                logo_url = new_logo
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400

        if request.form.get("remove_logo") == "1":
            logo_url = None

        brand_color = _valid_color(request.form.get("brand_color"))
        card_style = request.form.get("card_style")
        if card_style not in {"rounded", "compact", "minimal"}:
            card_style = "rounded"

        try:
            cur.execute("""
                INSERT INTO storefront_settings (
                    company_id, slug, title, description, logo_url,
                    whatsapp, instagram, enabled, show_products, show_services,
                    allow_orders, allow_booking, delivery_enabled, pickup_enabled,
                    work_start, work_end, slot_interval_minutes, delivery_price,
                    min_order_amount, brand_color, card_style,
                    show_stock, show_categories, created_at, updated_at
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW()
                )
                ON CONFLICT (company_id)
                DO UPDATE SET
                    slug=EXCLUDED.slug,
                    title=EXCLUDED.title,
                    description=EXCLUDED.description,
                    logo_url=EXCLUDED.logo_url,
                    whatsapp=EXCLUDED.whatsapp,
                    instagram=EXCLUDED.instagram,
                    enabled=EXCLUDED.enabled,
                    show_products=EXCLUDED.show_products,
                    show_services=EXCLUDED.show_services,
                    allow_orders=EXCLUDED.allow_orders,
                    allow_booking=EXCLUDED.allow_booking,
                    delivery_enabled=EXCLUDED.delivery_enabled,
                    pickup_enabled=EXCLUDED.pickup_enabled,
                    work_start=EXCLUDED.work_start,
                    work_end=EXCLUDED.work_end,
                    slot_interval_minutes=EXCLUDED.slot_interval_minutes,
                    delivery_price=EXCLUDED.delivery_price,
                    min_order_amount=EXCLUDED.min_order_amount,
                    brand_color=EXCLUDED.brand_color,
                    card_style=EXCLUDED.card_style,
                    show_stock=EXCLUDED.show_stock,
                    show_categories=EXCLUDED.show_categories,
                    updated_at=NOW()
                RETURNING *
            """, (
                company_id,
                slug,
                (request.form.get("title") or "").strip() or None,
                (request.form.get("description") or "").strip() or None,
                logo_url,
                (request.form.get("whatsapp") or "").strip() or None,
                (request.form.get("instagram") or "").strip() or None,
                request.form.get("enabled") == "1",
                request.form.get("show_products") == "1",
                request.form.get("show_services") == "1",
                request.form.get("allow_orders") == "1",
                request.form.get("allow_booking") == "1",
                request.form.get("delivery_enabled") == "1",
                request.form.get("pickup_enabled") == "1",
                request.form.get("work_start") or "09:00",
                request.form.get("work_end") or "18:00",
                request.form.get("slot_interval_minutes") or 30,
                request.form.get("delivery_price") or 0,
                request.form.get("min_order_amount") or 0,
                brand_color,
                card_style,
                request.form.get("show_stock") == "1",
                request.form.get("show_categories") == "1",
            ))
            saved = cur.fetchone()
            conn.commit()
        except Exception as e:
            conn.rollback()
            if "storefront_settings_slug_key" in str(e):
                return jsonify({"ok": False, "error": "Такой адрес витрины уже занят."}), 409
            raise

        return jsonify({
            "ok": True,
            "message": "Настройки сохранены",
            "settings": {
                "slug": saved["slug"],
                "logo_url": saved.get("logo_url"),
                "brand_color": saved.get("brand_color"),
                "card_style": saved.get("card_style"),
                "enabled": bool(saved.get("enabled")),
            }
        })
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/banners/add", methods=["POST"])
def banner_add():
    denied = _guard()
    if denied:
        return jsonify({"ok": False, "error": "Доступ запрещён"}), 403

    company_id = session["company_id"]
    image = request.files.get("banner_image")
    title = (request.form.get("banner_title") or "").strip()
    subtitle = (request.form.get("banner_subtitle") or "").strip()
    button_text = (request.form.get("banner_button_text") or "").strip()
    button_url = (request.form.get("banner_button_url") or "").strip()

    try:
        image_url = _save_banner_image(image, company_id)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    if not image_url:
        return jsonify({"ok": False, "error": "Выберите изображение баннера."}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM storefront_settings WHERE company_id=%s", (company_id,))
        store = cur.fetchone()

        cur.execute("""
            SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order
            FROM storefront_banners
            WHERE company_id=%s
        """, (company_id,))
        sort_order = cur.fetchone()["next_order"]

        cur.execute("""
            INSERT INTO storefront_banners (
                company_id, storefront_id, image_url, title, subtitle,
                button_text, button_url, sort_order, is_active, created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s)
            RETURNING *
        """, (
            company_id, store["id"] if store else None, image_url,
            title or None, subtitle or None, button_text or None,
            button_url or None, sort_order, now_kz(), now_kz()
        ))
        row = cur.fetchone()
        conn.commit()
        return jsonify({"ok": True, "banner": _banner_json(row)})
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/banners/<int:banner_id>/update", methods=["POST"])
def banner_update(banner_id):
    denied = _guard()
    if denied:
        return jsonify({"ok": False, "error": "Доступ запрещён"}), 403

    company_id = session["company_id"]
    try:
        sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE storefront_banners
            SET title=%s, subtitle=%s, button_text=%s, button_url=%s,
                sort_order=%s, is_active=%s, updated_at=%s
            WHERE id=%s AND company_id=%s
            RETURNING *
        """, (
            (request.form.get("title") or "").strip() or None,
            (request.form.get("subtitle") or "").strip() or None,
            (request.form.get("button_text") or "").strip() or None,
            (request.form.get("button_url") or "").strip() or None,
            sort_order,
            request.form.get("is_active") == "1",
            now_kz(),
            banner_id,
            company_id
        ))
        row = cur.fetchone()
        conn.commit()

        if not row:
            return jsonify({"ok": False, "error": "Баннер не найден."}), 404
        return jsonify({"ok": True, "banner": _banner_json(row)})
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/banners/<int:banner_id>/delete", methods=["POST"])
def banner_delete(banner_id):
    denied = _guard()
    if denied:
        return jsonify({"ok": False, "error": "Доступ запрещён"}), 403

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM storefront_banners
            WHERE id=%s AND company_id=%s
            RETURNING image_url
        """, (banner_id, company_id))
        row = cur.fetchone()
        conn.commit()

        if not row:
            return jsonify({"ok": False, "error": "Баннер не найден."}), 404

        if row.get("image_url"):
            relative = row["image_url"].lstrip("/")
            path = Path(current_app.root_path) / relative
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

        return jsonify({"ok": True, "id": banner_id})
    finally:
        cur.close()
        pool.putconn(conn)



def _decimal_number(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _order_status_label(value):
    return {
        "new": "Новый",
        "accepted": "Принят",
        "assembling": "Собирается",
        "ready": "Готов",
        "completed": "Выполнен",
        "cancelled": "Отменён",
    }.get(value, value or "Новый")


def _booking_status_label(value):
    return {
        "new": "Новая",
        "confirmed": "Подтверждена",
        "completed": "Выполнена",
        "cancelled": "Отменена",
        "rejected": "Отклонена",
    }.get(value, value or "Новая")


@storefront_manage_bp.route("/orders/<int:order_id>/data")
def order_data(order_id):
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT o.*
            FROM online_orders o
            WHERE o.id=%s AND o.company_id=%s
            LIMIT 1
        """, (order_id, company_id))
        order = cur.fetchone()

        if not order:
            return jsonify({"ok": False, "error": "Заказ не найден"}), 404

        cur.execute("""
            SELECT
                oi.id,
                oi.item_id,
                oi.name,
                oi.quantity,
                oi.price,
                oi.total,
                i.unit,
                (
                    SELECT ii.image
                    FROM item_images ii
                    WHERE ii.item_id=oi.item_id
                    ORDER BY ii.id
                    LIMIT 1
                ) AS image
            FROM online_order_items oi
            LEFT JOIN items i
              ON i.id=oi.item_id
             AND i.company_id=%s
            WHERE oi.order_id=%s
            ORDER BY oi.id
        """, (company_id, order_id))
        items = cur.fetchall()

        subtotal = sum(_decimal_number(x.get("total")) for x in items)
        delivery_price = max(
            0,
            _decimal_number(order.get("total_amount")) - subtotal
        )

        created_at = order.get("created_at")
        accepted_at = order.get("accepted_at")
        completed_at = order.get("completed_at")

        return jsonify({
            "ok": True,
            "order": {
                "id": order["id"],
                "customer_name": order.get("customer_name") or "",
                "phone": order.get("phone") or "",
                "customer_type": order.get("customer_type") or "private",
                "customer_iin_bin": order.get("customer_iin_bin") or "",
                "customer_company": order.get("customer_company") or "",
                "customer_email": order.get("customer_email") or "",
                "customer_legal_address": order.get("customer_legal_address") or "",
                "address": order.get("address") or "",
                "delivery_method": order.get("delivery_method") or "pickup",
                "comment": order.get("comment") or "",
                "payment_status": order.get("payment_status") or "unpaid",
                "order_status": order.get("order_status") or "new",
                "order_status_label": _order_status_label(order.get("order_status")),
                "total_amount": _decimal_number(order.get("total_amount")),
                "subtotal": subtotal,
                "delivery_price": delivery_price,
                "created_at": created_at.strftime("%d.%m.%Y %H:%M") if created_at else "",
                "accepted_at": accepted_at.strftime("%d.%m.%Y %H:%M") if accepted_at else "",
                "completed_at": completed_at.strftime("%d.%m.%Y %H:%M") if completed_at else "",
            },
            "items": [
                {
                    "id": x["id"],
                    "item_id": x.get("item_id"),
                    "name": x.get("name") or "",
                    "quantity": _decimal_number(x.get("quantity")),
                    "price": _decimal_number(x.get("price")),
                    "total": _decimal_number(x.get("total")),
                    "unit": x.get("unit") or "шт.",
                    "image": x.get("image"),
                }
                for x in items
            ]
        })
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/orders/<int:order_id>/status-ajax", methods=["POST"])
def order_status_ajax(order_id):
    denied = _guard()
    if denied:
        return denied

    status = (request.form.get("status") or "").strip()
    allowed = {"new", "accepted", "assembling", "ready", "completed", "cancelled"}

    if status not in allowed:
        return jsonify({"ok": False, "error": "Некорректный статус"}), 400

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE online_orders
            SET
                order_status=%s,
                accepted_at=CASE
                    WHEN %s='accepted' AND accepted_at IS NULL THEN %s
                    ELSE accepted_at
                END,
                completed_at=CASE
                    WHEN %s='completed' THEN %s
                    ELSE completed_at
                END,
                updated_at=%s
            WHERE id=%s AND company_id=%s
            RETURNING id, order_status
        """, (
            status,
            status, now_kz(),
            status, now_kz(),
            now_kz(),
            order_id, company_id
        ))
        row = cur.fetchone()

        if not row:
            conn.rollback()
            return jsonify({"ok": False, "error": "Заказ не найден"}), 404

        conn.commit()

        return jsonify({
            "ok": True,
            "id": row["id"],
            "status": row["order_status"],
            "status_label": _order_status_label(row["order_status"]),
        })
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/bookings/<int:booking_id>/data")
def booking_data(booking_id):
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                b.*,
                i.name AS service_name,
                i.description AS service_description,
                COALESCE(i.retail_price, i.price, 0) AS service_price,
                i.category AS service_category,
                i.booking_duration_minutes AS item_duration,
                (
                    SELECT ii.image
                    FROM item_images ii
                    WHERE ii.item_id=b.item_id
                    ORDER BY ii.id
                    LIMIT 1
                ) AS service_image
            FROM bookings b
            LEFT JOIN items i
              ON i.id=b.item_id
             AND i.company_id=b.company_id
            WHERE b.id=%s AND b.company_id=%s
            LIMIT 1
        """, (booking_id, company_id))
        booking = cur.fetchone()

        if not booking:
            return jsonify({"ok": False, "error": "Запись не найдена"}), 404

        booking_date = booking.get("booking_date")
        booking_time = booking.get("booking_time")
        created_at = booking.get("created_at")

        return jsonify({
            "ok": True,
            "booking": {
                "id": booking["id"],
                "item_id": booking.get("item_id"),
                "service_name": booking.get("service_name") or "Услуга",
                "service_description": booking.get("service_description") or "",
                "service_category": booking.get("service_category") or "",
                "service_price": _decimal_number(booking.get("service_price")),
                "service_image": booking.get("service_image"),
                "customer_name": booking.get("customer_name") or "",
                "phone": booking.get("phone") or "",
                "comment": booking.get("comment") or "",
                "booking_date": booking_date.strftime("%d.%m.%Y") if booking_date else "",
                "booking_time": booking_time.strftime("%H:%M") if booking_time else "",
                "duration_minutes": int(
                    booking.get("duration_minutes")
                    or booking.get("item_duration")
                    or 60
                ),
                "status": booking.get("status") or "new",
                "status_label": _booking_status_label(booking.get("status")),
                "payment_status": booking.get("payment_status") or "unpaid",
                "created_at": created_at.strftime("%d.%m.%Y %H:%M") if created_at else "",
            }
        })
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/bookings/<int:booking_id>/status-ajax", methods=["POST"])
def booking_status_ajax(booking_id):
    denied = _guard()
    if denied:
        return denied

    status = (request.form.get("status") or "").strip()
    allowed = {"new", "confirmed", "completed", "cancelled", "rejected"}

    if status not in allowed:
        return jsonify({"ok": False, "error": "Некорректный статус"}), 400

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE bookings
            SET status=%s, updated_at=%s
            WHERE id=%s AND company_id=%s
            RETURNING id, status
        """, (status, now_kz(), booking_id, company_id))
        row = cur.fetchone()

        if not row:
            conn.rollback()
            return jsonify({"ok": False, "error": "Запись не найдена"}), 404

        conn.commit()

        return jsonify({
            "ok": True,
            "id": row["id"],
            "status": row["status"],
            "status_label": _booking_status_label(row["status"]),
        })
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/orders")
def orders():
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    status = (request.args.get("status") or "").strip()
    q = (request.args.get("q") or "").strip()

    conn = get_db()
    cur = conn.cursor()
    try:
        where = ["o.company_id=%s"]
        params = [company_id]

        if status:
            where.append("o.order_status=%s")
            params.append(status)

        if q:
            val = f"%{q}%"
            where.append("(COALESCE(o.customer_name,'') ILIKE %s OR COALESCE(o.phone,'') ILIKE %s OR CAST(o.id AS TEXT) ILIKE %s)")
            params.extend([val, val, val])

        cur.execute(f"""
            SELECT o.*,
                   (SELECT COUNT(*) FROM online_order_items oi WHERE oi.order_id=o.id) AS positions_count
            FROM online_orders o
            WHERE {' AND '.join(where)}
            ORDER BY CASE WHEN o.order_status='new' THEN 0 ELSE 1 END, o.id DESC
            LIMIT 500
        """, params)
        rows = cur.fetchall()
        return render_template("storefront_manage/orders.html", orders=rows, status=status, q=q)
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/orders/<int:order_id>", methods=["GET", "POST"])
def order_detail(order_id):
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    conn = get_db()
    cur = conn.cursor()

    try:
        if request.method == "POST":
            new_status = (request.form.get("status") or "").strip()
            allowed = {"new", "accepted", "assembling", "ready", "completed", "cancelled"}

            if new_status in allowed:
                cur.execute("""
                    UPDATE online_orders
                    SET order_status=%s,
                        accepted_at=CASE WHEN %s='accepted' AND accepted_at IS NULL THEN %s ELSE accepted_at END,
                        completed_at=CASE WHEN %s='completed' THEN %s ELSE completed_at END,
                        updated_at=%s
                    WHERE id=%s AND company_id=%s
                """, (
                    new_status, new_status, now_kz(),
                    new_status, now_kz(), now_kz(),
                    order_id, company_id
                ))
                conn.commit()

            return redirect(url_for("storefront_manage.order_detail", order_id=order_id))

        cur.execute("""
            SELECT *
            FROM online_orders
            WHERE id=%s AND company_id=%s
        """, (order_id, company_id))
        order = cur.fetchone()

        if not order:
            return "Заказ не найден", 404

        cur.execute("""
            SELECT *
            FROM online_order_items
            WHERE order_id=%s
            ORDER BY id
        """, (order_id,))
        items = cur.fetchall()

        return render_template("storefront_manage/order_detail.html", order=order, items=items)
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/bookings")
def bookings():
    denied = _guard()
    if denied:
        return denied

    company_id = session["company_id"]
    q = (request.args.get("q") or "").strip()

    conn = get_db()
    cur = conn.cursor()
    try:
        params = [company_id]
        where = ["b.company_id=%s"]

        if q:
            value = f"%{q}%"
            where.append("(COALESCE(b.customer_name,'') ILIKE %s OR COALESCE(b.phone,'') ILIKE %s OR COALESCE(i.name,'') ILIKE %s)")
            params.extend([value, value, value])

        cur.execute(f"""
            SELECT b.*, i.name AS service_name
            FROM bookings b
            LEFT JOIN items i ON i.id=b.item_id
            WHERE {' AND '.join(where)}
            ORDER BY CASE WHEN b.status='new' THEN 0 ELSE 1 END,
                     b.booking_date, b.booking_time
            LIMIT 500
        """, params)

        return render_template("storefront_manage/bookings.html", bookings=cur.fetchall(), q=q)
    finally:
        cur.close()
        pool.putconn(conn)


@storefront_manage_bp.route("/bookings/<int:booking_id>/status", methods=["POST"])
def booking_status(booking_id):
    denied = _guard()
    if denied:
        return denied

    status = (request.form.get("status") or "").strip()
    if status not in {"new", "confirmed", "completed", "cancelled", "rejected"}:
        return "Некорректный статус", 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE bookings
            SET status=%s, updated_at=%s
            WHERE id=%s AND company_id=%s
        """, (status, now_kz(), booking_id, session["company_id"]))
        conn.commit()
        return redirect("/storefront/bookings")
    finally:
        cur.close()
        pool.putconn(conn)
