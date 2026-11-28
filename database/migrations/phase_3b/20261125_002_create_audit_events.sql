-- =============================================================================
-- Migration: 20261125_002_create_audit_events.sql
-- Module: Phase 3B - Medical Audit Logging Table
-- Safety: Append-only enforcement (SELECT/INSERT only; zero UPDATE/DELETE/TRUNCATE).
-- =============================================================================

BEGIN;

-- Prerequisite assertion
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'exacerbalert_backend') THEN
        RAISE EXCEPTION 'Prerequisite role "exacerbalert_backend" does not exist. Execute 20261125_000_provision_backend_role.sql first.';
    END IF;
END $$;

-- 1. Create audit_events table
CREATE TABLE IF NOT EXISTS public.audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    event_type VARCHAR(64) NOT NULL,
    actor_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    actor_email VARCHAR(255) NOT NULL,
    actor_role VARCHAR(32) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    target_id VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address VARCHAR(64) NULL, -- Pseudonymized HMAC-SHA256 (32 hex characters)
    user_agent VARCHAR(256) NULL, -- Sanitized, capped at 256 chars
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_audit_event_type CHECK (
        event_type IN (
            'USER_ROLE_UPDATED',
            'PATIENT_ASSIGNMENT_CREATED',
            'PATIENT_ASSIGNMENT_REVOKED',
            'ALERT_ACKNOWLEDGED'
        )
    )
);

-- 2. Query Indexes
CREATE INDEX IF NOT EXISTS idx_audit_actor ON public.audit_events (actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_target ON public.audit_events (target_type, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON public.audit_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_created ON public.audit_events (created_at DESC);

-- 3. Explicit Role Grants
GRANT SELECT, INSERT ON TABLE public.audit_events TO exacerbalert_backend;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_events FROM exacerbalert_backend;
REVOKE ALL ON TABLE public.audit_events FROM anon, authenticated, PUBLIC;

-- Sequence usage on generated identity
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'audit_events_id_seq' AND relkind = 'S') THEN
        GRANT USAGE, SELECT ON SEQUENCE public.audit_events_id_seq TO exacerbalert_backend;
    END IF;
END $$;

-- 4. Enable and FORCE Row-Level Security
ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "backend_select_audit_events" ON public.audit_events;
CREATE POLICY "backend_select_audit_events" 
    ON public.audit_events 
    FOR SELECT 
    TO exacerbalert_backend 
    USING (true);

DROP POLICY IF EXISTS "backend_insert_audit_events" ON public.audit_events;
CREATE POLICY "backend_insert_audit_events" 
    ON public.audit_events 
    FOR INSERT 
    TO exacerbalert_backend 
    WITH CHECK (true);

COMMIT;
