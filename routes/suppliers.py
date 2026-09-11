from datetime import datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, session

from models import get_db, pool
from routes.expenses import upsert_expense_from_source, _sync_expense_to_accounting
from routes.stock import is_product


suppliers_bp = Blueprint("suppliers", __name__)
_subscription_catalog_ready = False


def ensure_supplier_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            bin_iin TEXT,
            contact_name TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            comment TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_company ON suppliers(company_id)")
    cur.execute("ALTER TABLE stock_movements ADD COLUMN IF NOT EXISTS supplier_id INTEGER")
    conn.commit()
    cur.close()


def _ensure_subscription_catalog_once():
    global _subscription_catalog_ready
    if _subscription_catalog_ready:
        return
    conn = get_db()
    try:
        cur = conn.cursor()
        from routes.modular_registration import ensure_supplier_subscription_module
        ensure_supplier_subscription_module(cur)
        conn.commit()
        _subscription_catalog_ready = True
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def _supplier_module_enabled(company_id):
    """New subscriptions use a separate suppliers module; old companies keep legacy warehouse access until first resave."""
    if not company_id or session.get("is_super_admin"):
        return True
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT cm.enabled, cm.status
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = %s AND m.code = 'suppliers'
            LIMIT 1
        """, (company_id,))
        supplier_row = cur.fetchone()
        if supplier_row:
            return bool(supplier_row["enabled"] and supplier_row["status"] in ("trial", "active"))

        # Backward compatibility for companies created before Suppliers became
        # its own paid module.
        cur.execute("""
            SELECT 1
            FROM company_modules cm
            JOIN modules m ON m.id = cm.module_id
            WHERE cm.company_id = %s
              AND m.code = 'warehouse'
              AND cm.enabled = TRUE
              AND cm.status IN ('trial', 'active')
            LIMIT 1
        """, (company_id,))
        return bool(cur.fetchone())
    finally:
        cur.close()
        pool.putconn(conn)


@suppliers_bp.before_app_request
def modular_registration_bootstrap():
    """Make modular registration the public flow without changing old route URLs."""
    _ensure_subscription_catalog_once()

    if request.path == "/register":
        from routes.modular_registration import register_modular
        return register_modular()
    if request.path == "/onboarding":
        from routes.modular_registration import onboarding_modular
        return onboarding_modular()
    if request.path == "/onboarding/save":
        from routes.modular_registration import onboarding_save_modular
        return onboarding_save_modular()
    if request.path == "/onboarding/finish":
        from routes.modular_registration import onboarding_finish_modular
        return onboarding_finish_modular()
    return None


@suppliers_bp.before_request
def guard_suppliers_module():
    company_id = session.get("company_id")
    if not company_id:
        return None
    if _supplier_module_enabled(company_id):
        return None
    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "Модуль «Поставщики» не подключён",
            "module": "suppliers",
        }), 403
    return redirect("/subscription?required=suppliers")


@suppliers_bp.after_app_request
def inject_trial_subscription_ui(response):
    """Switch subscription form to trial-safe save flow without duplicating the large template."""
    if request.path != "/subscription":
        return response
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type.lower():
        return response
    try:
        html = response.get_data(as_text=True)
        html = html.replace(
            'action="/subscription/update"',
            'action="/subscription/selection"',
        )
        html = html.replace(
            'action="{{ url_for(\'subscriptions.subscription_update\') }}"',
            'action="/subscription/selection"',
        )
        if "trial-subscription-flow-20260911" not in html and "</body>" in html:
            script = r'''
<script id="trial-subscription-flow-20260911">
(function(){
  const statusEl=document.getElementById('subStatus');
  const form=document.getElementById('subscriptionForm');
  const saveBtn=form?.querySelector('.save-btn');
  const total=document.getElementById('grandTotal');
  const summaryLabel=form?.querySelector('.summary-total-label');
  const note=form?.querySelector('.summary-note');
  if(!form || !saveBtn || !statusEl) return;

  form.action='/subscription/selection';
  const status=statusEl.dataset.status || '';

  if(new URLSearchParams(location.search).get('saved')==='1'){
    const banner=document.createElement('div');
    banner.className='trial-note';
    banner.style.background='#ecfdf5';
    banner.style.borderColor='#a7f3d0';
    banner.style.color='#047857';
    banner.innerHTML='<b>Набор модулей сохранён.</b> Можно продолжать тестирование до конца пробного периода. Оплата сейчас не требуется.';
    const hero=document.querySelector('.sub-hero');
    hero?.insertAdjacentElement('afterend',banner);
  }

  function updateAction(){
    const amount=(total?.textContent || '').replace(/\s+/g,' ').trim();
    if(status==='trial'){
      if(summaryLabel) summaryLabel.textContent='После пробного периода';
      saveBtn.textContent='Сохранить набор модулей';
      if(note) note.textContent='Во время пробного периода оплата не требуется. Можно менять модули до его окончания; дата окончания trial не продлевается.';
    }else if(status==='expired' || status==='pending_payment' || status==='suspended' || status==='cancelled'){
      if(summaryLabel) summaryLabel.textContent='К оплате';
      saveBtn.textContent='Оплатить '+amount+' и продолжить работу';
      if(note) note.textContent='После успешной оплаты будут активированы только выбранные модули.';
    }
  }

  updateAction();
  if(total){
    new MutationObserver(updateAction).observe(total,{childList:true,subtree:true,characterData:true});
  }
})();
</script>
'''
            html = html.replace("</body>", script + "\n</body>", 1)
        response.set_data(html)
    except Exception as exc:
        print("SUBSCRIPTION TRIAL UI INJECT ERROR:", exc)
    return response


def _supplier_for_company(cur, supplier_id, company_id):
    if not supplier_id:
        return None
    cur.execute("""
        SELECT *
        FROM suppliers
        WHERE id = %s AND company_id = %s AND is_active = TRUE
    """, (supplier_id, company_id))
    return cur.fetchone()


def _delete_supplier_record(cur, company_id, supplier_id):
    cur.execute("""
        SELECT COUNT(*) AS linked_count
        FROM stock_movements
        WHERE company_id = %s AND supplier_id = %s
    """, (company_id, supplier_id))
    linked_count = int(cur.fetchone()["linked_count"] or 0)

    if linked_count == 0:
        cur.execute(
            "DELETE FROM suppliers WHERE id = %s AND company_id = %s",
            (supplier_id, company_id),
        )
        action = "deleted"
    else:
        cur.execute("""
            UPDATE suppliers
            SET is_active = FALSE, updated_at = NOW()
            WHERE id = %s AND company_id = %s
        """, (supplier_id, company_id))
        action = "archived"

    return action, linked_count


@suppliers_bp.route("/suppliers")
def suppliers_page():
    company_id = session.get("company_id")
    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                s.*,
                COUNT(sm.id) FILTER (WHERE sm.movement_type = 'income') AS income_count,
                COALESCE(SUM(sm.total) FILTER (WHERE sm.movement_type = 'income'), 0) AS income_total,
                MAX(sm.created_at) FILTER (WHERE sm.movement_type = 'income') AS last_income_at
            FROM suppliers s
            LEFT JOIN stock_movements sm
              ON sm.supplier_id = s.id
             AND sm.company_id = s.company_id
            WHERE s.company_id = %s
              AND s.is_active = TRUE
            GROUP BY s.id
            ORDER BY LOWER(s.name), s.id
        """, (company_id,))
        suppliers = cur.fetchall()
        return render_template("suppliers.html", suppliers=suppliers)
    finally:
        pool.putconn(conn)


