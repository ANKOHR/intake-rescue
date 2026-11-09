# Known limitations and future improvements

This is a verified local demonstration, not a claim of production readiness or a paid client deployment.

- Docker is absent on the original Windows machine. The supplied Docker Compose stack was subsequently built, started and exercised on a GitHub-hosted Ubuntu runner, with 49 tests and 14 genuine n8n scenarios passing. The original Windows runtime evidence remains separate. This is a tested local container deployment path, not a production hosting or availability guarantee.
- Multiple sources share an authenticated JSON webhook contract. Native vendor-specific adapters and webhook-signature verification are not included.
- SQLite suits this local workload. No load benchmark, distributed workers, high availability, network filesystem support or production PostgreSQL migration is claimed.
- Email/phone matching is conservative and UK-oriented. Shared inboxes, recycled phone numbers and legitimate identity changes need a client-specific reconciliation policy. The console resolves conflicts by correcting the lead; it does not offer a broad contact-merge tool.
- Identical normalised content from the same source is deduplicated for its retention lifetime. Real businesses may require a time window, explicit genuine-repeat override and retention policy.
- Keyword rules are intentionally narrow. They can miss synonyms and do not provide semantic understanding. Unknown/multiple categories require human review. AI enrichment is an optional future feature; it is not required or configured.
- Source reply permission is an input flag, not a full consent-management platform. Approved records are immutable through this API; there is no post-approval cancellation/revocation workflow. Establish that requirement before real communications.
- The admin token is shared, `X-Operator` is self-declared, and no session expiry/role UI is provided. Per-person authentication, verified actors and source token rotation belong in a client deployment.
- There is no real email adapter. The simulator's durable idempotency is stronger than some email providers' contracts. Exactly-once external delivery is not promised.
- Retry-After supports numeric seconds, not HTTP-date values. Backoff is capped and deterministic without jitter. One job is claimed per n8n five-second tick. Manual redrives are explicit new budgets; automatic retries remain bounded.
- n8n intake failures return a generic webhook 500 instead of mapping the underlying 409/422. The business database remains authoritative and duplicate-safe. More precise source-facing error mapping is a useful next improvement.
- The error workflow cannot persist to an unavailable application service. n8n keeps execution metadata, but no external alerting/incident channel is connected. Historical failed executions are cumulative and not individually resolved in the console.
- The dashboard displays the latest 200 leads and 50 attempts/events; it is not a paginated CRM. It does not allow custom draft-body editing. Reject/correct/regenerate creates a new reviewable revision.
- Desktop Chrome interaction and visual inspection were performed. Responsive CSS is included, but the browser viewport override did not change the observed Chrome viewport during verification; a real mobile-width test is **not** counted as passed.
- No formal accessibility audit, penetration test, browser-matrix test, full dependency vulnerability audit, backup restoration drill or performance SLA was completed. The Python test suite reports one upstream Starlette/AnyIO deprecation warning; it does not cause a failure.
- There is one initial idempotent schema migration; future migrations need explicit upgrade/rollback tests. The simulator shares the application database, so a real provider's independently retained state is a further boundary to test.

Priority next steps for an authorised real implementation: agree identity/repeat/permission rules; choose the actual delivery provider and its reconciliation contract; add per-person access and monitored backups; perform a backup restoration drill; exercise the complete client-specific source-to-provider flow with the agreed data policy.
