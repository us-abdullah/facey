-- ============================================================
-- Supabase schema for HOF Capital Security System
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- 1. Security incidents (main alert log)
CREATE TABLE IF NOT EXISTS security_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id TEXT UNIQUE NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_type TEXT NOT NULL,           -- unauthorized_door_access | zone_presence | line_crossing
    feed_id INTEGER NOT NULL DEFAULT 0,
    person_name TEXT NOT NULL DEFAULT 'Unknown',
    person_role TEXT,
    authorized BOOLEAN NOT NULL DEFAULT false,
    zone_name TEXT,
    details TEXT,
    acknowledged BOOLEAN NOT NULL DEFAULT false,
    resolution TEXT,                     -- NULL | acknowledged | problem_fixed
    recording_url TEXT,                  -- local API path to GIF
    report_url TEXT,                     -- local API path to PDF
    threat_image_url TEXT,               -- local API path to threat image
    escalation_level TEXT,               -- ROUTINE | URGENT | CRITICAL
    escalation_reasoning TEXT,
    recording_storage_path TEXT,         -- Supabase Storage path for GIF
    report_storage_path TEXT,            -- Supabase Storage path for PDF
    threat_image_storage_path TEXT       -- Supabase Storage path for threat image
);

CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON security_incidents (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_alert_type ON security_incidents (alert_type);
CREATE INDEX IF NOT EXISTS idx_incidents_person ON security_incidents (person_name);
CREATE INDEX IF NOT EXISTS idx_incidents_resolution ON security_incidents (resolution);

-- 2. Registered persons (visitors + non-visitors / employees)
CREATE TABLE IF NOT EXISTS registered_persons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_id TEXT UNIQUE NOT NULL,    -- matches face_service identity UUID
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Visitor', -- Visitor | Analyst | C-Level | custom
    authorized BOOLEAN NOT NULL DEFAULT true,
    is_visitor BOOLEAN NOT NULL DEFAULT true,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_persons_role ON registered_persons (role);
CREATE INDEX IF NOT EXISTS idx_persons_visitor ON registered_persons (is_visitor);

-- 3. Visitor log (check-in / check-out tracking)
CREATE TABLE IF NOT EXISTS visitor_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID REFERENCES registered_persons(id) ON DELETE SET NULL,
    identity_id TEXT NOT NULL,
    person_name TEXT NOT NULL,
    action TEXT NOT NULL,                -- check_in | check_out | detected
    feed_id INTEGER,
    zone_name TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_visitor_log_person ON visitor_log (identity_id);
CREATE INDEX IF NOT EXISTS idx_visitor_log_time ON visitor_log (timestamp DESC);

-- 4. Storage buckets (run these separately if needed)
-- In Supabase Dashboard → Storage → New Bucket:
--   - "recordings"  (public: true) — GIF clips
--   - "reports"     (public: true) — PDF incident reports
--   - "threat-images" (public: true) — threat snapshot JPEGs

-- Enable RLS but allow anon read/write for the hackathon
ALTER TABLE security_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE registered_persons ENABLE ROW LEVEL SECURITY;
ALTER TABLE visitor_log ENABLE ROW LEVEL SECURITY;

-- Allow all operations with anon key (hackathon-friendly policy)
CREATE POLICY "Allow all for anon" ON security_incidents FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON registered_persons FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON visitor_log FOR ALL USING (true) WITH CHECK (true);
