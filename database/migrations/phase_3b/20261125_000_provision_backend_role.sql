-- =============================================================================
-- Migration: 20261125_000_provision_backend_role.sql
-- Module: Phase 3B - Backend Role Provisioning, Clinical Security & Default Privileges
-- Safety: Enforces NOSUPERUSER, NOBYPASSRLS, and locks down public/browser access.
-- =============================================================================

BEGIN;

-- 0. Verification of Authoritative Migration Executor
-- In both Supabase and standard PostgreSQL environments, application migrations must be executed
-- by the authoritative application database owner: 'postgres'.
-- Platform-managed administrative roles such as 'supabase_admin' are internal to Supabase infrastructure;
-- they own internal extensions and infrastructure schemas, and their default ACLs cannot (and should not)
-- be altered by application migrations. 'supabase_admin' is NOT an interchangeable application executor.
DO $$
BEGIN
    IF NOT pg_has_role(current_user, 'postgres', 'MEMBER') THEN
        RAISE EXCEPTION 'MIGRATION_HALTED: Migration executor "%" must be a member of the authoritative application role "postgres". Application migrations must be executed as postgres.', current_user;
    END IF;
    RAISE NOTICE 'Migration executor "%" confirmed as member of authoritative role "postgres".', current_user;
END $$;

-- 1. Create or verify dedicated backend application role
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'exacerbalert_backend') THEN
        CREATE ROLE exacerbalert_backend WITH 
            LOGIN 
            NOSUPERUSER 
            NOCREATEDB 
            NOCREATEROLE 
            NOINHERIT 
            NOBYPASSRLS
            CONNECTION LIMIT 20;
        RAISE NOTICE 'Role exacerbalert_backend successfully created.';
    ELSE
        ALTER ROLE exacerbalert_backend WITH 
            LOGIN 
            NOSUPERUSER 
            NOCREATEDB 
            NOCREATEROLE 
            NOINHERIT 
            NOBYPASSRLS;
        RAISE NOTICE 'Role exacerbalert_backend flags verified.';
    END IF;
END $$;

-- 2. Schema USAGE requirement
GRANT USAGE ON SCHEMA public TO exacerbalert_backend;

-- 3. HARDEN EXISTING CLINICAL TABLES: Revoke public and browser web access
REVOKE ALL ON TABLE 
    public.patients, 
    public.sensor_measurements, 
    public.clinical_assessments, 
    public.exacerbations, 
    public.predictions, 
    public.alerts 
FROM PUBLIC, anon, authenticated;

-- 4. Grant minimal necessary privileges to exacerbalert_backend
GRANT SELECT ON 
    public.patients, 
    public.sensor_measurements, 
    public.clinical_assessments, 
    public.exacerbations, 
    public.predictions 
TO exacerbalert_backend;

-- Grant column-level UPDATE strictly on status and acknowledged_at
GRANT SELECT, UPDATE (status, acknowledged_at) ON public.alerts TO exacerbalert_backend;

-- Strictly revoke destructive privileges from exacerbalert_backend
REVOKE INSERT, DELETE, TRUNCATE ON 
    public.patients, 
    public.sensor_measurements, 
    public.clinical_assessments, 
    public.exacerbations, 
    public.predictions, 
    public.alerts 
FROM exacerbalert_backend;

REVOKE UPDATE ON 
    public.patients, 
    public.sensor_measurements, 
    public.clinical_assessments, 
    public.exacerbations, 
    public.predictions 
FROM exacerbalert_backend;

-- Sequence usage on alerts sequence (if exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'alerts_id_seq' AND relkind = 'S') THEN
        GRANT USAGE, SELECT ON SEQUENCE public.alerts_id_seq TO exacerbalert_backend;
    END IF;
END $$;

-- 5. Enable and FORCE Row-Level Security on all 6 clinical tables
ALTER TABLE public.patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.patients FORCE ROW LEVEL SECURITY;

ALTER TABLE public.sensor_measurements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sensor_measurements FORCE ROW LEVEL SECURITY;

ALTER TABLE public.clinical_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clinical_assessments FORCE ROW LEVEL SECURITY;

ALTER TABLE public.exacerbations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exacerbations FORCE ROW LEVEL SECURITY;

ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions FORCE ROW LEVEL SECURITY;

ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts FORCE ROW LEVEL SECURITY;

