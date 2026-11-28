-- =============================================================================
-- Migration: 20261125_001_create_clinician_patient_assignments.sql
-- Module: Phase 3B - Clinician-Patient Assignment Table
-- Safety: Enforces ON DELETE RESTRICT, partial unique index, and FORCE RLS.
-- Access: exacerbalert_backend granted strictly SELECT and INSERT (UPDATE revoked).
-- =============================================================================

BEGIN;

-- Prerequisite assertion
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'exacerbalert_backend') THEN
        RAISE EXCEPTION 'Prerequisite role "exacerbalert_backend" does not exist. Execute 20261125_000_provision_backend_role.sql first.';
    END IF;
END $$;

-- 1. Create clinician_patient_assignments table
CREATE TABLE IF NOT EXISTS public.clinician_patient_assignments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clinician_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    patient_id BIGINT NOT NULL REFERENCES public.patients(id) ON DELETE RESTRICT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
    revoked_at TIMESTAMPTZ NULL,
    revoked_by UUID NULL REFERENCES auth.users(id) ON DELETE RESTRICT,

    CONSTRAINT chk_revocation_chronology CHECK (
        revoked_at IS NULL OR revoked_at >= assigned_at
    ),
    CONSTRAINT chk_revocation_actor_pair CHECK (
        (revoked_at IS NULL AND revoked_by IS NULL) OR
        (revoked_at IS NOT NULL AND revoked_by IS NOT NULL)
    )
);

-- 2. Partial Unique Index: Exactly one ACTIVE assignment permitted per clinician-patient pair
CREATE UNIQUE INDEX IF NOT EXISTS idx_cpa_active_pair 
    ON public.clinician_patient_assignments (clinician_id, patient_id) 
    WHERE revoked_at IS NULL;

-- 3. Dedicated B-Tree Index for active patient lookups
CREATE INDEX IF NOT EXISTS idx_cpa_patient_active 
    ON public.clinician_patient_assignments (patient_id) 
    WHERE revoked_at IS NULL;

-- 4. Dedicated B-Tree Index for clinician audit history
CREATE INDEX IF NOT EXISTS idx_cpa_clinician_history 
    ON public.clinician_patient_assignments (clinician_id, assigned_at DESC);

-- 5. Explicit Role Grants: SELECT and INSERT only. UPDATE is strictly revoked!
GRANT SELECT, INSERT ON TABLE public.clinician_patient_assignments TO exacerbalert_backend;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.clinician_patient_assignments FROM exacerbalert_backend;
REVOKE ALL ON TABLE public.clinician_patient_assignments FROM anon, authenticated, PUBLIC;

-- Sequence usage on generated identity
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relname = 'clinician_patient_assignments_id_seq' AND relkind = 'S') THEN
        GRANT USAGE, SELECT ON SEQUENCE public.clinician_patient_assignments_id_seq TO exacerbalert_backend;
    END IF;
END $$;

-- 6. Enable and FORCE Row-Level Security
ALTER TABLE public.clinician_patient_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clinician_patient_assignments FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "backend_select_assignments" ON public.clinician_patient_assignments;
CREATE POLICY "backend_select_assignments" 
    ON public.clinician_patient_assignments 
    FOR SELECT 
    TO exacerbalert_backend 
    USING (true);

DROP POLICY IF EXISTS "backend_insert_assignments" ON public.clinician_patient_assignments;
CREATE POLICY "backend_insert_assignments" 
    ON public.clinician_patient_assignments 
    FOR INSERT 
    TO exacerbalert_backend 
    WITH CHECK (true);

COMMIT;
