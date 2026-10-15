Nika TEST synthetic load generator

Must use an independently provisioned PostgreSQL database whose name contains 'test'. Never point TEST at production. No actual payment, cash register, bank or messaging API is called.

Manual usage from /var/www/nika-business-test with TEST environment configured:

APP_MODE=test NIKA_ALLOW_SYNTHETIC_SEED=YES .venv/bin/python scripts/seed_test_load.py --size small --confirm

Sizes: small 1000 products / 250 clients / 5000 sales / 15000 stock movements; medium 5000 / 1250 / 25000 / 75000; large 20000 / 5000 / 100000 / 300000. Each invocation creates a new synthetic company prefixed [PERF-TEST]. No automatic loading on deploy; no cleanup procedure is implemented. Check available disk space and database backup first. A super administrator can choose the synthetic company to inspect it. Never run this on an unverified database.

Medium TEST load (safe workflow):
- Open GitHub Actions -> "Seed medium performance data on TEST" -> Run workflow on test.
- The job checks that the connected DB is independently named *test* and APP_MODE=test,
  has at least 2 GB of free disk, and that the verified TEST backup
  /var/backups/nika-business-test/latest.dump exists. If any preflight fails,
  it stops without seeding.
- Seed: [PERF-TEST] Нагрузочная организация MEDIUM 2026-10; 5,000 items,
  1,250 clients, 25,000 sales, 75,000 stock movements. Existing companies
  are untouched. Running twice with the same name does not duplicate the load.
- Never enable seed on regular deployment. The backup must be created and
  validated by a TEST VPS administrator; a random or empty file is not a
  substitute for a validated PostgreSQL backup.
- The workflow is manual and will not run by merging this change into test.
- Compare client/item searches, sales history paging, stock movements,
  database response times, CPU/RAM and PostgreSQL performance separately.
