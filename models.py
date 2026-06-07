import psycopg2
import psycopg2.extras
import os

from dotenv import load_dotenv

from utils.timezone import now_kz
from psycopg2.pool import SimpleConnectionPool
import pytz

kz = pytz.timezone("Asia/Almaty")

load_dotenv()

pool = SimpleConnectionPool(
    1,
    20,
    os.environ.get("DATABASE_URL")
)

def get_db():

    conn = pool.getconn()

    conn.cursor_factory = psycopg2.extras.RealDictCursor

    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id SERIAL PRIMARY KEY,
        name TEXT,
        price NUMERIC(12,2),
        category TEXT,
        type TEXT
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS item_images (
        id SERIAL PRIMARY KEY,
        item_id INTEGER,
        image TEXT
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS client_items (
        id SERIAL PRIMARY KEY,
        client_id INTEGER,
        item_id INTEGER,
        price NUMERIC(12,2),
        payment_method TEXT,
        is_paid BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'cashier',
        company_id INTEGER,
        is_super_admin BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id SERIAL PRIMARY KEY,
        is_deleted BOOLEAN DEFAULT FALSE,
        full_name TEXT,
        phone TEXT,
        status TEXT,
        category TEXT,
        payment TEXT,
        comment TEXT,
        address TEXT,
        created_at TIMESTAMP,
        iin TEXT,
        company_name TEXT,
        photo TEXT,
        comment_photos TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id SERIAL PRIMARY KEY,
        title TEXT,
        client_id INTEGER,
        due_date TEXT
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id SERIAL PRIMARY KEY,
        name TEXT,
        price NUMERIC(12,2)
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id SERIAL PRIMARY KEY,
        client_id INTEGER,
        total_amount NUMERIC(12,2),
        paid_amount NUMERIC(12,2),
        status TEXT,
        created_at TIMESTAMP
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        name TEXT,
        bin TEXT,
        address TEXT,
        phone TEXT,
        is_active BOOLEAN DEFAULT FALSE
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sale_items (
        id SERIAL PRIMARY KEY,
        sale_id INTEGER,
        item_id INTEGER,
        price NUMERIC(12,2),
        quantity NUMERIC(12,3),
        total NUMERIC(12,2),
        profit NUMERIC(12,2) DEFAULT 0
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id SERIAL PRIMARY KEY,
        company_id INTEGER,
        name TEXT,
        markup_percent REAL DEFAULT 0
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_movements (
        id SERIAL PRIMARY KEY,

        company_id INTEGER,

        item_id INTEGER,

        movement_type TEXT,

        quantity NUMERIC(12,3),

        price NUMERIC(12,2),

        total NUMERIC(12,2),

        comment TEXT,

        created_at TIMESTAMP
    )
    """)
    
    conn.commit()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS integrations (

        id SERIAL PRIMARY KEY,

        company_id INTEGER,

        kkm_type TEXT,

        webkassa_enabled BOOLEAN DEFAULT FALSE,
        webkassa_login TEXT,
        webkassa_password TEXT,
        webkassa_cashbox TEXT,

        pos_enabled BOOLEAN DEFAULT FALSE,
        pos_type TEXT,
        pos_ip TEXT,
        pos_port TEXT,

        created_at TIMESTAMP
    )
    """)
    
    try:
        cur.execute("""
            INSERT INTO users (
                username,
                password,
                role,
                is_super_admin,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            "admin",
            "12345",
            "admin",
            True,
            now_kz()
        ))

        conn.commit()

    except:
        conn.rollback()
            
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE")
        conn.commit()    
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN description TEXT")
        conn.commit()    
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE items ADD COLUMN retail_price INTEGER")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE items ADD COLUMN wholesale_price INTEGER")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE items ADD COLUMN discount_percent INTEGER")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE items ADD COLUMN purchase_price INTEGER")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE items ADD COLUMN barcode TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN company_id INTEGER")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN iik TEXT")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN bik TEXT")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN bank TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN kbe TEXT")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN knp TEXT")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN director TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sale_items ADD COLUMN unit TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN unit TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN markup_percent REAL DEFAULT 0")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN paid_at TIMESTAMP;")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN sale_type TEXT;")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sale_items ADD COLUMN name TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN cash_amount NUMERIC(12,2) DEFAULT 0")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE sales ADD COLUMN card_amount NUMERIC(12,2) DEFAULT 0")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE sales ADD COLUMN kaspi_amount NUMERIC(12,2) DEFAULT 0")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN kaspi_transaction_id TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN kaspi_method TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN is_refunded BOOLEAN DEFAULT FALSE
        """)
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'cashier'")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE users ADD COLUMN company_id INTEGER")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_super_admin BOOLEAN DEFAULT FALSE")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_creator BOOLEAN DEFAULT FALSE")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN percent_rate NUMERIC(12,2) DEFAULT 0;")
        conn.commit()
    except:
        conn.rollback()
                
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN owner_id INTEGER")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN tariff TEXT")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN paid_until TIMESTAMP")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN company_id INTEGER")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN company_id INTEGER")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN contract_number TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN contract_date TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN is_processed BOOLEAN DEFAULT FALSE;")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN quantity NUMERIC(12,3) DEFAULT 0;")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN gtin TEXT;")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN ntin TEXT;")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN is_marked BOOLEAN DEFAULT FALSE;")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("ALTER TABLE sale_items ADD COLUMN gtin TEXT;")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE sale_items ADD COLUMN ntin TEXT;")
        conn.commit()
    except:
        conn.rollback()
        
    # 🔥 INDEXES

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_sales_company
    ON sales(company_id)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_items_company
    ON items(company_id)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_clients_company
    ON clients(company_id)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_stock_company
    ON stock_movements(company_id)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_sale_items_sale
    ON sale_items(sale_id)
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_items_barcode
    ON items(barcode)
    """)
         
    conn.commit()
    pool.putconn(conn)