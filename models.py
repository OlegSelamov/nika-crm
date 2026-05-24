import os
import sqlite3
from datetime import datetime

# если есть диск (на Render)
if os.path.exists("/data"):
    DATABASE = "/data/database.db"
else:
    # локально
    DATABASE = "database.db"

def get_db():

    # 🔥 PostgreSQL на Render
    if os.environ.get("DATABASE_URL"):

        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(
            os.environ.get("DATABASE_URL")
        )

        conn.cursor_factory = (
            psycopg2.extras.RealDictCursor
        )

        return conn

    # 🔥 SQLite локально
    else:

        conn = sqlite3.connect(
            DATABASE,
            timeout=5
        )

        conn.row_factory = sqlite3.Row

        return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id SERIAL PRIMARY KEY,
        name TEXT,
        price INTEGER,
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
        price INTEGER,
        payment_method TEXT,
        is_paid INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'cashier',
        company_id INTEGER,
        is_super_admin INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY,
        is_deleted INTEGER DEFAULT 0,
        full_name TEXT,
        phone TEXT,
        status TEXT,
        category TEXT,
        payment TEXT,
        comment TEXT,
        address TEXT,
        created_at TEXT,
        iin TEXT,
        company_name TEXT,
        photo TEXT,
        comment_photos TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY,
        title TEXT,
        client_id INTEGER,
        due_date TEXT
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY,
        name TEXT,
        price INTEGER
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id SERIAL PRIMARY KEY,
        client_id INTEGER,
        total_amount INTEGER,
        paid_amount INTEGER,
        status TEXT,
        created_at TEXT
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id SERIAL PRIMARY KEY,
        name TEXT,
        bin TEXT,
        address TEXT,
        phone TEXT,
        is_active INTEGER DEFAULT 0
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sale_items (
        id SERIAL PRIMARY KEY,
        sale_id INTEGER,
        item_id INTEGER,
        price INTEGER,
        quantity INTEGER,
        total INTEGER
        profit REAL DEFAULT 0
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

        quantity REAL,

        price REAL,

        total REAL,

        comment TEXT,

        created_at TEXT
    )
    """)
    
    cur.execute("SELECT * FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (username, password, role, is_super_admin, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            "admin",
            "12345",
            "admin",
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
            
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN is_deleted INTEGER DEFAULT 0")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN description TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE items ADD COLUMN retail_price INTEGER")
    except:
        pass

    try:
        cur.execute("ALTER TABLE items ADD COLUMN wholesale_price INTEGER")
    except:
        pass

    try:
        cur.execute("ALTER TABLE items ADD COLUMN discount_percent INTEGER")
    except:
        pass

    try:
        cur.execute("ALTER TABLE items ADD COLUMN purchase_price INTEGER")
    except:
        pass

    try:
        cur.execute("ALTER TABLE items ADD COLUMN barcode TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN company_id INTEGER")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN iik TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN bik TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN bank TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN kbe TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN knp TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN director TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE sale_items ADD COLUMN unit TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN unit TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN markup_percent REAL DEFAULT 0")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN paid_at TEXT;")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN sale_type TEXT;")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE sale_items ADD COLUMN name TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN cash_amount INTEGER DEFAULT 0")
    except:
        pass

    try:
        cur.execute("ALTER TABLE sales ADD COLUMN card_amount INTEGER DEFAULT 0")
    except:
        pass

    try:
        cur.execute("ALTER TABLE sales ADD COLUMN kaspi_amount INTEGER DEFAULT 0")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'cashier'")
    except:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN company_id INTEGER")
    except:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_super_admin INTEGER DEFAULT 0")
    except:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE users ADD COLUMN is_creator INTEGER DEFAULT 0")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN owner_id INTEGER")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE companies ADD COLUMN is_active INTEGER DEFAULT 1")
    except:
        pass

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN tariff TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE companies ADD COLUMN paid_until TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN company_id INTEGER")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN company_id INTEGER")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN contract_number TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE clients ADD COLUMN contract_date TEXT")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE sales ADD COLUMN is_processed INTEGER DEFAULT 0;")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN quantity REAL DEFAULT 0;")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN gtin TEXT;")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN ntin TEXT;")
    except:
        pass
        
    try:
        cur.execute("ALTER TABLE items ADD COLUMN is_marked INTEGER DEFAULT 0;")
    except:
        pass
         
    conn.commit()
    conn.close()