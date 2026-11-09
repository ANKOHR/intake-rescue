"""Transactional business rules. n8n owns orchestration; SQLite owns invariants."""
import hashlib
import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def uid():
    return str(uuid.uuid4())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Problem(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class ClosingConnection(sqlite3.Connection):
    """sqlite3's normal context manager commits but doesn't close the connection."""
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def normalize(p):
    """Conservative UK default; retain invalid values for operator correction."""
    def text(key):
        v = p.get(key, '')
        return v.strip() if isinstance(v, str) else ''
    phone = re.sub(r'[\s().-]', '', text('phone'))
    if phone.startswith('00'):
        phone = '+' + phone[2:]
    elif phone.startswith('0'):
        phone = '+44' + phone[1:]
    return dict(name=text('name'), email=text('email').lower(), phone=phone,
                message=text('message'), permission=p.get('permission_to_reply') is True)


def issues_for(n):
    issues = []
    if not n['name']:
        issues.append('missing_name')
    if not n['message']:
        issues.append('missing_message')
    if not re.fullmatch(r'[^\s@<>]+@[^\s@<>.]+(?:\.[^\s@<>.]+)+', n['email']):
        issues.append('invalid_email')
    if n['phone'] and not re.fullmatch(r'\+[1-9][0-9]{7,14}', n['phone']):
        issues.append('invalid_phone')
    return issues


CATEGORIES = {
    'Booking enquiry': r'\b(book|booking|appointment|availability)\b',
    'Sales enquiry': r'\b(quote|pricing|price|purchase|buy|proposal)\b',
    'Support request': r'\b(broken|error|support|refund|fault|not working)\b',
    'Recruitment enquiry': r'\b(job|career|vacancy|cv|recruitment|apply)\b',
}


def classify(message):
    matches = [name for name, pattern in CATEGORIES.items() if re.search(pattern, message, re.I)]
    return (matches[0], False) if len(matches) == 1 else ('Other', True)


class Store:
    def __init__(self, path, clock=time.time, max_attempts=4, base_delay=5, lease_seconds=30):
        self.path = str(path)
        self.clock = clock
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.lease_seconds = lease_seconds
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript(Path(__file__).with_name('migrations').joinpath('001_initial.sql').read_text())

    def connect(self):
        c = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=15000')
        return c

    @contextmanager
    def tx(self):
        c = self.connect()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def event(self, c, lead, kind, detail=None):
        c.execute('INSERT INTO events(lead_id,correlation_id,kind,detail,created_at) VALUES(?,?,?,?,?)',
                  (lead['id'], lead['correlation_id'], kind, json.dumps(detail or {}), self.clock()))

    def lead(self, c, lead_id):
        row = c.execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
        if not row:
            raise Problem(404, 'lead_not_found')
        return dict(row)

    def match_contact(self, c, n, issues):
        email = n['email'] if 'invalid_email' not in issues else None
        phone = n['phone'] if n['phone'] and 'invalid_phone' not in issues else None
        rows = c.execute('SELECT * FROM contacts WHERE email=? OR phone=?', (email, phone)).fetchall()
        # A matching email with a different existing phone (or vice versa) is ambiguous too.
        if len(rows) > 1 or (rows and (
            (email and rows[0]['email'] and email != rows[0]['email']) or
            (phone and rows[0]['phone'] and phone != rows[0]['phone'])
        )):
            issues.append('identity_conflict')
            return None
        if rows:
            row = rows[0]
            c.execute('UPDATE contacts SET email=COALESCE(email,?),phone=COALESCE(phone,?) WHERE id=?',
                      (email, phone, row['id']))
            return row['id']
        if not email and not phone:
            return None
        contact = uid()
        c.execute('INSERT INTO contacts VALUES(?,?,?,?)', (contact, email, phone, self.clock()))
        return contact

    def ingest(self, p):
        for key in ('source', 'event_id'):
            if not isinstance(p.get(key), str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', p[key]):
                raise Problem(422, 'invalid_' + key)
        for key, limit in [('name', 200), ('email', 254), ('phone', 40), ('message', 10000)]:
            if key in p and (not isinstance(p[key], str) or len(p[key]) > limit):
                raise Problem(422, 'invalid_' + key + '_type_or_length')
        if 'permission_to_reply' in p and type(p['permission_to_reply']) is not bool:
            raise Problem(422, 'permission_must_be_boolean')
        allowed = {k: p[k] for k in ('source','event_id','name','email','phone','message','permission_to_reply') if k in p}
        h = digest(allowed)
        n = normalize(p)
        # Different sources share contacts, but each genuine source enquiry is retained.
        fp = digest({'source': p['source'], **n})
        now = self.clock()
        with self.tx() as c:
            old = c.execute('SELECT id,payload_hash FROM leads WHERE source=? AND event_id=?',
                            (p['source'], p['event_id'])).fetchone()
            alias = c.execute('SELECT lead_id AS id,payload_hash FROM duplicates WHERE source=? AND event_id=?',
                              (p['source'], p['event_id'])).fetchone()
            if old or alias:
                old = old or alias
                if old['payload_hash'] != h:
                    raise Problem(409, 'event_payload_conflict')
                lead = self.lead(c, old['id'])
                self.event(c, lead, 'duplicate_delivery')
                return {'lead_id': lead['id'], 'duplicate': True, 'state': lead['state'], 'correlation_id': lead['correlation_id']}
            same = c.execute('SELECT id FROM leads WHERE fingerprint=?', (fp,)).fetchone()
            if same:
                lead = self.lead(c, same['id'])
                c.execute('INSERT INTO duplicates VALUES(?,?,?,?,?)', (p['source'],p['event_id'],h,lead['id'],now))
                self.event(c, lead, 'duplicate_submission')
                return {'lead_id': lead['id'], 'duplicate': True, 'state': lead['state'], 'correlation_id': lead['correlation_id']}
            issues = issues_for(n)
            contact = self.match_contact(c, n, issues)
            lead_id, correlation = uid(), uid()
            c.execute('''INSERT INTO leads(id,source,event_id,correlation_id,payload_hash,fingerprint,original,
                name,email,phone,message,permission,contact_id,issues,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (lead_id,p['source'],p['event_id'],correlation,h,fp,json.dumps(allowed),n['name'],n['email'],
                 n['phone'],n['message'],int(n['permission']),contact,json.dumps(issues),
                 'review' if issues else 'received',now,now))
            lead = self.lead(c, lead_id)
            self.event(c, lead, 'intake_persisted', {'issue_codes': issues})
            return {'lead_id': lead_id, 'duplicate': False, 'state': lead['state'], 'correlation_id': correlation}

    def qualify(self, lead_id):
        with self.tx() as c:
            lead = self.lead(c, lead_id)
            if lead['state'] == 'received':
                category, uncertain = classify(lead['message'])
                issues = ['uncertain_category'] if uncertain else []
                c.execute('UPDATE leads SET category=?,issues=?,state=?,updated_at=? WHERE id=?',
                          (category,json.dumps(issues),'review' if uncertain else 'qualified',self.clock(),lead_id))
                self.event(c, lead, 'qualification', {'category':category,'uncertain':uncertain})
            return {'lead_id':lead_id,'state':self.lead(c, lead_id)['state']}

    def draft(self, lead_id):
        with self.tx() as c:
            lead = self.lead(c, lead_id)
            if lead['state'] == 'qualified':
                if not lead['permission']:
                    c.execute('UPDATE leads SET state=?,updated_at=? WHERE id=?', ('no_permission',self.clock(),lead_id))
                    self.event(c, lead, 'reply_blocked_no_permission')
                else:
                    prompts = {
                        'Booking enquiry': 'Please share your preferred date and time so we can check availability.',
                        'Sales enquiry': 'Please share the scope and timing you have in mind so we can prepare the next step.',
                        'Support request': 'Please share any relevant error details so a person can review the issue.',
                        'Recruitment enquiry': 'Please share the role you are interested in and any relevant experience.',
                        'Other': 'Please share a little more detail so we can direct your enquiry to the right person.',
                    }
                    body = f"Hello {lead['name']},\n\nThank you for your enquiry. {prompts[lead['category']]}\n\nSparrow Works"
                    c.execute('INSERT OR IGNORE INTO drafts VALUES(?,?,?,?,?,?,?)',
                              (uid(),lead_id,lead['revision'],lead['email'],'Re: your enquiry',body,'pending'))
                    c.execute('UPDATE leads SET state=?,updated_at=? WHERE id=?', ('awaiting_approval',self.clock(),lead_id))
                    self.event(c, lead, 'draft_created', {'revision':lead['revision']})
            return {'lead_id':lead_id,'state':self.lead(c, lead_id)['state']}

    def correct(self, lead_id, patch, actor):
        allowed = {'name','email','phone','message','category'}
        if set(patch) - allowed:
            raise Problem(422, 'unsupported_correction')
        with self.tx() as c:
            lead = self.lead(c, lead_id)
            if c.execute('SELECT 1 FROM outbox o JOIN drafts d ON d.id=o.draft_id WHERE d.lead_id=?', (lead_id,)).fetchone():
                raise Problem(409, 'approved_lead_locked')
            p = {k: lead[k] for k in ('name','email','phone','message')}
            p.update({k:v for k,v in patch.items() if k != 'category'})
            for key,v in p.items():
                if not isinstance(v,str) or len(v) > {'name':200,'email':254,'phone':40,'message':10000}[key]:
                    raise Problem(422, 'invalid_correction')
            n = normalize(p)
            issues = issues_for(n)
            contact = self.match_contact(c, n, issues)
            category = patch.get('category')
            if category is not None and category not in {*CATEGORIES, 'Other'}:
                raise Problem(422, 'invalid_category')
            if not category:
                category, uncertain = classify(n['message'])
                if uncertain:
                    issues.append('uncertain_category')
            c.execute("UPDATE drafts SET state='superseded' WHERE lead_id=? AND state IN ('pending','rejected')", (lead_id,))
            c.execute('''UPDATE leads SET name=?,email=?,phone=?,message=?,category=?,issues=?,contact_id=?,
                       state=?,revision=revision+1,updated_at=? WHERE id=?''',
                      (n['name'],n['email'],n['phone'],n['message'],category,json.dumps(issues),contact,
                       'review' if issues else 'qualified',self.clock(),lead_id))
            self.event(c, lead, 'operator_correction', {'actor':actor,'fields':sorted(patch)})
        return self.draft(lead_id)

    def decide(self, lead_id, draft_id, decision, actor, simulation_faults=None):
        if decision not in ('approve','reject'):
            raise Problem(422, 'invalid_decision')
        if simulation_faults is not None and (decision!='approve' or not simulation_faults or len(simulation_faults)>10 or any(type(s) is not int or s not in (200,400,429,500,503) for s in simulation_faults)):
            raise Problem(422, 'invalid_fault_plan')
        with self.tx() as c:
            lead = self.lead(c, lead_id)
            draft = c.execute('SELECT * FROM drafts WHERE id=? AND lead_id=?', (draft_id,lead_id)).fetchone()
            if not draft:
                raise Problem(404, 'draft_not_found')
            if draft['revision'] != lead['revision'] or draft['state'] == 'superseded':
                raise Problem(409, 'stale_draft')
            previous = c.execute('SELECT decision FROM approvals WHERE draft_id=?', (draft_id,)).fetchone()
            if previous:
                if previous['decision'] != decision:
                    raise Problem(409, 'decision_already_recorded')
                return {'lead_id':lead_id,'state':lead['state'],'repeated':True}
            if lead['state'] != 'awaiting_approval' or not lead['permission'] or json.loads(lead['issues']):
                raise Problem(409, 'lead_not_approvable')
            c.execute('INSERT INTO approvals VALUES(?,?,?,?)', (draft_id,decision,actor,self.clock()))
            c.execute('UPDATE drafts SET state=? WHERE id=?', ('approved' if decision=='approve' else 'rejected',draft_id))
            state = 'queued' if decision == 'approve' else 'rejected'
            c.execute('UPDATE leads SET state=?,updated_at=? WHERE id=?', (state,self.clock(),lead_id))
            if decision == 'approve':
                outbox_id = uid()
                c.execute('INSERT INTO outbox(id,draft_id,state,next_at,created_at) VALUES(?,?,?,?,?)',
                          (outbox_id,draft_id,'queued',self.clock(),self.clock()))
                if simulation_faults:
                    c.execute('INSERT INTO provider_faults VALUES(?,?)',(outbox_id,json.dumps(simulation_faults)))
            self.event(c, lead, 'human_' + decision, {'actor':actor,'draft_id':draft_id})
            return {'lead_id':lead_id,'state':state,'repeated':False}

    def pending(self):
        with self.connect() as c:
            return {'leads':[{'lead_id':r['id']} for r in c.execute("SELECT id FROM leads WHERE state IN ('received','qualified') ORDER BY created_at LIMIT 50")]}

    def recover(self):
        now = self.clock()
        count = 0
        with self.tx() as c:
            for o in c.execute("SELECT * FROM outbox WHERE state='processing' AND lease_until<=?", (now,)).fetchall():
                state = 'dead' if o['attempts'] >= self.max_attempts else 'retry'
                c.execute('UPDATE delivery_attempts SET outcome=? WHERE token=? AND outcome=?',
                          ('interrupted',o['lease_token'],'started'))
                c.execute('UPDATE outbox SET state=?,next_at=?,lease_token=NULL,lease_until=NULL,last_error=? WHERE id=?',
                          (state,now,'lease_expired',o['id']))
                lead = c.execute('SELECT l.* FROM leads l JOIN drafts d ON d.lead_id=l.id WHERE d.id=?',(o['draft_id'],)).fetchone()
                c.execute('UPDATE leads SET state=?,updated_at=? WHERE id=?', ('failed' if state=='dead' else 'queued',now,lead['id']))
                self.event(c, lead, 'lease_recovered', {'outbox_id':o['id'],'state':state})
                count += 1
        return {'recovered':count}

    def claim(self):
        now = self.clock()
        with self.tx() as c:
            row = c.execute("SELECT * FROM outbox WHERE state IN ('queued','retry') AND next_at<=? AND attempts<? ORDER BY next_at LIMIT 1",(now,self.max_attempts)).fetchone()
            if not row:
                return {'jobs':[]}
            token = uid()
            c.execute("UPDATE outbox SET state='processing',attempts=attempts+1,lease_until=?,lease_token=? WHERE id=?",(now+self.lease_seconds,token,row['id']))
            c.execute('INSERT INTO delivery_attempts(outbox_id,attempt,token,outcome,created_at) VALUES(?,?,?,?,?)',
                      (row['id'],row['attempts']+1,token,'started',now))
            return {'jobs':[{'outbox_id':row['id'],'lease_token':token}]}

    def delivery_payload(self, outbox_id, lease_token):
        token = lease_token
        with self.connect() as c:
            r = c.execute('''SELECT o.*,d.recipient,d.subject,d.body,d.state AS draft_state,l.permission
                            FROM outbox o JOIN drafts d ON d.id=o.draft_id JOIN leads l ON l.id=d.lead_id
                            JOIN approvals a ON a.draft_id=d.id AND a.decision='approve' WHERE o.id=?''',(outbox_id,)).fetchone()
            if not r or r['state'] != 'processing' or r['lease_token'] != token or r['lease_until'] <= self.clock():
                raise Problem(409, 'lease_not_owned')
            if not r['permission'] or r['draft_state'] != 'approved':
                raise Problem(409, 'approval_required')
            return {k:r[k] for k in ('recipient','subject','body')} | {'idempotency_key':outbox_id}

    def finish(self, outbox_id, token, status, retry_after=0):
        now = self.clock()
        with self.tx() as c:
            o = c.execute("SELECT * FROM outbox WHERE id=? AND state='processing' AND lease_token=? AND lease_until>?",(outbox_id,token,now)).fetchone()
            if not o:
                raise Problem(409, 'stale_delivery_result')
            if 200 <= status < 300:
                state, error, next_at = 'sent', None, now
            elif (status == 429 or status >= 500 or status == 0) and o['attempts'] < self.max_attempts:
                state, error = 'retry', 'transport_error' if status==0 else f'provider_http_{status}'
                next_at = now + max(min(max(retry_after,0),3600),min(300,self.base_delay * 2 ** (o['attempts']-1)))
            else:
                state, error, next_at = 'dead', f'provider_http_{status}', now
            c.execute('UPDATE outbox SET state=?,next_at=?,lease_token=NULL,lease_until=NULL,last_error=?,sent_at=? WHERE id=?',
                      (state,next_at,error,now if state=='sent' else None,outbox_id))
            c.execute('UPDATE delivery_attempts SET outcome=?,status=?,next_at=? WHERE token=?',(state,status,next_at,token))
            lead = c.execute('SELECT l.* FROM leads l JOIN drafts d ON d.lead_id=l.id WHERE d.id=?',(o['draft_id'],)).fetchone()
            c.execute('UPDATE leads SET state=?,updated_at=? WHERE id=?',('sent' if state=='sent' else 'failed' if state=='dead' else 'queued',now,lead['id']))
            self.event(c, lead, 'delivery_' + state, {'outbox_id':outbox_id,'attempt':o['attempts'],'status':status})
            return {'outbox_id':outbox_id,'state':state,'next_at':next_at,'attempts':o['attempts']}

    def set_fault(self, outbox_id, statuses):
        if not statuses or len(statuses)>10 or any(type(s) is not int or s not in (200,400,429,500,503) for s in statuses):
            raise Problem(422, 'invalid_fault_plan')
        with self.tx() as c:
            if not c.execute('SELECT 1 FROM outbox WHERE id=?',(outbox_id,)).fetchone():
                raise Problem(404, 'outbox_not_found')
            c.execute('INSERT INTO provider_faults VALUES(?,?) ON CONFLICT(outbox_id) DO UPDATE SET statuses=excluded.statuses', (outbox_id,json.dumps(statuses)))

    def simulate(self, payload):
        key = payload['idempotency_key']
        h = digest(payload)
        with self.tx() as c:
            old = c.execute('SELECT * FROM provider_receipts WHERE idempotency_key=?',(key,)).fetchone()
            if old:
                if old['payload_hash'] != h:
                    raise Problem(409, 'provider_idempotency_conflict')
                return 200, {'receipt_id':old['receipt_id'],'replayed':True}
            # Simulator accepts only an actually approved frozen payload, even with its own token.
            approved = c.execute('''SELECT d.recipient,d.subject,d.body FROM outbox o JOIN drafts d ON d.id=o.draft_id
                    JOIN approvals a ON a.draft_id=d.id AND a.decision='approve' WHERE o.id=? AND d.state='approved' ''',(key,)).fetchone()
            if not approved or any(payload.get(k) != approved[k] for k in ('recipient','subject','body')):
                raise Problem(409, 'simulator_requires_approved_payload')
            fault = c.execute('SELECT statuses FROM provider_faults WHERE outbox_id=?',(key,)).fetchone()
            if fault:
                statuses = json.loads(fault['statuses'])
                if statuses:
                    status = statuses.pop(0)
                    c.execute('UPDATE provider_faults SET statuses=? WHERE outbox_id=?',(json.dumps(statuses),key))
                    if status != 200:
                        return status, {'code':'synthetic_fault'}
            receipt = uid()
            c.execute('INSERT INTO provider_receipts VALUES(?,?,?,?,?,?,?)',
                      (key,h,receipt,payload['recipient'],payload['subject'],payload['body'],self.clock()))
            return 200, {'receipt_id':receipt,'replayed':False}

    def retry_dead(self, outbox_id, actor):
        # Do not reset the automatic budget: manual reconciliation is a separate, explicit action.
        with self.tx() as c:
            o = c.execute("SELECT * FROM outbox WHERE id=? AND state='dead'",(outbox_id,)).fetchone()
            if not o:
                raise Problem(409, 'not_dead_letter')
            receipt = c.execute('SELECT 1 FROM provider_receipts WHERE idempotency_key=?',(outbox_id,)).fetchone()
            if not receipt:
                raise Problem(409, 'resolve_fault_and_create_new_review_required')
            c.execute("UPDATE outbox SET state='sent',sent_at=?,last_error=NULL WHERE id=?",(self.clock(),outbox_id))
            lead = c.execute('SELECT l.* FROM leads l JOIN drafts d ON d.lead_id=l.id WHERE d.id=?',(o['draft_id'],)).fetchone()
            c.execute("UPDATE leads SET state='sent',updated_at=? WHERE id=?",(self.clock(),lead['id']))
            self.event(c, lead, 'receipt_reconciled', {'actor':actor,'outbox_id':outbox_id})
            return {'state':'sent'}

    def redrive_dead(self, outbox_id, actor):
        with self.tx() as c:
            o = c.execute("SELECT * FROM outbox WHERE id=? AND state='dead'",(outbox_id,)).fetchone()
            if not o:
                raise Problem(409,'not_dead_letter')
            if c.execute('SELECT 1 FROM provider_receipts WHERE idempotency_key=?',(outbox_id,)).fetchone():
                raise Problem(409,'receipt_exists_reconcile_instead')
            c.execute("UPDATE outbox SET state='queued',attempts=0,next_at=?,last_error=NULL WHERE id=?",(self.clock(),outbox_id))
            lead = c.execute('SELECT l.* FROM leads l JOIN drafts d ON d.lead_id=l.id WHERE d.id=?',(o['draft_id'],)).fetchone()
            c.execute("UPDATE leads SET state='queued',updated_at=? WHERE id=?",(self.clock(),lead['id']))
            self.event(c,lead,'human_redrive',{'actor':actor,'outbox_id':outbox_id,'new_attempt_budget':self.max_attempts})
            return {'state':'queued','outbox_id':outbox_id}

    def detail(self, lead_id):
        with self.connect() as c:
            lead = self.lead(c, lead_id)
            lead['issues'] = json.loads(lead['issues'])
            lead['original'] = json.loads(lead['original'])
            lead['drafts'] = [dict(r) for r in c.execute('SELECT * FROM drafts WHERE lead_id=? ORDER BY revision DESC',(lead_id,))]
            lead['events'] = [dict(r) for r in c.execute('SELECT * FROM events WHERE lead_id=? ORDER BY id',(lead_id,))]
            lead['outbox'] = [dict(r) for r in c.execute('SELECT o.* FROM outbox o JOIN drafts d ON d.id=o.draft_id WHERE d.lead_id=?',(lead_id,))]
            lead['attempts'] = [dict(r) for r in c.execute('SELECT a.* FROM delivery_attempts a JOIN outbox o ON o.id=a.outbox_id JOIN drafts d ON d.id=o.draft_id WHERE d.lead_id=? ORDER BY a.id',(lead_id,))]
            lead['contact_history'] = [dict(r) for r in c.execute('''SELECT l.id,l.source,l.category,l.state,l.created_at FROM leads l
                  WHERE l.contact_id=? AND l.id!=? ORDER BY l.created_at DESC''',(lead['contact_id'],lead_id))]
            return lead

    def dashboard(self):
        with self.connect() as c:
            def count(sql):
                return c.execute(sql).fetchone()[0]
            return {'metrics':{
                'total_enquiries':count('SELECT COUNT(*) FROM leads'),
                'qualified_leads':count("SELECT COUNT(*) FROM leads WHERE category IS NOT NULL AND issues='[]'"),
                'duplicate_submissions':count("SELECT COUNT(*) FROM events WHERE kind IN ('duplicate_delivery','duplicate_submission')"),
                'pending_reviews':count("SELECT COUNT(*) FROM leads WHERE state='review'"),
                'pending_approvals':count("SELECT COUNT(*) FROM drafts WHERE state='pending'"),
                'queued_followups':count("SELECT COUNT(*) FROM outbox WHERE state IN ('queued','retry','processing')"),
                'failed_executions':count("SELECT COUNT(*) FROM outbox WHERE state='dead'") + count('SELECT COUNT(*) FROM orchestration_failures'),
                'retry_history':count("SELECT COUNT(*) FROM delivery_attempts WHERE outcome IN ('retry','interrupted')"),
                'simulated_deliveries':count('SELECT COUNT(*) FROM provider_receipts')},
                'leads':[dict(r) for r in c.execute('SELECT id,name,email,source,category,state,created_at,correlation_id FROM leads ORDER BY created_at DESC LIMIT 200')],
                'recent_events':[dict(r) for r in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 50')],
                'dead_letters':[dict(r) for r in c.execute("SELECT id,last_error,attempts FROM outbox WHERE state='dead'")],
                'delivery_attempts':[dict(r) for r in c.execute('SELECT * FROM delivery_attempts ORDER BY id DESC LIMIT 50')]}
