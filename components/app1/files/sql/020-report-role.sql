-- A read-only reporting login. MOUNTS in config.defaults.yaml mounts this file
-- into seed-database; install fills in @@DB_NAME@@ and the generated password.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'todo_report') THEN
    CREATE ROLE todo_report LOGIN;
  END IF;
END
$$;
ALTER ROLE todo_report PASSWORD '@@secret:app1-report-password/password@@';
GRANT CONNECT ON DATABASE @@DB_NAME@@ TO todo_report;
GRANT SELECT ON demo_seed TO todo_report;
