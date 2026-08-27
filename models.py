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
        profit NUMERIC(12,2) DEFAULT 0,
        item_type TEXT
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
            ALTER TABLE items
            ADD COLUMN service_sale_mode TEXT DEFAULT 'order'
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
        cur.execute("ALTER TABLE sale_items ADD COLUMN item_type TEXT;")
        conn.commit()
    except:
        conn.rollback()

    try:
        cur.execute("""
            UPDATE sale_items si
            SET item_type = COALESCE(i.item_type, 'product')
            FROM items i
            WHERE si.item_id = i.id
              AND (si.item_type IS NULL OR si.item_type = '')
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


    # ================== ONBOARDING / EASY START ==================

    # Эти изменения безопасно выполняются повторно при каждом запуске.
    cur.execute("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()
    """)

    cur.execute("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS city TEXT
    """)

    cur.execute("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS business_type TEXT
    """)

    cur.execute("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS registration_source TEXT DEFAULT 'direct'
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_progress (
            id SERIAL PRIMARY KEY,
            company_id INTEGER UNIQUE NOT NULL,
            owner_user_id INTEGER,
            current_step INTEGER DEFAULT 1,
            business_type TEXT,
            has_products BOOLEAN,
            has_employees BOOLEAN,
            needs_cashbox BOOLEAN,
            needs_accounting BOOLEAN,
            completed BOOLEAN DEFAULT FALSE,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_onboarding_company
        ON onboarding_progress(company_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_companies_created_at
        ON companies(created_at)
    """)


    # ================== FUNCTIONAL ONBOARDING ==================

    cur.execute("""
        ALTER TABLE onboarding_progress
        ADD COLUMN IF NOT EXISTS employee_count INTEGER DEFAULT 0
    """)

    cur.execute("""
        ALTER TABLE onboarding_progress
        ADD COLUMN IF NOT EXISTS sells_services BOOLEAN
    """)

    cur.execute("""
        ALTER TABLE onboarding_progress
        ADD COLUMN IF NOT EXISTS has_stock BOOLEAN
    """)

    cur.execute("""
        ALTER TABLE onboarding_progress
        ADD COLUMN IF NOT EXISTS needs_reports BOOLEAN
    """)

    cur.execute("""
        ALTER TABLE onboarding_progress
        ADD COLUMN IF NOT EXISTS needs_clients BOOLEAN
    """)

    cur.execute("""
        ALTER TABLE onboarding_progress
        ADD COLUMN IF NOT EXISTS needs_tasks BOOLEAN
    """)

    cur.execute("""
        ALTER TABLE onboarding_progress
        ADD COLUMN IF NOT EXISTS selected_modules TEXT[]
    """)


    # ================== STOREFRONT / ONLINE SALES ==================

    cur.execute("""
        ALTER TABLE items
        ADD COLUMN IF NOT EXISTS storefront_visible BOOLEAN DEFAULT FALSE
    """)

    cur.execute("""
        ALTER TABLE items
        ADD COLUMN IF NOT EXISTS storefront_hidden BOOLEAN DEFAULT FALSE
    """)

    cur.execute("""
        ALTER TABLE items
        ADD COLUMN IF NOT EXISTS booking_duration_minutes INTEGER DEFAULT 60
    """)

    cur.execute("""
        ALTER TABLE items
        ADD COLUMN IF NOT EXISTS booking_enabled BOOLEAN DEFAULT TRUE
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS storefront_settings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            title TEXT,
            description TEXT,
            logo_url TEXT,
            cover_url TEXT,
            whatsapp TEXT,
            instagram TEXT,
            enabled BOOLEAN DEFAULT FALSE,
            show_products BOOLEAN DEFAULT TRUE,
            show_services BOOLEAN DEFAULT TRUE,
            allow_orders BOOLEAN DEFAULT TRUE,
            allow_booking BOOLEAN DEFAULT TRUE,
            allow_payment BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS online_orders (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            storefront_id INTEGER,
            customer_name TEXT,
            phone TEXT,
            address TEXT,
            delivery_method TEXT DEFAULT 'pickup',
            comment TEXT,
            total_amount NUMERIC(12,2) DEFAULT 0,
            payment_status TEXT DEFAULT 'unpaid',
            order_status TEXT DEFAULT 'new',
            source TEXT DEFAULT 'storefront',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS online_order_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL,
            item_id INTEGER,
            name TEXT,
            quantity NUMERIC(12,3) DEFAULT 1,
            price NUMERIC(12,2) DEFAULT 0,
            total NUMERIC(12,2) DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            storefront_id INTEGER,
            item_id INTEGER,
            employee_id INTEGER,
            customer_name TEXT,
            phone TEXT,
            booking_date DATE,
            booking_time TIME,
            duration_minutes INTEGER DEFAULT 60,
            status TEXT DEFAULT 'new',
            payment_status TEXT DEFAULT 'unpaid',
            comment TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_storefront_slug
        ON storefront_settings(slug)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_online_orders_company
        ON online_orders(company_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_online_order_items_order
        ON online_order_items(order_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bookings_company
        ON bookings(company_id)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bookings_company_date
        ON bookings(company_id, booking_date)
    """)


    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS work_start TIME DEFAULT '09:00'
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS work_end TIME DEFAULT '18:00'
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS slot_interval_minutes INTEGER DEFAULT 30
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS delivery_enabled BOOLEAN DEFAULT FALSE
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS pickup_enabled BOOLEAN DEFAULT TRUE
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS delivery_price NUMERIC(12,2) DEFAULT 0
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS min_order_amount NUMERIC(12,2) DEFAULT 0
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS theme TEXT DEFAULT 'marketplace'
    """)

    cur.execute("""
        ALTER TABLE online_orders
        ADD COLUMN IF NOT EXISTS customer_id INTEGER
    """)

    cur.execute("""
        ALTER TABLE online_orders
        ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMP
    """)

    cur.execute("""
        ALTER TABLE online_orders
        ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP
    """)

    cur.execute("""
        ALTER TABLE bookings
        ADD COLUMN IF NOT EXISTS customer_id INTEGER
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_busy_slot
        ON bookings(company_id, booking_date, booking_time, item_id)
        WHERE status NOT IN ('cancelled', 'rejected')
    """)



    # ================== STOREFRONT BRANDING / FINAL SETTINGS ==================

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS brand_color TEXT DEFAULT '#6366f1'
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS card_style TEXT DEFAULT 'rounded'
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS hero_style TEXT DEFAULT 'gradient'
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS show_stock BOOLEAN DEFAULT TRUE
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS show_categories BOOLEAN DEFAULT TRUE
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS custom_domain TEXT
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS domain_status TEXT DEFAULT 'not_connected'
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS payment_provider TEXT
    """)

    cur.execute("""
        ALTER TABLE storefront_settings
        ADD COLUMN IF NOT EXISTS payment_enabled BOOLEAN DEFAULT FALSE
    """)



    # ================== STOREFRONT BANNERS ==================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS storefront_banners (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,
            storefront_id INTEGER,
            image_url TEXT NOT NULL,
            title TEXT,
            subtitle TEXT,
            button_text TEXT,
            button_url TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_storefront_banners_company
        ON storefront_banners(company_id, is_active, sort_order)
    """)

    # ================== WHATSAPP / GREEN-API ==================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_integrations (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL,

            provider TEXT NOT NULL DEFAULT 'green_api',

            phone TEXT,
            instance_id TEXT NOT NULL,
            api_token TEXT NOT NULL,

            enabled BOOLEAN DEFAULT TRUE,
            incoming_enabled BOOLEAN DEFAULT TRUE,
            outgoing_enabled BOOLEAN DEFAULT TRUE,

            ai_enabled BOOLEAN DEFAULT FALSE,
            ai_instructions TEXT,

            status TEXT DEFAULT 'unknown',

            webhook_token TEXT,

            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(company_id),
            UNIQUE(instance_id)
        )
    """)


    cur.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_chats (
            id BIGSERIAL PRIMARY KEY,

            company_id INTEGER NOT NULL,
            integration_id INTEGER NOT NULL,

            external_chat_id TEXT NOT NULL,

            phone TEXT,
            contact_name TEXT,

            customer_id INTEGER,

            last_message TEXT,
            last_message_at TIMESTAMP,

            unread_count INTEGER DEFAULT 0,

            ai_paused BOOLEAN DEFAULT FALSE,
            ai_paused_at TIMESTAMP,
            ai_pause_reason TEXT,

            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),

            UNIQUE(integration_id, external_chat_id)
        )
    """)


    cur.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            id BIGSERIAL PRIMARY KEY,

            company_id INTEGER NOT NULL,
            integration_id INTEGER NOT NULL,
            chat_id BIGINT NOT NULL,

            external_message_id TEXT,

            direction TEXT NOT NULL,
            message_type TEXT DEFAULT 'text',

            message_text TEXT,

            sender_phone TEXT,

            status TEXT DEFAULT 'received',

            is_ai BOOLEAN DEFAULT FALSE,

            ai_processed_at TIMESTAMP,
            ai_error TEXT,

            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_whatsapp_external_message
        ON whatsapp_messages(integration_id, external_message_id)
        WHERE external_message_id IS NOT NULL
    """)


    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_integrations_company
        ON whatsapp_integrations(company_id)
    """)


    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_chats_company
        ON whatsapp_chats(company_id)
    """)


    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_chats_last_message
        ON whatsapp_chats(company_id, last_message_at DESC)
    """)


    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_whatsapp_messages_chat
        ON whatsapp_messages(chat_id, created_at)
    """)

    # WhatsApp media/status metadata for the communication center.
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS media_url TEXT")
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS file_name TEXT")
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS mime_type TEXT")
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS caption TEXT")
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP")
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMP")

    # Customer-facing Nika AI for WhatsApp. ALTERs also upgrade existing databases.
    cur.execute("ALTER TABLE whatsapp_integrations ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE whatsapp_integrations ADD COLUMN IF NOT EXISTS ai_instructions TEXT")
    cur.execute("ALTER TABLE whatsapp_chats ADD COLUMN IF NOT EXISTS ai_paused BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE whatsapp_chats ADD COLUMN IF NOT EXISTS ai_paused_at TIMESTAMP")
    cur.execute("ALTER TABLE whatsapp_chats ADD COLUMN IF NOT EXISTS ai_pause_reason TEXT")
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS ai_processed_at TIMESTAMP")
    cur.execute("ALTER TABLE whatsapp_messages ADD COLUMN IF NOT EXISTS ai_error TEXT")

    # ================== BCC OPEN API ==================
    # Ключ и пароль приложения BCC хранятся только в окружении сервера.
    # В базе находятся зашифрованные клиентские токены каждой организации.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bcc_integrations (
            id BIGSERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL UNIQUE,
            environment TEXT NOT NULL DEFAULT 'sandbox',
            client_idn TEXT,
            access_token_encrypted TEXT,
            refresh_token_encrypted TEXT,
            token_type TEXT,
            token_expires_at TIMESTAMPTZ,
            scope TEXT,
            status TEXT NOT NULL DEFAULT 'disconnected',
            connected_at TIMESTAMPTZ,
            last_sync_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bcc_integrations_company
        ON bcc_integrations(company_id)
    """)

    # Nika AI: история диалогов хранится отдельно для каждой компании и пользователя.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_conversations (
            id TEXT PRIMARY KEY,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_messages (
            id BIGSERIAL PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_conversations_owner
        ON ai_conversations(company_id, user_id, updated_at DESC)
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
        ON ai_messages(conversation_id, id)
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
