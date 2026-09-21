from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, session, flash, jsonify
from models import get_db, pool
from utils.timezone import now_kz

production_bp = Blueprint("production", __name__)

def _recipe_availability(cur, company_id, item_id, output_qty=Decimal("1")):
    cur.execute("""SELECT r.ingredient_item_id, r.quantity, i.name, i.unit,
                  COALESCE(i.purchase_price,0) purchase_price, COALESCE(i.quantity,0) available
                  FROM item_recipes r JOIN items i ON i.id=r.ingredient_item_id AND i.company_id=r.company_id
                  WHERE r.company_id=%s AND r.item_id=%s ORDER BY i.name""", (company_id,item_id))
    rows=[]; max_output=None
    for row in cur.fetchall():
        per_unit=Decimal(str(row["quantity"])); available=Decimal(str(row["available"] or 0)); needed=per_unit*output_qty
        possible=(available/per_unit) if per_unit>0 else Decimal("0")
        max_output=possible if max_output is None else min(max_output,possible)
        rows.append({**dict(row),"needed":needed,"enough":available>=needed})
    return rows, (max_output or Decimal("0"))

@production_bp.route("/api/stock/production/<int:item_id>/availability")
def production_availability(item_id):
    company_id=session.get("company_id")
    try: qty=Decimal(str(request.args.get("quantity") or 1))
    except (InvalidOperation,TypeError,ValueError): qty=Decimal("1")
    conn=get_db(); cur=conn.cursor()
    try:
        rows,max_output=_recipe_availability(cur,company_id,item_id,max(qty,Decimal("0")))
        return jsonify({"success":True,"max_output":float(max_output),"ingredients":[{"item_id":r["ingredient_item_id"],"name":r["name"],"unit":r["unit"],"per_unit":float(r["quantity"]),"needed":float(r["needed"]),"available":float(r["available"]),"enough":r["enough"]} for r in rows]})
    finally:
        cur.close(); pool.putconn(conn)

@production_bp.route("/stock/production", methods=["GET", "POST"])
def production():
    company_id = session.get("company_id")
    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            try:
                item_id = int(request.form.get("item_id") or 0)
                output_qty = Decimal(str(request.form.get("quantity") or 0))
            except (ValueError, TypeError, InvalidOperation):
                item_id, output_qty = 0, Decimal("0")
            if output_qty <= 0:
                flash("Укажите количество приготовленного полуфабриката", "error")
                return redirect("/stock/production")

            cur.execute("SELECT id,name,unit FROM items WHERE id=%s AND company_id=%s AND item_type='semi_finished' FOR UPDATE", (item_id, company_id))
            item = cur.fetchone()
            if not item:
                flash("Полуфабрикат не найден", "error")
                return redirect("/stock/production")

            recipe, max_output = _recipe_availability(cur, company_id, item_id, output_qty)
            if not recipe:
                flash("Сначала заполните техкарту полуфабриката", "error")
                return redirect("/stock/production")
            shortages = [row for row in recipe if not row["enough"]]
            if shortages:
                names = ", ".join(row["name"] for row in shortages[:3])
                flash(f"Недостаточно сырья: {names}. Максимально можно приготовить {max_output:.3f} {item['unit']}", "error")
                return redirect("/stock/production")

            total_cost = Decimal("0")
            created = now_kz()
            for row in recipe:
                needed = Decimal(str(row["quantity"])) * output_qty
                cur.execute("UPDATE items SET quantity=COALESCE(quantity,0)-%s WHERE id=%s AND company_id=%s", (needed,row["ingredient_item_id"],company_id))
                cost = needed * Decimal(str(row["purchase_price"] or 0))
                total_cost += cost
                cur.execute("""INSERT INTO stock_movements(company_id,item_id,movement_type,quantity,price,total,comment,created_at)
                               VALUES(%s,%s,'writeoff',%s,%s,%s,%s,%s)""",
                            (company_id,row["ingredient_item_id"],needed,row["purchase_price"],cost,
                             "Производство: "+item["name"],created))

            unit_cost = total_cost / output_qty if output_qty else Decimal("0")
            cur.execute("UPDATE items SET quantity=COALESCE(quantity,0)+%s, purchase_price=%s WHERE id=%s AND company_id=%s",
                        (output_qty,unit_cost,item_id,company_id))
            cur.execute("""INSERT INTO stock_movements(company_id,item_id,movement_type,quantity,price,total,comment,created_at)
                           VALUES(%s,%s,'income',%s,%s,%s,%s,%s)""",
                        (company_id,item_id,output_qty,unit_cost,total_cost,"Производство полуфабриката",created))
            conn.commit()
            flash(f"Приготовлено: {item['name']} — {output_qty} {item['unit']}", "success")
            return redirect("/stock/production")

        cur.execute("""SELECT i.id,i.name,i.unit,COALESCE(i.quantity,0) quantity,
                      EXISTS(SELECT 1 FROM item_recipes r WHERE r.company_id=i.company_id AND r.item_id=i.id) has_recipe
                      FROM items i WHERE i.company_id=%s AND i.item_type='semi_finished' ORDER BY i.name""",(company_id,))
        items=cur.fetchall()
        cur.execute("""SELECT sm.*,i.name item_name,i.unit FROM stock_movements sm JOIN items i ON i.id=sm.item_id
                       WHERE sm.company_id=%s AND i.item_type='semi_finished' AND sm.movement_type='income'
                       AND sm.comment='Производство полуфабриката' ORDER BY sm.id DESC LIMIT 30""",(company_id,))
        history=cur.fetchall()
        return render_template("stock_production.html",items=items,history=history)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        pool.putconn(conn)
