-- One-time setup of the database and its three roles. Run as the postgres superuser:
--
--   psql -U postgres -h localhost -v ON_ERROR_STOP=1 `
--        -v owner_pw="..." -v app_pw="..." -v ro_pw="..." -f db/init.sql
--
-- Pick three different passwords without quotes or backslashes. Safe to re-run.
--
-- Roles:
--   expense_owner : owns the database and every table; used only to run migrations.
--   app_user      : what the FastAPI app connects as. It does NOT own the tables, so
--                   row-level security policies apply to it and cannot be bypassed.
--   ai_readonly   : executes AI-generated SQL. Read-only, short statement timeout, and it
--                   will be granted SELECT on the allowlisted spending views only.

SELECT format('CREATE ROLE expense_owner LOGIN PASSWORD %L', :'owner_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'expense_owner') \gexec

SELECT format('CREATE ROLE app_user LOGIN PASSWORD %L', :'app_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') \gexec

SELECT format('CREATE ROLE ai_readonly LOGIN PASSWORD %L', :'ro_pw')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_readonly') \gexec

-- None of these roles may bypass row-level security or create roles/databases.
ALTER ROLE expense_owner NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE app_user      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
ALTER ROLE ai_readonly   NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

-- Limits for AI-generated queries (scope section 6.5).
ALTER ROLE ai_readonly SET statement_timeout = '5s';
ALTER ROLE ai_readonly SET default_transaction_read_only = on;

SELECT 'CREATE DATABASE expense_tracker OWNER expense_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'expense_tracker') \gexec

\connect expense_tracker

-- Only the three project roles may connect.
REVOKE ALL ON DATABASE expense_tracker FROM PUBLIC;
GRANT CONNECT ON DATABASE expense_tracker TO expense_owner, app_user, ai_readonly;

GRANT USAGE ON SCHEMA public TO app_user, ai_readonly;

-- Tables the owner creates later (in migrations) are readable/writable by the app role
-- automatically. ai_readonly gets no default access: it is granted the spending views
-- explicitly, one by one.
ALTER DEFAULT PRIVILEGES FOR ROLE expense_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES FOR ROLE expense_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_user;