@suppliers_bp.route("/api/suppliers", methods=["GET", "POST"])
def api_suppliers():
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()

        if request.method == "GET":
            cur.execute("""
                SELECT id, name, bin_iin, contact_name, phone, email, address, comment
                FROM suppliers
                WHERE company_id = %s AND is_active = TRUE
                ORDER BY LOWER(name), id
            """, (company_id,))
            return jsonify(cur.fetchall())

        data = request.get_json(silent=True) or request.form
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": "Укажите название поставщика"}), 400

        cur.execute("""
            INSERT INTO suppliers (
                company_id, name, bin_iin, contact_name, phone,
                email, address, comment, created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
            RETURNING id
        """, (
            company_id,
            name,
            str(data.get("bin_iin") or "").strip() or None,
            str(data.get("contact_name") or "").strip() or None,
            str(data.get("phone") or "").strip() or None,
            str(data.get("email") or "").strip() or None,
            str(data.get("address") or "").strip() or None,
            str(data.get("comment") or "").strip() or None,
        ))
        supplier_id = cur.fetchone()["id"]
        conn.commit()
        return jsonify({"success": True, "id": supplier_id})
    finally:
        pool.putconn(conn)


@suppliers_bp.route("/api/suppliers/<int:supplier_id>/delete", methods=["POST"])
def api_supplier_delete(supplier_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM suppliers WHERE id = %s AND company_id = %s AND is_active = TRUE",
            (supplier_id, company_id),
        )
        if not cur.fetchone():
            return jsonify({"success": False, "error": "Поставщик не найден"}), 404

        action, linked_count = _delete_supplier_record(cur, company_id, supplier_id)
        conn.commit()
        return jsonify({
            "success": True,
            "action": action,
            "linked_count": linked_count,
            "message": (
                "Поставщик удалён"
                if action == "deleted"
                else "Поставщик скрыт из активных. История приходов сохранена"
            ),
        })
    except Exception as error:
        conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        pool.putconn(conn)


