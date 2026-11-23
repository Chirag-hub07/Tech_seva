-- Add a source identifier to make clinical assessment imports idempotent.
ALTER TABLE public.clinical_assessments
ADD COLUMN IF NOT EXISTS source_record_id TEXT;

-- Prevent duplicate source records for the same patient.
CREATE UNIQUE INDEX IF NOT EXISTS idx_clinical_source_record
ON public.clinical_assessments (patient_id, source_record_id)
WHERE source_record_id IS NOT NULL;
