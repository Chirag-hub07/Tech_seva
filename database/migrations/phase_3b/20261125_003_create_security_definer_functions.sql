-- =============================================================================
-- Migration: 20261125_003_create_security_definer_functions.sql
-- Module: Phase 3B - Hardened SECURITY DEFINER Status and Revocation Functions
-- Safety: Fixed search_path (pg_catalog, pg_temp), trusted owner (postgres),
--         and EXECUTE privileges granted strictly to exacerbalert_backend.
-- =============================================================================

BEGIN;

-- Prerequisite assertion
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'exacerbalert_backend') THEN
        RAISE EXCEPTION 'Prerequisite role "exacerbalert_backend" does not exist. Execute 20261125_000_provision_backend_role.sql first.';
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- Function 1: Authoritative User Status & Permission Verification
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_auth_user_status(p_user_id UUID)
RETURNS TABLE (
    id UUID,
    email VARCHAR,
    role VARCHAR,
    permissions JSONB,
    banned_until TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        u.id,
        u.email::VARCHAR,
        (u.raw_app_meta_data->>'role')::VARCHAR AS role,
        pg_catalog.coalesce(u.raw_app_meta_data->'permissions', '[]'::jsonb) AS permissions,
        u.banned_until,
        u.deleted_at
    FROM auth.users u
    WHERE u.id = p_user_id;
END;
$$;

-- Establish trusted owner
ALTER FUNCTION public.get_auth_user_status(UUID) OWNER TO postgres;

-- Revoke default public execution
REVOKE ALL ON FUNCTION public.get_auth_user_status(UUID) FROM PUBLIC, anon, authenticated;

-- Grant execution strictly to exacerbalert_backend
GRANT EXECUTE ON FUNCTION public.get_auth_user_status(UUID) TO exacerbalert_backend;


-- -----------------------------------------------------------------------------
-- Function 2: Narrowly Scoped Atomic Assignment Revocation
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.revoke_patient_assignment(
    p_assignment_id BIGINT,
    p_revoked_by UUID,
    p_client_ip VARCHAR DEFAULT NULL,
    p_user_agent VARCHAR DEFAULT NULL
)
RETURNS public.clinician_patient_assignments
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_record public.clinician_patient_assignments;
    v_actor_email VARCHAR;
    v_actor_role VARCHAR;
    v_actor_banned TIMESTAMPTZ;
    v_actor_deleted TIMESTAMPTZ;
BEGIN
    -- 1. Lock the target assignment row for update
    SELECT * INTO v_record
    FROM public.clinician_patient_assignments
    WHERE id = p_assignment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'ASSIGNMENT_NOT_FOUND: Assignment with ID % does not exist.', p_assignment_id;
    END IF;

    -- 2. State transition check: Must be currently active
    IF v_record.revoked_at IS NOT NULL THEN
        RAISE EXCEPTION 'ASSIGNMENT_ALREADY_REVOKED: Assignment % was already revoked at %.', p_assignment_id, v_record.revoked_at;
    END IF;

    -- 3. Verify revoking actor exists, is active, unbanned, undeleted, and holds administrator role
    SELECT 
        u.email::VARCHAR, 
        (u.raw_app_meta_data->>'role')::VARCHAR,
        u.banned_until,
        u.deleted_at
    INTO v_actor_email, v_actor_role, v_actor_banned, v_actor_deleted
    FROM auth.users u
    WHERE u.id = p_revoked_by;

    IF v_actor_role IS NULL OR v_actor_role != 'administrator' THEN
        RAISE EXCEPTION 'UNAUTHORIZED_ACTOR: Revoking user % must have active administrator role.', p_revoked_by;
    END IF;

    IF v_actor_deleted IS NOT NULL THEN
        RAISE EXCEPTION 'ACCOUNT_DELETED: Revoking administrator account % is deleted.', p_revoked_by;
    END IF;

    IF v_actor_banned IS NOT NULL AND v_actor_banned > pg_catalog.clock_timestamp() THEN
        RAISE EXCEPTION 'ACCOUNT_BANNED: Revoking administrator account % is currently banned.', p_revoked_by;
    END IF;

    -- 4. Atomically execute revocation
    UPDATE public.clinician_patient_assignments
    SET 
        revoked_at = pg_catalog.now(),
        revoked_by = p_revoked_by
    WHERE id = p_assignment_id
    RETURNING * INTO v_record;

    -- 5. Atomically insert audit event in the same transaction
    INSERT INTO public.audit_events (
        event_type,
        actor_id,
        actor_email,
        actor_role,
        target_type,
        target_id,
        action,
        details,
        ip_address,
        user_agent,
        created_at
    ) VALUES (
        'PATIENT_ASSIGNMENT_REVOKED',
        p_revoked_by,
        v_actor_email,
        v_actor_role,
        'ASSIGNMENT',
        p_assignment_id::VARCHAR,
        'REVOKE_ACCESS',
        pg_catalog.json_build_object(
            'clinician_id', v_record.clinician_id,
            'patient_id', v_record.patient_id,
            'assigned_at', v_record.assigned_at,
            'revoked_at', v_record.revoked_at
        )::jsonb,
        p_client_ip,
        p_user_agent,
        pg_catalog.now()
    );

    RETURN v_record;
END;
$$;

-- Establish trusted owner
ALTER FUNCTION public.revoke_patient_assignment(BIGINT, UUID, VARCHAR, VARCHAR) OWNER TO postgres;

-- Revoke default public execution
REVOKE ALL ON FUNCTION public.revoke_patient_assignment(BIGINT, UUID, VARCHAR, VARCHAR) FROM PUBLIC, anon, authenticated;

-- Grant execution strictly to exacerbalert_backend
GRANT EXECUTE ON FUNCTION public.revoke_patient_assignment(BIGINT, UUID, VARCHAR, VARCHAR) TO exacerbalert_backend;

COMMIT;
