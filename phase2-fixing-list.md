# Phase 2 Fixing List

Items to resolve before the Phase 2 acceptance gate can be considered passed.

---

## Code fixes (do these before deploying)

- [x] **Fix 4 `test_policy_engine.py` mock-exhaustion failures**
  - Tests: `TestHappyPath`, `TestDepartmentAddOn`, `TestQuotaExceeded` (and one more)
  - Root cause: `AsyncMock side_effect` lists are one entry short after Rule 4 (quota check) was added in Task 2.3
  - File: `backend/tests/unit/test_policy_engine.py`
  - Actual fix: `celery.schedules` was missing from the conftest stubs — adding `from celery.schedules import crontab` to `celery_app.py` (retention worker beat schedule) broke the `audit_writer` import, failing all 16 tests. Added `sys.modules["celery.schedules"]` stub to `conftest.py`. All 16 pass.

- [x] **Delete `backend/demo_seed.py`**
  - Scratch file left from a curl demo session — must not be committed to the repo

- [x] **Add `pytest-docker>=3` to `pyproject.toml` dev-dependencies**
  - Was installed manually during Task 2.3 integration test work; not yet in the lockfile
  - File: `backend/pyproject.toml`
  - Already present on line 37 — no change needed

- [x] **Provision `audit_log` Postgres partition for July 2026 (and beyond)**
  - The baseline migration only created partitions up to the current month
  - Without a July partition, audit writes will fail after 2026-07-01
  - Added migration `0003_audit_partitions.py` (covers 2026-07 → 2027-12)
  - Added `retention.py` Celery beat task (creates partition 2 months ahead, fires 1st of each month)

---

## Deployment steps (do these on the production server)

- [ ] **Run `alembic upgrade head`** to apply migration `0002_consent_acknowledged`
  - Adds `consent_acknowledged_at` column to `users`
  - Adds `consent_acknowledged` value to the `audit_action` enum
  - Users cannot chat until this is applied (consent gate returns 500 on missing column)

---

## Phase 2 acceptance gate (requires 30+ days of production use)

- [ ] All 100 employees onboarded and able to log in
- [ ] One full billing cycle (≥ 30 days) of external API usage tracked; quota totals within < 5% of provider invoice
- [ ] At least one reveal request submitted, approved by a different admin, and viewed end-to-end in production
- [ ] Audit log shows zero successful external API calls where `data_tier >= TIER_3` (verify with SQL)
