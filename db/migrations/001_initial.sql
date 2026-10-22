CREATE TABLE IF NOT EXISTS app_lock (id integer PRIMARY KEY CHECK (id = 1), panel_version integer NOT NULL DEFAULT 1);
INSERT INTO app_lock (id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS people (
  id text PRIMARY KEY, name text NOT NULL, title text NOT NULL DEFAULT 'Student',
  roles jsonb NOT NULL DEFAULT '["student"]', active boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS identities (
  issuer text NOT NULL, subject text NOT NULL, person_id text NOT NULL UNIQUE REFERENCES people(id),
  PRIMARY KEY (issuer, subject)
);
CREATE TABLE IF NOT EXISTS panel_members (person_id text PRIMARY KEY REFERENCES people(id));
CREATE TABLE IF NOT EXISTS courses (
  id text PRIMARY KEY, code text NOT NULL UNIQUE, name text NOT NULL,
  capacity integer NOT NULL CHECK (capacity BETWEEN 1 AND 10000), version integer NOT NULL DEFAULT 1
);
CREATE SEQUENCE IF NOT EXISTS waitlist_order;
CREATE TABLE IF NOT EXISTS memberships (
  course_id text NOT NULL REFERENCES courses(id), person_id text NOT NULL REFERENCES people(id),
  status text NOT NULL CHECK (status IN ('enrolled', 'waiting')),
  sort_order bigint NOT NULL DEFAULT nextval('waitlist_order'),
  PRIMARY KEY (course_id, person_id)
);
CREATE TABLE IF NOT EXISTS exception_requests (
  id text PRIMARY KEY, kind text NOT NULL CHECK (kind IN ('force', 'jump', 'remove', 'panel')),
  requester_id text NOT NULL REFERENCES people(id), data jsonb NOT NULL,
  reason text NOT NULL, public_reason text NOT NULL, panel_snapshot jsonb NOT NULL,
  panel_version integer NOT NULL, course_version integer,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','denied','stale')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS request_approvals (
  request_id text NOT NULL REFERENCES exception_requests(id), approver_id text NOT NULL REFERENCES people(id),
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (request_id, approver_id)
);
CREATE TABLE IF NOT EXISTS audit_events (
  id bigserial PRIMARY KEY, actor_id text REFERENCES people(id), kind text NOT NULL,
  summary text NOT NULL, request_id text REFERENCES exception_requests(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS one_execution_per_request ON audit_events(request_id) WHERE kind = 'exception.applied';
CREATE TABLE IF NOT EXISTS mutation_keys (
  person_id text NOT NULL REFERENCES people(id), route text NOT NULL, key text NOT NULL,
  fingerprint text NOT NULL, response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (person_id, route, key)
);
CREATE TABLE IF NOT EXISTS dpop_replays (key text PRIMARY KEY, expires_at bigint NOT NULL);