@suppliers_bp.route("/api/suppliers/<int:supplier_id>", methods=["PUT", "DELETE"])
def api_supplier_detail(supplier_id):
    company_id = session.get("company_id")
    if not company_id:
        return jsonify({"success": False, "error": "Компания не выбрана"}), 401

    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name FROM suppliers WHERE id = %s AND company_id = %s",
            (supplier_id, company_id),
        )
        supplier = cur.fetchone()
        if not supplier:
            return jsonify({"success": False, "error": "Поставщик не найден"}), 404

        if request.method == "DELETE":
            action, linked_count = _delete_supplier_record(cur, company_id, supplier_id)
            conn.commit()
            return jsonify({
                "success": True,
                "action": action,
                "linked_count": linked_count,
                "message": (
                    "Поставщик удалён"
                    if action == "deleted"
                    else "Поставщик скрыт из активных. История приходов сохранена"
                ),
            })

        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": "Укажите название поставщика"}), 400

        cur.execute("""
            UPDATE suppliers
            SET name=%s, bin_iin=%s, contact_name=%s, phone=%s,
                email=%s, address=%s, comment=%s, updated_at=NOW()
            WHERE id=%s AND company_id=%s
        """, (
            name,
            str(data.get("bin_iin") or "").strip() or None,
            str(data.get("contact_name") or "").strip() or None,
            str(data.get("phone") or "").strip() or None,
            str(data.get("email") or "").strip() or None,
            str(data.get("address") or "").strip() or None,
            str(data.get("comment") or "").strip() or None,
            supplier_id,
            company_id,
        ))
        conn.commit()
        return jsonify({"success": True})
    finally:
        pool.putconn(conn)


@suppliers_bp.route("/stock/income/supplier", methods=["POST"])
def stock_income_with_supplier():
    company_id = session.get("company_id")
    conn = get_db()
    try:
        ensure_supplier_schema(conn)
        cur = conn.cursor()

        item_id = request.form.get("item_id")
        supplier_id = request.form.get("supplier_id")
        try:
            quantity = float(request.form.get("quantity", 0))
            price = float(request.form.get("price", 0))
        except (TypeError, ValueError):
            return "Некорректное количество или цена", 400

        if quantity <= 0 or price < 0:
            return "Проверьте количество и закупочную цену", 400

        if not is_product(cur, item_id, company_id):
            return "Приход доступен только для товаров", 400

        supplier = _supplier_for_company(cur, supplier_id, company_id)
        if not supplier:
            return "Выберите поставщика", 400

        cur.execute("SELECT name FROM items WHERE id = %s AND company_id = %s", (item_id, company_id))
        item_row = cur.fetchone()
        item_name = item_row["name"] if item_row else f"Товар #{item_id}"

        comment = request.form.get("comment")
        total = quantity * price
        movement_datetime = datetime.utcnow() + timedelta(hours=5)

        cur.execute("""
            INSERT INTO stock_movements (
                company_id, item_id, movement_type, quantity, price,
                total, comment, supplier_id, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            company_id, item_id, "income", quantity, price,
            total, comment, supplier["id"], movement_datetime
        ))
        movement_id = cur.fetchone()["id"]

        expense_id = upsert_expense_from_source(
            cur,
            company_id=company_id,
            source_type="stock_income",
            source_id=movement_id,
            category="Закупки",
            description=f"Закуп товара: {item_name} · {supplier['name']}",
            amount=total,
            expense_date=movement_datetime.date(),
            payment_method="Другое",
            comment=comment or f"Поставщик: {supplier['name']}",
            user_id=session.get("user_id"),
        )
        _sync_expense_to_accounting(cur, expense_id, company_id)
        conn.commit()
        return redirect("/stock/income")
    finally:
        pool.putconn(conn)


# Import for side effect: attaches /subscription/selection to the already
# registered subscriptions blueprint before Flask starts serving requests.
from routes import subscription_selection as _subscription_selection  # noqa: E402,F401
