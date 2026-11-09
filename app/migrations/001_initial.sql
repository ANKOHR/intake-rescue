CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS contacts(
 id TEXT PRIMARY KEY, email TEXT UNIQUE, phone TEXT UNIQUE, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS leads(
 id TEXT PRIMARY KEY, source TEXT NOT NULL, event_id TEXT NOT NULL, correlation_id TEXT NOT NULL,
 payload_hash TEXT NOT NULL, fingerprint TEXT NOT NULL, original TEXT NOT NULL,
 name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, message TEXT NOT NULL,
 permission INTEGER NOT NULL CHECK(permission IN (0,1)), contact_id TEXT REFERENCES contacts(id),
 category TEXT, issues TEXT NOT NULL DEFAULT '[]', state TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL,
 UNIQUE(source,event_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS lead_fingerprint ON leads(fingerprint);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, lead_id TEXT REFERENCES leads(id), correlation_id TEXT NOT NULL,
 kind TEXT NOT NULL, detail TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS duplicates(
 source TEXT NOT NULL, event_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
 lead_id TEXT NOT NULL REFERENCES leads(id), created_at REAL NOT NULL,
 PRIMARY KEY(source,event_id)
);
CREATE TABLE IF NOT EXISTS drafts(
 id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id), revision INTEGER NOT NULL,
 recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('pending','approved','rejected','superseded')),
 UNIQUE(lead_id,revision)
);
CREATE TABLE IF NOT EXISTS approvals(
 draft_id TEXT PRIMARY KEY REFERENCES drafts(id), decision TEXT NOT NULL,
 actor TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox(
 id TEXT PRIMARY KEY, draft_id TEXT NOT NULL UNIQUE REFERENCES drafts(id),
 state TEXT NOT NULL CHECK(state IN ('queued','processing','retry','sent','dead')),
 attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL, lease_until REAL,
 lease_token TEXT, last_error TEXT, created_at REAL NOT NULL, sent_at REAL
);
CREATE TABLE IF NOT EXISTS delivery_attempts(
 id INTEGER PRIMARY KEY, outbox_id TEXT NOT NULL REFERENCES outbox(id),
 attempt INTEGER NOT NULL, token TEXT NOT NULL UNIQUE, outcome TEXT NOT NULL,
 status INTEGER, next_at REAL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_faults(
 outbox_id TEXT PRIMARY KEY REFERENCES outbox(id), statuses TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_receipts(
 idempotency_key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, receipt_id TEXT NOT NULL,
 recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS orchestration_failures(
 id INTEGER PRIMARY KEY, workflow_id TEXT NOT NULL, execution_id TEXT NOT NULL,
 node TEXT NOT NULL, created_at REAL NOT NULL
);
INSERT OR IGNORE INTO schema_migrations(version,applied_at) VALUES(1,unixepoch());
