-- PostgreSQL schema proposal for Clínica Demo / multi-tenant SaaS.
-- Review and apply through versioned migrations, not manually in production.
-- Tenant isolation: all clinic-owned tables carry clinic_id; use RLS plus backend authorization.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS clinics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  legal_name TEXT NOT NULL,
  display_name TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'America/Argentina/Buenos_Aires',
  status TEXT NOT NULL DEFAULT 'trial' CHECK (status IN ('trial','active','suspended','closed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clinic_settings (
  clinic_id UUID PRIMARY KEY REFERENCES clinics(id) ON DELETE CASCADE,
  public_email TEXT,
  phone TEXT,
  address TEXT,
  website_url TEXT,
  reminder_24h_enabled BOOLEAN NOT NULL DEFAULT true,
  reminder_3h_enabled BOOLEAN NOT NULL DEFAULT true,
  reminder_24h_minutes INTEGER NOT NULL DEFAULT 1440 CHECK (reminder_24h_minutes BETWEEN 60 AND 10080),
  reminder_3h_minutes INTEGER NOT NULL DEFAULT 180 CHECK (reminder_3h_minutes BETWEEN 30 AND 720),
  email_provider TEXT,
  email_from_name TEXT,
  -- Never store plaintext SMTP passwords here. Use secret manager / encrypted secret references.
  smtp_secret_ref TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('platform_admin','clinic_admin','reception','professional','patient')),
  active BOOLEAN NOT NULL DEFAULT true,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (clinic_id, email)
);

CREATE TABLE IF NOT EXISTS patients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  user_id UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL,
  given_names TEXT NOT NULL,
  family_names TEXT NOT NULL,
  dni_encrypted BYTEA,
  dni_lookup_hash BYTEA,
  birth_date DATE,
  sex TEXT,
  email TEXT,
  phone TEXT,
  emergency_contact JSONB NOT NULL DEFAULT '{}'::jsonb,
  consent_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','merged')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (clinic_id, dni_lookup_hash),
  UNIQUE (clinic_id, id)
);

CREATE TABLE IF NOT EXISTS professionals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  display_name TEXT NOT NULL,
  specialty TEXT NOT NULL,
  license_number_encrypted BYTEA,
  email TEXT,
  phone TEXT,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (clinic_id, id)
);

CREATE TABLE IF NOT EXISTS schedules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  professional_id UUID NOT NULL,
  weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  starts_at TIME NOT NULL,
  ends_at TIME NOT NULL,
  appointment_minutes INTEGER NOT NULL DEFAULT 30 CHECK (appointment_minutes BETWEEN 5 AND 240),
  effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
  effective_until DATE,
  active BOOLEAN NOT NULL DEFAULT true,
  FOREIGN KEY (clinic_id, professional_id) REFERENCES professionals(clinic_id, id) ON DELETE CASCADE,
  CHECK (ends_at > starts_at)
);

CREATE TABLE IF NOT EXISTS schedule_exceptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  professional_id UUID NOT NULL,
  exception_date DATE NOT NULL,
  is_closed BOOLEAN NOT NULL DEFAULT true,
  starts_at TIME,
  ends_at TIME,
  reason TEXT,
  FOREIGN KEY (clinic_id, professional_id) REFERENCES professionals(clinic_id, id) ON DELETE CASCADE,
  CHECK ((is_closed = true) OR (starts_at IS NOT NULL AND ends_at > starts_at))
);

CREATE TABLE IF NOT EXISTS appointments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  patient_id UUID NOT NULL,
  professional_id UUID NOT NULL,
  starts_at TIMESTAMPTZ NOT NULL,
  ends_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'booked'
    CHECK (status IN ('pending','booked','checked_in','completed','cancelled','no_show')),
  reason TEXT,
  patient_note TEXT,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  cancelled_at TIMESTAMPTZ,
  cancellation_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (clinic_id, patient_id) REFERENCES patients(clinic_id, id),
  FOREIGN KEY (clinic_id, professional_id) REFERENCES professionals(clinic_id, id),
  CHECK (ends_at > starts_at),
  UNIQUE (clinic_id, id)
);
CREATE INDEX IF NOT EXISTS appointments_clinic_start_idx ON appointments(clinic_id, starts_at);
CREATE INDEX IF NOT EXISTS appointments_patient_idx ON appointments(clinic_id, patient_id, starts_at DESC);
CREATE INDEX IF NOT EXISTS appointments_reminder_idx ON appointments(status, starts_at);

