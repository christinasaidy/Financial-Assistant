-- Stops the assistant's generated SQL from switching to another user's rows.
--
-- Row-level security reads the current user from the setting `app.user_id`. Any role may normally call
-- set_config() to change a setting, even inside a SELECT, so a query run as ai_readonly could switch to
-- another user's id. This takes set_config() away from everyone except the two roles that need it.
-- ai_readonly sets the user with SET LOCAL instead, which cannot appear inside a SELECT.
--
-- Run once as the postgres superuser (built-in functions can only be changed by a superuser):
--
--   psql -U postgres -h localhost -d expense_tracker -v ON_ERROR_STOP=1 -f db/restrict_set_config.sql
--
-- Safe to run more than once. It is also part of db/init.sql for new setups.

REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) TO expense_owner, app_user;
