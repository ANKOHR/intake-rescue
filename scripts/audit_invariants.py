"""Read-only SQL audit; also executable inside the app container for independent CI checks."""
import json
import os
import sqlite3

path=os.environ.get('IR_DATABASE','data/intake.db')
with sqlite3.connect(path) as c:
    unapproved=c.execute("SELECT COUNT(*) FROM provider_receipts r LEFT JOIN outbox o ON o.id=r.idempotency_key LEFT JOIN approvals a ON a.draft_id=o.draft_id AND a.decision='approve' WHERE a.draft_id IS NULL").fetchone()[0]
    duplicates=c.execute('SELECT COUNT(*) FROM (SELECT draft_id FROM outbox GROUP BY draft_id HAVING COUNT(*)>1)').fetchone()[0]
    receipts=c.execute('SELECT COUNT(*) FROM provider_receipts').fetchone()[0]
assert unapproved==0 and duplicates==0
print(json.dumps({'unapproved_receipts':unapproved,'duplicate_outbox_groups':duplicates,'simulated_receipts':receipts}))
