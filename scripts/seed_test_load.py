#!/usr/bin/env python3
"""Generate synthetic data only in an isolated Nika TEST PostgreSQL database."""
import argparse
import os
import psycopg2
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_file = os.environ.get("NIKA_ENV_FILE", ".env")
load_dotenv(env_file if os.path.isabs(env_file) else os.path.join(ROOT, env_file), override=True)

SIZES = {"small": (1000, 250, 5000, 15000),
         "medium": (5000, 1250, 25000, 75000),
         "large": (20000, 5000, 100000, 300000)}
MARKER = "[PERF-TEST]"


def validate(conn):
    if os.environ.get("APP_MODE", "").lower() != "test":
        raise RuntimeError("APP_MODE must be test")
    if os.environ.get("NIKA_ALLOW_SYNTHETIC_SEED") != "YES":
        raise RuntimeError("Set NIKA_ALLOW_SYNTHETIC_SEED=YES")
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    if "test" not in dbname.lower():
        raise RuntimeError("Refusing to seed database without 'test' in its name: " + dbname)
    prod = os.getenv("NIKA_PRODUCTION_DATABASE_URL")
    if prod and prod == os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL matches the production URL")


def create_data(conn, sizes, company_name=None):
    ni, nc, ns, nm = sizes
    with conn.cursor() as cur:
        cur.execute("INSERT INTO companies(name,is_active,business_mode) VALUES (%s,TRUE,'retail') RETURNING id",
                    (company_name or MARKER + " Нагрузочная организация",))
        cid = cur.fetchone()[0]
        cur.execute("INSERT INTO company_subscriptions(company_id,status,trial_ends_at,period_end) "
                    "VALUES (%s,'active',NOW()+INTERVAL '5 years',NOW()+INTERVAL '5 years')", (cid,))
        cur.execute("INSERT INTO company_modules(company_id,module_id,enabled,status) "
                    "SELECT %s,id,TRUE,'active' FROM modules WHERE is_active=TRUE AND code <> 'cto' "
                    "ON CONFLICT DO NOTHING", (cid,))
        cur.execute("INSERT INTO categories(company_id,name,markup_percent,category_type) "
                    "SELECT %s, %s || n::text, 20,'product' FROM generate_series(1,20) n",
                    (cid, MARKER + " Категория "))
        cur.execute("INSERT INTO items(company_id,name,category,item_type,unit,retail_price,purchase_price,quantity,barcode) "
                    "SELECT %s,%s||n::text,%s||(((n-1) %% 20)+1)::text,'product','шт',"
                    "500+(n %% 1000),300+(n %% 500),100,'299'||lpad((%s::bigint*100000+n)::text,10,'0') "
                    "FROM generate_series(1,%s) n", (cid, MARKER+" Товар ", MARKER+" Категория ",cid,ni))
        cur.execute("CREATE TEMP TABLE perf_items ON COMMIT DROP AS "
                    "SELECT id,row_number() OVER (ORDER BY id) rn FROM items WHERE company_id=%s", (cid,))
        cur.execute("INSERT INTO clients(company_id,full_name,is_deleted,created_at) "
                    "SELECT %s,%s||n::text,FALSE,NOW()-(n %% 365)*INTERVAL '1 day' "
                    "FROM generate_series(1,%s) n", (cid,MARKER+" Клиент ",nc))
        cur.execute("CREATE TEMP TABLE perf_clients ON COMMIT DROP AS "
                    "SELECT id,row_number() OVER (ORDER BY id) rn FROM clients WHERE company_id=%s", (cid,))
        cur.execute("INSERT INTO sales(company_id,client_id,sale_number,total_amount,paid_amount,status,"
                    "sale_type,cash_amount,card_amount,kaspi_amount,created_at) "
                    "SELECT %s,c.id,n,500+(n %% 1000),500+(n %% 1000),'Оплачено','cash',"
                    "500+(n %% 1000),0,0,NOW()-(n %% 365)*INTERVAL '1 day' "
                    "FROM generate_series(1,%s) n JOIN perf_clients c ON c.rn=((n-1) %% %s)+1",
                    (cid,ns,nc))
        cur.execute("CREATE TEMP TABLE perf_sales ON COMMIT DROP AS "
                    "SELECT id,row_number() OVER (ORDER BY id) rn FROM sales WHERE company_id=%s", (cid,))
        cur.execute("INSERT INTO sale_items(sale_id,item_id,name,price,quantity,total,profit,item_type,unit) "
                    "SELECT s.id,i.id,%s||i.rn::text,500+(s.rn %% 1000),1,500+(s.rn %% 1000),"
                    "200,'product','шт' FROM perf_sales s JOIN perf_items i ON i.rn=((s.rn-1) %% %s)+1",
                    (MARKER+" Товар ",ni))
        # The normal stock trigger recalculates one item's full ledger after EACH
        # inserted movement. A 75,000-row synthetic insert can therefore take many
        # minutes. Only in this validated TEST seeder, pause the exact quantity-cache
        # trigger inside our existing transaction, then rebuild the new company's
        # cached quantities in a single grouped UPDATE.
        #
        # ALTER TABLE is transactional in PostgreSQL: an error/rollback restores
        # the original trigger state and removes ALL generated company data.
        # It also takes a table lock, so fail quickly if other TEST requests are
        # currently using stock_movements rather than stall the site.
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgrelid = 'stock_movements'::regclass
                  AND tgname = 'trg_nika_stock_movement_sync_quantity'
                  AND NOT tgisinternal
            )
        """)
        sync_trigger_exists = cur.fetchone()[0]
        if sync_trigger_exists:
            cur.execute("SET LOCAL lock_timeout = '5s'")
            cur.execute("ALTER TABLE stock_movements DISABLE TRIGGER trg_nika_stock_movement_sync_quantity")
            cur.execute("SET LOCAL lock_timeout = DEFAULT")

        print("Loading synthetic stock movements...", flush=True)
        cur.execute("INSERT INTO stock_movements(company_id,item_id,movement_type,quantity,price,total,comment,created_at) "
                    "SELECT %s,i.id,CASE WHEN n %% 3=0 THEN 'writeoff' WHEN n %% 3=1 THEN 'income' "
                    "ELSE 'sale' END,1,300,300,%s,NOW()-(n %% 365)*INTERVAL '1 day' "
                    "FROM generate_series(1,%s) n JOIN perf_items i ON i.rn=((n-1) %% %s)+1",
                    (cid,MARKER,nm,ni))

        if sync_trigger_exists:
            cur.execute("""
                UPDATE items i
                   SET quantity = totals.qty
                  FROM (
                        SELECT item_id,
                               COALESCE(SUM(
                                   CASE
                                       WHEN movement_type IN ('income', 'refund') THEN quantity
                                       WHEN movement_type IN ('sale', 'writeoff') THEN -quantity
                                       ELSE 0
                                   END
                               ), 0) AS qty
                          FROM stock_movements
                         WHERE company_id = %s
                         GROUP BY item_id
                       ) AS totals
                 WHERE i.company_id = %s
                   AND i.id = totals.item_id
                   AND COALESCE(i.item_type, 'product') = 'product'
            """, (cid, cid))
            cur.execute("ALTER TABLE stock_movements ENABLE TRIGGER trg_nika_stock_movement_sync_quantity")
        print("Synthetic stock movements complete.", flush=True)
        return cid


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--size", choices=list(SIZES), default="small")
    p.add_argument("--company-name", default=None,
                   help="Synthetic company name, must begin with [PERF-TEST]")
    p.add_argument("--skip-existing", action="store_true",
                   help="Do not duplicate an already seeded company of this name")
    p.add_argument("--check-only", action="store_true",
                   help="Verify test database and check whether the company exists")
    p.add_argument("--confirm", action="store_true")
    args = p.parse_args()
    if not args.check_only and not args.confirm:
        p.error("Explicit --confirm is required")
    if args.skip_existing and not args.company_name:
        p.error("--skip-existing requires --company-name")
    if args.company_name is not None and not args.company_name.startswith(MARKER):
        p.error("The synthetic company name must start with [PERF-TEST]")
    if not os.environ.get("DATABASE_URL"):
        p.error("DATABASE_URL is required")
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=10)
    try:
        validate(conn)
        if args.company_name:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM companies WHERE name = %s ORDER BY id LIMIT 1",
                            (args.company_name,))
                existing = cur.fetchone()
            if existing:
                if args.check_only or args.skip_existing:
                    print("Synthetic company already exists:", existing[0],
                          "(skipping write)")
                    return
                raise RuntimeError("Synthetic company already exists; refusing duplicate load")
        if args.check_only:
            print("Verified isolated TEST database; requested synthetic company is absent")
            return
        company_id = create_data(conn, SIZES[args.size],
                                 company_name=args.company_name)
        conn.commit()
        print("Synthetic TEST company:", company_id, "counts:", SIZES[args.size])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
