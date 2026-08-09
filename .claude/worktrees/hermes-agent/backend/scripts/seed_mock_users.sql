-- Seed mock username/password accounts for local login (one per role).
-- SQL equivalent of scripts/seed_mock_users.py — use whichever fits your workflow.
--
-- Run against the app database, e.g.:
--   docker compose exec -T postgres psql -U brandbiz -d brandbiz < backend/scripts/seed_mock_users.sql
--
-- All accounts share the password: Passw0rd!
-- Hash below is bcrypt (cost 12) of that password, generated via
-- app.services.password.hash_password — do not hand-edit without regenerating.
--
-- Only useful while GOOGLE_OAUTH_CLIENT_ID is unset — POST /auth/login rejects
-- password logins once real Google OAuth is configured. Requires migrations
-- 0022_user_password_auth and 0023_login_failed_audit_action to be applied first.

INSERT INTO users (id, username, google_email, display_name, role, password_hash, is_active)
VALUES
    (gen_random_uuid(), 'l1.associate', 'l1.associate@company.local', 'l1.associate', 'L1', '$2b$12$cqqnb0cUwPN1P9pr5N2FNOTkwz.2z7l8eEnCZxZUep00r2NEubyxO', TRUE),
    (gen_random_uuid(), 'l2.analyst',   'l2.analyst@company.local',   'l2.analyst',   'L2', '$2b$12$cqqnb0cUwPN1P9pr5N2FNOTkwz.2z7l8eEnCZxZUep00r2NEubyxO', TRUE),
    (gen_random_uuid(), 'l3.senior',    'l3.senior@company.local',    'l3.senior',    'L3', '$2b$12$cqqnb0cUwPN1P9pr5N2FNOTkwz.2z7l8eEnCZxZUep00r2NEubyxO', TRUE),
    (gen_random_uuid(), 'l4.lead',      'l4.lead@company.local',      'l4.lead',      'L4', '$2b$12$cqqnb0cUwPN1P9pr5N2FNOTkwz.2z7l8eEnCZxZUep00r2NEubyxO', TRUE),
    (gen_random_uuid(), 'l5.manager',   'l5.manager@company.local',   'l5.manager',   'L5', '$2b$12$cqqnb0cUwPN1P9pr5N2FNOTkwz.2z7l8eEnCZxZUep00r2NEubyxO', TRUE),
    (gen_random_uuid(), 'l6.director',  'l6.director@company.local',  'l6.director',  'L6', '$2b$12$cqqnb0cUwPN1P9pr5N2FNOTkwz.2z7l8eEnCZxZUep00r2NEubyxO', TRUE),
    (gen_random_uuid(), 'admin',        'admin@company.local',        'admin',        'ADMIN', '$2b$12$cqqnb0cUwPN1P9pr5N2FNOTkwz.2z7l8eEnCZxZUep00r2NEubyxO', TRUE)
ON CONFLICT (username) DO UPDATE SET
    password_hash = EXCLUDED.password_hash,
    role = EXCLUDED.role,
    is_active = TRUE;