-- Prevent overlapping appointments for the same professional; enable btree_gist in migrations.
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE appointments
  ADD CONSTRAINT appointments_no_overlap
  EXCLUDE USING gist (
    clinic_id WITH =,
    professional_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
  ) WHERE (status IN ('pending','booked','checked_in'));

CREATE TABLE IF NOT EXISTS medical_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  patient_id UUID NOT NULL,
  professional_id UUID NOT NULL,
  appointment_id UUID,
  record_type TEXT NOT NULL CHECK (record_type IN ('consultation','evolution','diagnosis','prescription','procedure','other')),
  summary TEXT NOT NULL,
  clinical_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  signed_at TIMESTAMPTZ,
  created_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (clinic_id, patient_id) REFERENCES patients(clinic_id, id),
  FOREIGN KEY (clinic_id, professional_id) REFERENCES professionals(clinic_id, id),
  FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments(clinic_id, id)
);
CREATE INDEX IF NOT EXISTS medical_records_patient_idx ON medical_records(clinic_id, patient_id, created_at DESC);

CREATE TABLE IF NOT EXISTS studies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  patient_id UUID NOT NULL,
  uploaded_by UUID NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  study_type TEXT,
  storage_key TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
  checksum_sha256 TEXT,
  comments TEXT,
  status TEXT NOT NULL DEFAULT 'pending_review' CHECK (status IN ('pending_review','published','rejected','archived')),
  published_by UUID REFERENCES users(id),
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (clinic_id, patient_id) REFERENCES patients(clinic_id, id),
  UNIQUE (clinic_id, storage_key)
);

CREATE TABLE IF NOT EXISTS notification_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
  appointment_id UUID NOT NULL,
  channel TEXT NOT NULL CHECK (channel IN ('email','whatsapp')),
  kind TEXT NOT NULL CHECK (kind IN ('confirmation','reminder_24h','reminder_3h','cancellation')),
  scheduled_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','sent','failed','cancelled')),
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error_code TEXT,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (clinic_id, appointment_id) REFERENCES appointments(clinic_id, id) ON DELETE CASCADE,
  UNIQUE (appointment_id, channel, kind)
);
CREATE INDEX IF NOT EXISTS notification_jobs_due_idx ON notification_jobs(status, scheduled_at);

CREATE TABLE IF NOT EXISTS audit_events (
  id BIGSERIAL PRIMARY KEY,
  clinic_id UUID REFERENCES clinics(id) ON DELETE SET NULL,
  actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  request_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_events_clinic_idx ON audit_events(clinic_id, created_at DESC);

-- RLS: set app.current_clinic_id on every transaction after validating the authenticated user's membership.
-- Example backend transaction: SET LOCAL app.current_clinic_id = '<validated UUID>';
ALTER TABLE clinic_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE professionals ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE schedule_exceptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE medical_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE studies ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY clinic_settings_tenant_isolation ON clinic_settings
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY patients_tenant_isolation ON patients
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY professionals_tenant_isolation ON professionals
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY schedules_tenant_isolation ON schedules
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY schedule_exceptions_tenant_isolation ON schedule_exceptions
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY appointments_tenant_isolation ON appointments
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY medical_records_tenant_isolation ON medical_records
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY studies_tenant_isolation ON studies
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY notification_jobs_tenant_isolation ON notification_jobs
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
CREATE POLICY audit_events_tenant_isolation ON audit_events
 USING (clinic_id = current_setting('app.current_clinic_id', true)::uuid)
 WITH CHECK (clinic_id = current_setting('app.current_clinic_id', true)::uuid);
