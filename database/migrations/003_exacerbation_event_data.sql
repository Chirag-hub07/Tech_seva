-- Migration 003: Add event_data to exacerbations
-- Purpose: Preserve original source event fields as JSONB.

ALTER TABLE public.exacerbations
ADD COLUMN IF NOT EXISTS event_data JSONB;

COMMENT ON COLUMN public.exacerbations.event_data IS
'Original source exacerbation event fields preserved as JSONB.';