-- 6. Define explicit RLS policies for exacerbalert_backend on clinical tables
DROP POLICY IF EXISTS "backend_select_patients" ON public.patients;
CREATE POLICY "backend_select_patients" 
    ON public.patients FOR SELECT TO exacerbalert_backend USING (true);

DROP POLICY IF EXISTS "backend_select_sensor_measurements" ON public.sensor_measurements;
CREATE POLICY "backend_select_sensor_measurements" 
    ON public.sensor_measurements FOR SELECT TO exacerbalert_backend USING (true);

DROP POLICY IF EXISTS "backend_select_clinical_assessments" ON public.clinical_assessments;
CREATE POLICY "backend_select_clinical_assessments" 
    ON public.clinical_assessments FOR SELECT TO exacerbalert_backend USING (true);

DROP POLICY IF EXISTS "backend_select_exacerbations" ON public.exacerbations;
CREATE POLICY "backend_select_exacerbations" 
    ON public.exacerbations FOR SELECT TO exacerbalert_backend USING (true);

DROP POLICY IF EXISTS "backend_select_predictions" ON public.predictions;
CREATE POLICY "backend_select_predictions" 
    ON public.predictions FOR SELECT TO exacerbalert_backend USING (true);

DROP POLICY IF EXISTS "backend_select_alerts" ON public.alerts;
CREATE POLICY "backend_select_alerts" 
    ON public.alerts FOR SELECT TO exacerbalert_backend USING (true);

-- Constrain alert update to pending -> acknowledged transition only
DROP POLICY IF EXISTS "backend_update_alerts" ON public.alerts;
CREATE POLICY "backend_update_alerts" 
    ON public.alerts FOR UPDATE TO exacerbalert_backend 
    USING (status = 'pending') 
    WITH CHECK (status = 'acknowledged' AND acknowledged_at IS NOT NULL);

-- 7. Audit & Alter Default Privileges for future objects
-- PostgreSQL rule: Schema-specific REVOKEs do NOT cancel privileges granted through global default privileges.
-- Therefore, we apply global default revokes FIRST, followed by schema-specific revokes in schema public.
-- In Supabase and local PostgreSQL environments, 'postgres' is the authoritative role that authors all application
-- tables, views, sequences, and routines. Platform-managed roles (such as 'supabase_admin') manage infrastructure
-- and platform extensions separately; their default ACLs are isolated from application tables.

-- 7.1 Global Default Privileges for authoritative role 'postgres'
ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON ROUTINES FROM PUBLIC, anon, authenticated;

-- 7.2 Schema-specific Default Privileges in schema public for authoritative role 'postgres'
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON ROUTINES FROM PUBLIC, anon, authenticated;

-- 7.3 Apply to current_user if executing under a distinct role alias
DO $$
BEGIN
    IF current_user <> 'postgres' THEN
        RAISE NOTICE 'Applying default privilege revokes for current executing role "%"...', current_user;
        EXECUTE 'ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;';
        EXECUTE 'ALTER DEFAULT PRIVILEGES REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;';
        EXECUTE 'ALTER DEFAULT PRIVILEGES REVOKE ALL ON ROUTINES FROM PUBLIC, anon, authenticated;';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON ROUTINES FROM PUBLIC, anon, authenticated;';
    END IF;
END $$;

-- 7.4 Audit effective pg_default_acl state for authoritative role 'postgres'
DO $$
DECLARE
    rec record;
BEGIN
    RAISE NOTICE '--- [Post-Migration] pg_default_acl state for postgres ---';
    FOR rec IN (
        SELECT 
            defaclrole::regrole::text AS role_name,
            CASE WHEN defaclnamespace = 0 THEN '(global)' ELSE defaclnamespace::regnamespace::text END AS scope,
            defaclobjtype AS obj_type,
            array_to_string(defaclacl, ',') AS acl_entries
        FROM pg_default_acl
        WHERE defaclrole = 'postgres'::regrole
    ) LOOP
        RAISE NOTICE 'Role: %, Scope: %, Obj: %, ACL: %', rec.role_name, rec.scope, rec.obj_type, rec.acl_entries;
    END LOOP;
END $$;

COMMIT;
