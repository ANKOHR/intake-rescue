# Operational handover

## Start and stop

Follow the README to install the pinned Python and n8n dependencies. Start `scripts/serve.py` and `scripts/n8n_local.py start` in separate terminals; stop each with Ctrl+C. Keep `.env`, `.runtime/.n8n` and `data/intake.db` together across restarts. An unexpected stop is recoverable; deleting state or changing the encryption key is a different operation.

For Compose, use `docker compose up -d` and `docker compose down`. Volumes persist unless explicitly removed. To reimport changed workflows, stop the n8n service, run `docker compose run --rm n8n-init`, then start n8n again. Do not run concurrent initialization against an actively edited instance. Fixed IDs mean imports overwrite those four demonstration workflows.

The originally verified Windows instance used a separately isolated dependency folder under the supervising task's `work/` directory and business state under this repository. The source archive excludes both environments. `scripts/install-n8n.ps1` creates a fresh repository-local `.runtime` using the included lockfile. No global npm install is required.

## Reviewing the console

1. Unlock with the local admin token and your operator label. Keep the token private.
2. Review **Pending reviews**. Read the original source payload and issues. Correct details and select a routing category where rules are uncertain.
3. Review **Pending approvals**. Check recipient, body, revision and source permission. Click approve or reject. Rejected drafts never enter the outbox.
4. Monitor **Queued follow-ups** and the attempt log. Normal delivery runs on the next n8n tick. Retry history shows 429/5xx and interruptions.
5. Review **Failed executions**. This counts current dead outbox rows plus cumulative redacted n8n failures; a deliberate failed demonstration remains part of the latter count. It is not an uptime metric.

Selecting a lead shows its immutable original payload, current normalised details, draft, processing timeline, outbox and previous enquiries sharing the contact. Search covers name/email/source; the inbox shows the latest 200 records. The overview polls every five seconds. Selected details update on state change; Refresh data also reloads them. Open correction forms are not repeatedly overwritten by routine polling of an unchanged state.

Metrics are operational counts with explicit scope: **Total enquiries** excludes duplicate deliveries/submission aliases; **Qualified leads** counts records with a category and no outstanding issues; **Duplicate submissions** counts observed suppressed deliveries, including repeated webhook attempts; **Retry history** counts retry/interrupted attempts; **Simulated deliveries** counts provider receipts.

## Dead-letter procedure

Open the failed enquiry and read the attempt history. Determine whether the local simulator has already committed a receipt. **Reconcile simulator receipt** marks the outbox sent only when that receipt exists. If no receipt exists, reconciliation fails safely. Correct the synthetic fault plan if needed, then **Retry approved draft (new 4-attempt budget)** explicitly requeues the same frozen approved draft and stable key. It cannot revise the recipient or approve a rejected draft.

For a real provider, first reconcile against its supported status lookup; do not assume the absence of a local receipt proves non-delivery. A real adapter is not included.

## Repeatable demonstration

Run `submit_sample.py valid-enquiry.json --new-event` to create a distinct enquiry. Run the exact same unmodified sample twice to prove duplicate handling. Select the atomic **Simulated delivery scenario** before approval to demonstrate 503/429/400; setting a fault afterward can race the scheduler. The post-approval fault control exists for deliberate operator experiments only.

The complete automated n8n verifier is `scripts/verify_n8n.py`. It creates its own uniquely prefixed data and records a JSON result. It also deliberately fails an intake node to exercise the error workflow. This creates an expected historical failure count.

`verify_process_restart.py <PID>` deliberately terminates the designated app process after a simulated acceptance. Confirm the PID belongs to your disposable demonstration app before running it. It restarts that app, leaves its replacement running, records `.runtime/app.pid`, and verifies n8n recovery with a single receipt. This is a verification tool, not a routine restart mechanism.

## Backup and restore

For a consistent application snapshot while the app is running, use SQLite's backup API through a local operator script, rather than copying only the main `.db` while WAL writes are active:

```python
import sqlite3
with sqlite3.connect('data/intake.db') as source:
    with sqlite3.connect('data/intake-backup.db') as target:
        source.backup(target)
```

Store backups outside a public repository. Stop n8n before copying its whole state volume/directory, including its encryption configuration. Preserve `.env` securely. Restore into an isolated local instance first, verify schema version and record counts, and replay an existing source/event to confirm duplicate suppression. The build tested persistence/recovery after restart; it did not perform a disaster-recovery restore drill.

## Troubleshooting

- **401:** check role and header; admin is not a worker credential. Tokens must match the local n8n credential import. After rotating tokens, stop n8n, rerun the import, restart it and unlock the console again.
- **Generic webhook 500:** inspect the redacted failure node and the source identifiers. The service's precise 409/422 is intentionally not exposed through the current n8n failure response.
- **No progress:** check `/health`, then n8n is running and the recovery/delivery workflows are published locally. A successful static page alone does not prove worker health.
- **Queued beyond lease/backoff:** inspect `next_at`, attempts and n8n execution metadata. Allow the 5-second scheduler granularity.
- **SQLite locked:** keep one local database host, short transactions and normal storage. Do not move it to a network share. Capacity beyond this demo needs measurement and likely PostgreSQL.
- **Port already in use:** stop your existing demonstration processes or intentionally change ports, `IR_API_URL`, simulator URL and webhook base together. Do not terminate unrelated services.
- **n8n editor data absent:** execution payload retention is disabled. Business processing evidence is in the protected console and SQLite history.

## Shutdown and ownership

No scheduler was installed in Windows Task Scheduler and no future Codex automation was created. Running n8n schedules operate only while the local n8n process runs. No client account, public tunnel, external mailbox or paid service was connected. The next commercial step is a separately authorised client-specific discovery and implementation, using this demonstration as engineering evidence.
