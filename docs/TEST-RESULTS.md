# Test results

**Verification date:** 9 November 2026. **Scope:** local synthetic demonstration. No real external messages were sent.

## Executed automated suite

`python -m pytest -q --junitxml=evidence/unit-tests.xml` passed **49 tests**, with zero failures. The checked-in JUnit XML is the machine-readable record. One upstream Starlette/AnyIO deprecation warning is recorded; it is not a failing assertion.

| Required scenario | Executed evidence |
|---|---|
| 1. Valid lead | Normalised email/UK phone, category, pending draft; real n8n intake |
| 2. Missing required fields | Missing name retained for review; missing event rejected |
| 3. Invalid email | Review issue, no eligible draft |
| 4. Repeated webhook event | Same lead ID, duplicate true, one lead row; real n8n repeat |
| 5. Contact across sources | Distinct enquiries with same contact ID; real n8n cross-source case |
| 6. Conflicting identities | Email/phone collision flagged; no silent merge |
| 7. No permission to reply | No draft/outbox; non-Boolean permission rejected; real runtime case |
| 8. Approval granted | One queued outbox for exact draft; real simulated delivery |
| 9. Approval rejected | No claimable work; opposite later decision refused; browser rejection |
| 10. Repeated approval | Idempotent result and one outbox row; real runtime repeat |
| 11. Temporary API failure | 503 → retry → 200; stored backoff respected in real n8n |
| 12. Rate limiting | 429 Retry-After → delayed 200; real n8n delivery |
| 13. Permanent API failure | 400 → dead, no automatic retry; real runtime case |
| 14. Interrupted execution | Provider-accepted-before-ack crash, lease expiry, receipt replay, stale-worker refusal |
| 15. Concurrent same lead | 16 concurrent ingests/approvals/claims; one lead/outbox/claim |
| 16. Duplicate outbound prevention | 16 concurrent simulator calls → same receipt; one first acceptance |
| 17. Unauthorized API | Seven protected route cases plus wrong-role tokens and real n8n webhook auth |
| 18. Persistence after restart | Reopened SQLite state and actual service-process restart preserve identity/receipt |
| 19. Manual review/correction | Invalid email corrected, manual routing, new draft revision, stale-draft rejection |
| 20. End-to-end processing | HTTP intake → qualification → approval → delivery → committed state; actual n8n run |

Additional tests exercise retry exhaustion, interrupted intake resumption, content deduplication under new events, all routing categories, strict permission types, approved-recipient immutability, role separation, oversized input, text-only UI rendering, simulator approval checks, final-attempt receipt reconciliation, explicit dead-letter redrive and database uniqueness constraints.

## Genuine n8n runtime suite

`python scripts/verify_n8n.py` passed **14 observed scenarios**. It called real authenticated n8n webhooks and waited for actual five-second Schedule Trigger executions. n8n was not mocked. It verified intake, qualification/draft, duplicate delivery, shared contact, no pre-approval delivery, approval idempotency, 503 recovery, 429 recovery, permanent failure, review/rejection, permission blocking, interrupted intake resumption, a deliberate n8n node failure, webhook authentication and an independent SQL invariant audit. Some related assertions are grouped in one reported scenario; the JSON lists the exact 14 entries.

Machine-readable results: [n8n-integration.json](../evidence/n8n-integration.json).

All four imported workflows were opened in the real n8n editor and inspected. The intake-node credential mismatch discovered during the first runtime attempt was corrected; the successful suite ran afterward. A later repeat exposed an intentionally deduplicated review fixture because that fixture omitted its run-specific reference. The fixture was corrected and the final complete suite passed. Failed attempts are not reported as passing runs.

## Actual process interruption

`scripts/verify_process_restart.py` persisted an approved simulated receipt, terminated the running application process before marking the outbox successful, and started a replacement process on the same database. The real n8n recovery scheduler expired the lease and dispatched the stable key again.

Observed result: attempt outcomes `interrupted, sent`; one provider receipt for the outbox key; stale worker HTTP 409; original event remained a duplicate after restart. The evidence records the actual terminated/replacement PIDs and identifiers. The verifier was rerun against the final connection-management implementation.

Machine-readable results: [process-restart.json](../evidence/process-restart.json).

## Browser verification

Chrome was used to unlock the actual operations console, search for an invalid enquiry, inspect its original message, correct its email, select Other and regenerate a draft. The browser then selected an atomic 503 demonstration scenario and approved the draft; the real scheduler produced 503/retry followed by 200/sent. A different draft was rejected in the browser. The original source payload and processing history remained visible.

The final browser checklist is recorded in [browser-qa.json](../evidence/browser-qa.json). Screenshots include the actual n8n canvases, the approval view and recovered delivery. The attempted mobile viewport override did not change the measured viewport; mobile-width behaviour is not claimed as tested.

## Environment and limits

Windows; Python 3.10.11; Node.js 24.14.0; npm 11.9.0; n8n 2.46.7. Python dependencies and n8n transitive dependencies are locked in the repository. SQLite business state and n8n state were persisted locally. The initial npm parent-folder resolution was corrected to an isolated workspace runtime, and the added parent dependency was removed.

Docker was absent from the original Windows command discovery. In a subsequent approved publication step, the supplied Compose stack was built and started on an Ubuntu GitHub-hosted runner. All 49 automated tests and all 14 real n8n integration scenarios passed there, including an SQL invariant audit executed inside the application container. The initializer, official pinned n8n image and named-volume configuration were exercised. [Public CI run](https://github.com/ANKOHR/intake-rescue/actions/runs/42654424357) · [Container evidence](../evidence/docker/verification.json).

The source repository and reviewed two-minute recording have been published as portfolio material. The application itself remains local. No real-account integration, external email delivery, load benchmark, security certification or disaster-recovery restore drill is claimed.

The passing evidence supports the demonstrated local behaviours and documented simulator contract. It does not establish operational guarantees for an unimplemented real provider or a future production deployment.
