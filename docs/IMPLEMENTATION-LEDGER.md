# Implementation commitments

| Phase | Intended result | Required evidence | Status |
|---|---|---|---|
| Architecture | Local n8n, transactional SQLite service, simulator, review UI | Environment inspection and documented boundaries | Complete |
| Core | Validate, normalise, deduplicate, match identities, persist, classify | Repeatable behavioural and concurrency tests | Tests passing |
| Orchestration | Native n8n intake, recovery, delivery and error workflows | 14 genuine webhook/scheduler runtime scenarios; all four canvases inspected | Complete |
| Interface | Protected console, original payload, correction, decisions, history | Chrome correction/approval/rejection and recovered delivery | Complete for desktop; mobile not verified |
| Verification | Required 20 scenarios, fault recovery, approval invariants | 49 passing tests, runtime report, actual process-kill recovery, database audit | Complete for local demonstration |
| Portfolio | Reproducible source, handover, case study, demonstration, ZIP | Deliverable/link/credential checks, CRC-tested ZIP and SHA-256 manifest | Complete |

Boundary: local services and synthetic data only. Public hosting, real accounts, external messages and publication require separate authorization.
