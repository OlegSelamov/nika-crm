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
        cur.execute("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("ALTER TABLE users ADD COLUMN last_seen_at TIMESTAMP")
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
        cur.execute("""
            INSERT INTO integrations (company_id, created_at)
            SELECT id, NOW()
            FROM companies
            WHERE id NOT IN (
                SELECT company_id
                FROM integrations
                WHERE company_id IS NOT NULL
            )
        """)
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
        cur.execute("""
            ALTER TABLE items
            ADD COLUMN item_type TEXT NOT NULL DEFAULT 'product'
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            UPDATE items
            SET item_type = 'product'
            WHERE item_type IS NULL OR item_type = ''
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE categories
            ADD COLUMN category_type TEXT NOT NULL DEFAULT 'product'
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            UPDATE categories
            SET category_type = 'product'
            WHERE category_type IS NULL OR category_type = ''
        """)
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
        
    try:
        cur.execute("ALTER TABLE sale_items ADD COLUMN excise_stamp TEXT")
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("""
            ALTER TABLE integrations
            ADD COLUMN rekassa_enabled BOOLEAN DEFAULT FALSE
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE integrations
            ADD COLUMN rekassa_number TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE integrations
            ADD COLUMN rekassa_password TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE integrations
            ADD COLUMN rekassa_crs_id INTEGER
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE integrations
            ADD COLUMN rekassa_serial_number TEXT
        """)
        conn.commit()
    except:
            conn.rollback()
            
    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_ticket_id BIGINT
        """)
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_ticket_number TEXT
        """)
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_document_number TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_rnm TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_znm TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_ticket_number TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_qr TEXT
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_shift_number INTEGER
        """)
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN rekassa_status TEXT
        """)
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN sale_number INTEGER
        """)
        conn.commit()
    except:
        conn.rollback()
        
    try:
        cur.execute("""
            ALTER TABLE sales
            ADD COLUMN user_id INTEGER
        """)
        conn.commit()
    except:
        conn.rollback()
        
    # ================== SAAS / SUBSCRIPTIONS ==================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS modules (
        id SERIAL PRIMARY KEY,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        category TEXT DEFAULT 'Основное',
        monthly_price NUMERIC(12,2) DEFAULT 0,
        annual_price NUMERIC(12,2) DEFAULT 0,
        route_prefix TEXT,
        icon TEXT,
        is_core BOOLEAN DEFAULT FALSE,
        is_active BOOLEAN DEFAULT TRUE,
        sort_order INTEGER DEFAULT 100,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS company_subscriptions (
        id SERIAL PRIMARY KEY,
        company_id INTEGER UNIQUE NOT NULL,
        status TEXT DEFAULT 'trial',
        billing_period TEXT DEFAULT 'month',
        base_price NUMERIC(12,2) DEFAULT 2990,
        employees_price NUMERIC(12,2) DEFAULT 0,
        branches_price NUMERIC(12,2) DEFAULT 0,
        modules_price NUMERIC(12,2) DEFAULT 0,
        discount NUMERIC(12,2) DEFAULT 0,
        total_price NUMERIC(12,2) DEFAULT 0,
        trial_ends_at TIMESTAMP,
        period_start TIMESTAMP,
        period_end TIMESTAMP,
        next_payment_at TIMESTAMP,
        auto_renew BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS company_modules (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL,
        module_id INTEGER NOT NULL,
        enabled BOOLEAN DEFAULT TRUE,
        status TEXT DEFAULT 'trial',
        price NUMERIC(12,2) DEFAULT 0,
        billing_period TEXT DEFAULT 'month',
        activated_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(company_id, module_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS employee_module_permissions (
        id SERIAL PRIMARY KEY,
        employee_id INTEGER NOT NULL,
        module_id INTEGER NOT NULL,
        allowed BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(employee_id, module_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscription_payments (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL,
        subscription_id INTEGER,
        amount NUMERIC(12,2) NOT NULL,
        currency TEXT DEFAULT 'KZT',
        provider TEXT,
        payment_method TEXT,
        provider_payment_id TEXT,
        status TEXT DEFAULT 'created',
        description TEXT,
        paid_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscription_changes (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL,
        user_id INTEGER,
        action TEXT NOT NULL,
        old_value JSONB,
        new_value JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """)

    module_seed = [
        ('profile', 'Профиль', 'Профиль сотрудника и личная статистика.', 'Основное', 0, '/profile', '/static/icons/profile.png', True, 10),
        ('dashboard', 'Главная', 'Главная панель компании.', 'Основное', 0, '/dashboard', '/static/icons/home.png', True, 20),
        ('sales', 'Продажи', 'Кассовое рабочее место, чеки, возвраты и история продаж.', 'Торговля', 1490, '/sales', '/static/icons/sales.png', False, 30),
        ('analytics', 'Аналитика', 'Выручка, прибыль, средний чек и показатели сотрудников.', 'Управление', 1490, '/analytics', '/static/icons/analytics.png', False, 40),
        ('catalog', 'Каталог', 'Товары, категории, цены, штрихкоды и единицы измерения.', 'Торговля', 790, '/items', '/static/icons/items.png', False, 50),
        ('tasks', 'Задачи', 'Задачи, сроки и контроль исполнения.', 'Управление', 490, '/tasks', '/static/icons/tasks.png', False, 60),
        ('cto', 'ККМ и ЦТО', 'Кассовые аппараты и обслуживание ЦТО.', 'Интеграции', 1490, '/cto', '/static/icons/cto.png', False, 70),
        ('accounting', 'Бухгалтерия', 'Налоги, платежи и бухгалтерский контроль.', 'Финансы', 1990, '/accounting', '/static/icons/buh.png', False, 80),
        ('reports', 'Отчёты', 'Формы 910, 200 и управленческие отчёты.', 'Финансы', 1490, '/reports', '/static/icons/otchet.png', False, 90),
        ('expenses', 'Расходы', 'Учет расходов и движения денежных средств.', 'Финансы', 990, '/expenses', '/static/icons/rashod.png', False, 100),
        ('warehouse', 'Склад', 'Остатки, приход, списание и движение товара.', 'Склад', 990, '/stock', '/static/icons/stock.png', False, 110),
        ('clients', 'Клиенты', 'Клиентская база, статусы, история и документы.', 'CRM', 990, '/clients', '/static/icons/clients.png', False, 120),
        ('settings', 'Настройки', 'Настройки компании и интеграций.', 'Система', 0, '/settings', '/static/icons/settings.png', True, 200)
    ]

    for module in module_seed:
        cur.execute("""
            INSERT INTO modules (
                code, name, description, category, monthly_price,
                route_prefix, icon, is_core, sort_order
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                monthly_price = EXCLUDED.monthly_price,
                route_prefix = EXCLUDED.route_prefix,
                icon = EXCLUDED.icon,
                is_core = EXCLUDED.is_core,
                sort_order = EXCLUDED.sort_order,
                is_active = TRUE
        """, module)

    cur.execute("""
        INSERT INTO company_subscriptions (
            company_id, status, billing_period, base_price,
            trial_ends_at, period_start, next_payment_at
        )
        SELECT id, 'trial', 'month', 2990,
               NOW() + INTERVAL '14 days', NOW(), NOW() + INTERVAL '14 days'
        FROM companies
        ON CONFLICT (company_id) DO NOTHING
    """)

    cur.execute("""
        INSERT INTO company_modules (
            company_id, module_id, enabled, status, price, billing_period
        )
        SELECT c.id, m.id, TRUE, 'trial', m.monthly_price, 'month'
        FROM companies c
        CROSS JOIN modules m
        WHERE m.is_core = TRUE
           OR m.code IN ('sales', 'catalog', 'warehouse', 'clients', 'analytics')
        ON CONFLICT (company_id, module_id) DO NOTHING
    """)

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