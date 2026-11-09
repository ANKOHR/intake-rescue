# Two-minute technical demonstration

## Prepare before recording

Start the local app and n8n. Open the intake canvas and console, unlock with the local admin token, and keep tokens/passwords out of the recording. Close n8n's optional Production Checklist overlay and use Zoom to Fit. Have the delivery canvas available in another tab if helpful.

Open a terminal in the repository with these commands ready; no secret appears in their command lines:

```powershell
.venv\Scripts\python scripts\submit_sample.py
.venv\Scripts\python scripts\submit_sample.py
```

For the cleanest first recording, use fresh disposable synthetic state. If the default sample already exists, make a prepared copy with a unique event ID **and** a unique reference in the message; submit that same copy twice. `--new-event` is useful for new demonstrations, but running it twice creates two different records, so it is not the duplicate demonstration.

Check that the delivery/recovery schedules are locally published. The default schedule ticks every five seconds; a simulated 503 succeeds on a later tick after the five-second backoff. Practise the timing once. The existing evidence files support a deeper review outside the two-minute recording.

## Recording timeline

| Time | Screen and action | Narration / proof |
|---|---|---|
| 0:00–0:15 | Genuine n8n intake editor, all nodes visible | “This is Intake Rescue, a local Sparrow Works demonstration. n8n separates authenticated intake, persistence, duplicate handling, qualification and drafting.” |
| 0:15–0:30 | Submit the first sample; show its receipt and console row | “The enquiry is validated and stored with source/event identifiers and a correlation ID. A draft is awaiting a person. No email account is connected.” |
| 0:30–0:45 | Submit the identical payload again | “The second delivery returns the same lead ID with duplicate true. The enquiry count stays the same; the duplicate count increases.” |
| 0:45–1:05 | Select the enquiry; inspect original, recipient and draft | “Approval is attached to this draft revision. A correction would invalidate a pending draft; a rejected draft cannot be sent.” Choose **Temporary failure, then recover**. |
| 1:05–1:20 | Click **Approve simulated reply**; show delivery canvas briefly | “Approval creates one outbox job atomically. n8n claims an exclusive lease and calls the local delivery adapter.” |
| 1:20–1:40 | Console delivery log shows 503/retry, then 200/sent | “The simulated provider fails once. The retry runs after its stored backoff and uses the same idempotency key. The history records both attempts and one simulated receipt.” |
| 1:40–1:55 | Show recovered enquiry timeline; optionally show error/recovery canvas | “If a process stops, the recovery workflow resumes durable stages and expired leases. Our process-kill test accepted a message before the app died, then recovered with one receipt.” |
| 1:55–2:00 | Test report / evidence folder | “49 automated tests, 14 real n8n scenarios and the actual restart evidence are included. This is a synthetic demonstration, not a claimed client result.” |

If an unexpected issue appears, stop the recording and investigate it. Do not edit a failed run into a claimed successful demonstration. Do not click the n8n test-listener button for the production webhook demo; the sample script uses `/webhook/`, which requires a locally activated workflow.

## Optional contractor follow-up

Show the database uniqueness constraints, stale-draft test, concurrent claims test and process-restart report. Explain the external-provider exactly-once limitation. To demonstrate review, submit `review-enquiry.json`, correct its email and select Other; to demonstrate permission blocking, submit `no-permission.json`. Neither needs any real external account.
