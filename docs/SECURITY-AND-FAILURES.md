# Security and failure modes

## Authorization and privacy

Default services are loopback-only. Four independent random tokens protect intake, worker, admin and simulator routes. Startup fails if any is shorter than 24 characters or if tokens are reused across roles. Tokens are compared with constant-time comparison, passed in headers and excluded from source exports. n8n credentials are imported through a short-lived private runtime file, then stored using n8n's encryption key. `.env`, databases and runtime directories are excluded from Git and the archive.

The dashboard stores its token only in tab memory and clears data on lock. It uses no analytics, third-party fonts or CDN scripts. Content Security Policy, no-store responses, no-referrer and text-only rendering reduce accidental disclosure and script injection. API mutations use Authorization headers rather than ambient browser cookies. There is no CORS opt-in. This is a single-operator demonstration: `X-Operator` is an audit label, and anyone holding the admin token can act as an operator.

The application disables access logs. Its history records state, actor, IDs, category and safe error codes, not full message bodies or provider response text. Original synthetic enquiries are stored in lead records and exposed only through protected APIs. n8n workflow execution payload retention is disabled in exports. Its own execution metadata/editor still exists. Platform stderr may include operational stack traces; keep it private. A verification scan found no configured IR tokens or synthetic email addresses in the captured local n8n log. Diagnostic reporting and template/version notifications are disabled.

HTTP request bodies are limited to 32 KiB. Normalised field limits and types are checked server-side. Credentials do not appear in screenshots or packaged evidence. No real customer information was used. Backups of an eventual real deployment would contain personal data and need a client-approved retention/access policy; this demonstration makes no compliance certification.

## Approval invariant

An approval identifies a frozen draft ID and current revision. Approval, decision record and unique outbox creation happen in one transaction. Repeated identical decisions do not create additional outbox rows. Rejected, superseded, incomplete and no-permission records cannot send. Corrections cannot grant permission and cannot change an approved recipient/content. Delivery checks approval again; even the simulator rejects an arbitrary unapproved payload.

There is no real email adapter. The only delivery URL is a checked loopback `/simulator/send` endpoint, redirects are disabled, and the recipient/subject/body are written to SQLite. A local simulated approval is not authorization to connect a real account or transmit a customer message.

## Failure handling

| Failure | Persisted response | Operator action |
|---|---|---|
| Same source/event repeated | Original lead; duplicate event | None unless the producer is unexpectedly retrying |
| Same source/event with changed payload | 409 in service; generic n8n webhook failure; error ledger | Repair producer identity semantics, then resubmit intentionally |
| Missing source/event or invalid types | Reject before business persistence | Correct producer payload |
| Invalid contact details / conflicting identity | Review issues, no eligible draft | Correct and explicitly route; never silently merge |
| Ambiguous or unmatched category | Other + review | Select category after reading enquiry |
| No reply permission | `no_permission`, no draft/outbox | Handle through an appropriately authorised manual process |
| API stops after intake persistence | `received`/`qualified` remains durable | n8n recovery scheduler resumes stages |
| n8n stops | Durable business state remains; schedules stop | Restart n8n using the same state and encryption key |
| Provider 503/500 or transport timeout | Retry due time + safe error + attempt row | Wait for backoff; inspect repeated failures |
| Provider 429 | Retry no earlier than numeric Retry-After or exponential delay | Wait; avoid manual rapid retries |
| Permanent 4xx | Dead-letter immediately | Inspect fault, reconcile receipt or explicitly redrive same approved draft |
| Worker dies with an active lease | Expired lease → interrupted attempt → retry/dead | Scheduler recovers; stale tokens cannot commit |
| Provider accepts, worker dies before acknowledgement | Receipt survives; outbox remains processing | Recovered call uses same key and gets same receipt |
| Fourth attempt dies after acceptance | Dead-letter until receipt reconciliation | Click reconcile; do not create a second send |
| API unavailable to error workflow | Redacted ledger cannot be written | Inspect private n8n failed execution metadata; the ledger is not a durable alert transport |
| Disk full / DB corruption / lost machine | No in-process guarantee | Stop processing; restore a verified backup; inspect receipt/provider reconciliation |

Default delivery attempts are bounded at four per automatic budget. An explicit admin redrive creates a new budget, retains history and keeps the same idempotency key. The per-budget attempt counter restarts; timestamps and audit events distinguish redrives. No automatic path endlessly resets a failed record.

## Exactly-once limits

SQLite can enforce exactly one local outbox row and one local simulated receipt per key. That does **not** prove exactly-once delivery through an arbitrary external provider. A provider may accept a message and lose its response. Without a durable, sufficiently long-lived provider idempotency contract or a reliable status lookup, retrying can send twice and refusing to retry can lose a message.

This simulator intentionally implements durable idempotency and payload binding. The actual process-kill test demonstrates that contract. Before adding a real adapter, establish its idempotency retention, timeout semantics, receipt lookup and reconciliation process. Mark ambiguous outcomes for review when those guarantees are unavailable. Do not reuse these simulator results as evidence that a real email provider has equivalent behaviour.

## Public deployment boundary

Public hosting is outside this build. Before an authorised client deployment, add TLS, per-person authentication and audit identity, source authentication/rotation, appropriate rate limiting, monitored backups, retention/deletion, workflow access controls and operational alerting. n8n environment access is enabled so trusted HTTP nodes can read `IR_API_URL`; workflow editors must be trusted administrators. The local configuration is not a multi-tenant security boundary.
