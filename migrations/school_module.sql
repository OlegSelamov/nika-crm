BEGIN;

INSERT INTO modules(code,name,description,category,monthly_price,route_prefix,icon,is_core,is_active,sort_order)
VALUES('school','Школа','Классные руководители, ежедневное питание и отчёты.','Школа',1490,'/school','/static/icons/tasks.png',FALSE,TRUE,130)
ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name,description=EXCLUDED.description,category=EXCLUDED.category,monthly_price=EXCLUDED.monthly_price,route_prefix=EXCLUDED.route_prefix,icon=EXCLUDED.icon,is_active=TRUE,sort_order=EXCLUDED.sort_order;

CREATE TABLE IF NOT EXISTS school_classes(id SERIAL PRIMARY KEY,company_id INTEGER NOT NULL,name TEXT NOT NULL,sort_order INTEGER DEFAULT 100,is_active BOOLEAN DEFAULT TRUE,created_at TIMESTAMP DEFAULT NOW(),UNIQUE(company_id,name));
CREATE TABLE IF NOT EXISTS school_class_leaders(id SERIAL PRIMARY KEY,company_id INTEGER NOT NULL,class_id INTEGER REFERENCES school_classes(id) ON DELETE SET NULL,full_name TEXT NOT NULL,room TEXT,phone TEXT,created_at TIMESTAMP DEFAULT NOW(),updated_at TIMESTAMP DEFAULT NOW());
CREATE TABLE IF NOT EXISTS school_meal_prices(id SERIAL PRIMARY KEY,company_id INTEGER NOT NULL,free_price NUMERIC(12,2) NOT NULL DEFAULT 0,paid_price NUMERIC(12,2) NOT NULL DEFAULT 0,effective_from DATE NOT NULL DEFAULT CURRENT_DATE,created_at TIMESTAMP DEFAULT NOW(),UNIQUE(company_id,effective_from));
CREATE TABLE IF NOT EXISTS school_meals(id SERIAL PRIMARY KEY,company_id INTEGER NOT NULL,class_id INTEGER NOT NULL REFERENCES school_classes(id) ON DELETE CASCADE,meal_date DATE NOT NULL,plan_count INTEGER NOT NULL DEFAULT 0 CHECK(plan_count>=0),fact_count INTEGER NOT NULL DEFAULT 0 CHECK(fact_count>=0),free_count INTEGER NOT NULL DEFAULT 0 CHECK(free_count>=0),paid_count INTEGER NOT NULL DEFAULT 0 CHECK(paid_count>=0),free_price NUMERIC(12,2) NOT NULL DEFAULT 0,paid_price NUMERIC(12,2) NOT NULL DEFAULT 0,note TEXT,created_by INTEGER,created_at TIMESTAMP DEFAULT NOW(),updated_at TIMESTAMP DEFAULT NOW(),UNIQUE(company_id,class_id,meal_date));
CREATE INDEX IF NOT EXISTS idx_school_meals_company_date ON school_meals(company_id,meal_date DESC);
CREATE INDEX IF NOT EXISTS idx_school_leaders_company ON school_class_leaders(company_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_school_one_leader_per_class ON school_class_leaders(company_id,class_id) WHERE class_id IS NOT NULL;

COMMIT;
