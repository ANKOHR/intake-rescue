# Recorded demonstration

[Watch the two-minute MP4](Intake-Rescue-Two-Minute-Demo.mp4).

This is a silent, captioned edit of an actual live browser recording on 9 November 2026. The source capture lasted approximately 3 minutes 50 seconds. The two-minute version uses chronological excerpts, adjusts section timing for pacing and holds the delivery canvas for explanation. It does not claim real-time performance. Captions identify it throughout as an edited local demonstration with no customer mailbox connected.

The recording shows a genuine n8n intake canvas; a successful authenticated synthetic webhook; repeat delivery returning the same lead ID; explicit approval of the draft through the operations console; a recorded 503 followed by 200 using the same outbox; the n8n delivery/retry canvas; and a final independent receipt count of one.

The visible submission panel is a disposable recording aid, not a connected customer form. Its two buttons send the same fixed synthetic payload through the actual n8n production webhook. Authentication stays server-side. It has no approval or email-sending control. The separately protected operations console records the approval. Run `python scripts/demo_panel.py` from the repository to reproduce that panel on loopback port 8899 after starting the main services. The reproduction fixture uses a stable synthetic contact and fresh event/reference for each process run.

[Recording evidence](recording-evidence.json) records the observed result. [Edit decisions](edit-decision-list.json) document the selected source intervals. The MP4 was fully decoded without errors and its key scenes were visually reviewed for content and accidental credential exposure. Credentials were entered before capture began; the recording does not show authentication fields, a real mailbox or real customer information.

The simulator's receipt guarantee does not establish a real email provider's guarantees. This is a demonstration asset, not a client deployment, production security assessment or claimed financial result.
