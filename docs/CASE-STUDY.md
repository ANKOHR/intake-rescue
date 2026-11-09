# Intake Rescue: dependable enquiry handling with n8n

**Sparrow Works · Demonstration project · Synthetic data only · November 2026**

## The problem

A form submission is only the start of an enquiry workflow. The same event may arrive twice. A contact may use a different form. A provider can accept a message just before the workflow loses its response. An incomplete record can look ready to send when it still needs a person to check it.

Intake Rescue demonstrates how Sparrow Works approaches those failure points: a visible n8n workflow, clear database guarantees, useful exception queues and a human approval before follow-up.

## What was built

Four native n8n workflows handle intake, interrupted-stage recovery, approved delivery and redacted execution errors. A Python service and SQLite database maintain identities, idempotency, draft versions and leased delivery jobs. A lightweight local console lets an operator read the original enquiry, correct information, approve or reject a draft and inspect the history.

The default delivery adapter calls a local HTTP simulator. It records receipts rather than sending email. No real customer information, mailbox or paid service is involved.

## Engineering decisions

**Keep orchestration visible.** The intake canvas separates the source envelope, persistence, duplicate branch, qualification and draft generation. Recovery and delivery have their own canvases. A reviewer can see the workflow boundaries without tracing a single opaque request.

**Use transactions for the guarantees that matter.** Source/event uniqueness, contact identifiers, draft revisions, approval decisions and outbox creation live in SQLite. Concurrency tests exercise those constraints. A repeated approval cannot create a second outbound job.

**Review uncertainty.** Deterministic rules route straightforward enquiries into booking, sales, support or recruitment. Missing details, identity conflicts and ambiguous categories require human review. Unknown enquiries are not given a confident artificial classification.

**Bind approval to what was reviewed.** A decision identifies an exact draft revision. Corrections supersede earlier pending drafts; old approval requests are rejected. Source reply permission is required and cannot be manufactured through a correction form.

**Design around interrupted work.** n8n resumes persisted intake stages. Delivery uses expiring leases and fencing tokens. Retryable failures receive bounded backoff, permanent failures enter a dead-letter queue, and provider calls reuse a stable idempotency key.

## Demonstrated evidence

- **49 passing automated tests**, covering all 20 required scenarios plus additional permission, concurrency, revision and retry checks.
- **14 passing real n8n runtime scenarios**, submitted through actual HTTP webhooks and processed by actual n8n schedules.
- **An actual process termination after simulated acceptance.** The application restarted, n8n recovered its expired lease, and the provider retained one receipt. The stale worker's token was refused.
- **Browser-exercised operations.** In Chrome, an invalid enquiry was corrected, a new draft generated, a simulated 503 scenario approved and recovered, and a separate draft rejected.
- **Independent SQL checks** found no unapproved simulator receipts and no duplicated outbox groupings in the verified state.
- **All four canvases opened in the genuine n8n editor.** Screenshots and structured results are included in the repository.
- **Docker Compose independently exercised on Linux.** The supplied stack started on a GitHub-hosted Ubuntu runner and passed the same 49 automated tests and 14 genuine n8n scenarios. [Public verification run](https://github.com/ANKOHR/intake-rescue/actions/runs/42654424357).

The development checks exposed a misassigned intake-node credential. It was corrected and the real runtime suite passed afterward. That is why this portfolio includes operational evidence as well as source files.

## What this shows a prospective client

Sparrow Works can implement a practical n8n workflow with data validation, database-backed duplicate controls, human review, approval gates, retry handling and an understandable handover. The system demonstrates the engineering habits behind a maintainable automation engagement.

It does not claim a measured revenue increase, hours saved or a customer deployment. Both the original Windows/npm installation and the subsequent Docker Compose installation have runtime evidence. External exactly-once delivery remains dependent on a real provider's idempotency and reconciliation contract.

Sparrow Works' previously described paid Webflow, Zapier and Airtable application workflow is separate experience. This new n8n system was not deployed for that client.

## Evidence links

[Test report](TEST-RESULTS.md) · [Architecture](ARCHITECTURE.md) · [Failure model](SECURITY-AND-FAILURES.md) · [Runtime results](../evidence/n8n-integration.json) · [Process restart](../evidence/process-restart.json) · [n8n editor](../evidence/n8n-intake-editor.jpg) · [Browser approval](../evidence/dashboard-approval.jpg) · [Recovered delivery](../evidence/dashboard-recovered.jpg)
