Nika TEST synthetic load generator

Must use an independently provisioned PostgreSQL database whose name contains 'test'. Never point TEST at production. No actual payment, cash register, bank or messaging API is called.

Manual usage from /var/www/nika-business-test with TEST environment configured:

APP_MODE=test NIKA_ALLOW_SYNTHETIC_SEED=YES .venv/bin/python scripts/seed_test_load.py --size small --confirm

Sizes: small 1000 products / 250 clients / 5000 sales / 15000 stock movements; medium 5000 / 1250 / 25000 / 75000; large 20000 / 5000 / 100000 / 300000. Each invocation creates a new synthetic company prefixed [PERF-TEST]. No automatic loading on deploy; no cleanup procedure is implemented. Check available disk space and database backup first. A super administrator can choose the synthetic company to inspect it. Never run this on an unverified database.
