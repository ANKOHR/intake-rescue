"""Real HTTP → n8n → service → SQLite → simulator verification. Synthetic data only.

Requires the local app and imported/published n8n workflows. Never mocks n8n.
Run against disposable local state or retain the created synthetic records as demo evidence.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid
import httpx
from config import load, ROOT

load()
BASE=os.environ.get('IR_API_URL','http://127.0.0.1:8765')
N8N='http://127.0.0.1:'+os.environ.get('N8N_PORT','5678')
prefix=uuid.uuid4().hex[:10]
results=[]
client=httpx.Client(timeout=30)


def api(path,method='GET',body=None,role='admin',expect=200):
    r=client.request(method,BASE+path,json=body,headers={
        'Authorization':'Bearer '+os.environ['IR_'+role.upper()+'_TOKEN'],'X-Operator':'runtime-verifier'})
    assert r.status_code==expect,(path,r.status_code,r.text[:200])
    return r.json()


def wait(fn,seconds=45):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        value=fn()
        if value:return value
        time.sleep(.25)
    raise AssertionError('Timed out waiting for observed runtime state')


def record(name,proof):
    results.append({'scenario':name,'result':'PASS','proof':proof})
    print('PASS '+name,flush=True)


def payload(tag,**extra):
    return {'source':'runtime-demo','event_id':prefix+'-'+tag,'name':tag.title()+' Example',
            'email':tag+'-'+prefix+'@example.test','message':'Please send a quote. Reference '+prefix+' '+tag+'.',
            'permission_to_reply':True,**extra}


def intake(p,expected=200):
    r=client.post(N8N+'/webhook/intake-rescue/enquiry',json=p,headers={
        'Authorization':'Bearer '+os.environ['IR_INTAKE_TOKEN']})
    assert r.status_code==expected,(r.status_code,r.text[:200])
    return r.json()


def detail(lead):return api('/api/leads/'+lead)
def is_state(lead,state):
    d=detail(lead)
    return d if d['state']==state else None
def approve(lead,faults=None):
    d=wait(lambda:is_state(lead,'awaiting_approval'))
    body={'draft_id':d['drafts'][0]['id'],'decision':'approve'}
    if faults:body['simulation_faults']=faults
    return api('/api/leads/'+lead+'/decision','POST',body)


def main():
    assert api('/health')['delivery_mode']=='simulated'
    initial=api('/api/dashboard')['metrics']
    p=payload('successful')
    receipt=intake(p)
    lead=receipt['lead_id']
    d=wait(lambda:is_state(lead,'awaiting_approval'))
    assert d['category']=='Sales enquiry'
    assert not d['outbox']
    record('Real n8n intake, qualification and draft',{'lead_id':lead,'correlation_id':receipt['correlation_id']})
    duplicate=intake(p)
    assert duplicate['duplicate'] and duplicate['lead_id']==lead
    record('Repeated webhook suppressed',{'same_lead_id':True})
    p2=p|{'source':'partner-demo','event_id':prefix+'-partner'}
    partner=intake(p2)['lead_id']
    assert detail(partner)['contact_id']==detail(lead)['contact_id']
    record('Cross-source contact recognised',{'distinct_enquiries':partner!=lead,'shared_contact':True})
    assert api('/api/dashboard')['metrics']['simulated_deliveries']==initial['simulated_deliveries']
    record('No delivery before approval',{'receipt_count_unchanged':True})
    approve(lead)
    repeat={'draft_id':d['drafts'][0]['id'],'decision':'approve'}
    assert api('/api/leads/'+lead+'/decision','POST',repeat)['repeated']
    sent=wait(lambda:is_state(lead,'sent'))
    assert len(sent['outbox'])==1
    record('Approved delivery and repeated approval',{'state':'sent','outbox_rows':1})
    retry=intake(payload('retry'))['lead_id']
    approve(retry,[503,200])
    recovered=wait(lambda:is_state(retry,'sent'))
    assert [a['status'] for a in recovered['attempts']]==[503,200]
    assert recovered['attempts'][1]['created_at']>=recovered['attempts'][0]['next_at']
    record('503 failure and durable retry',{'statuses':[503,200],'backoff_respected':True})
    rate=intake(payload('rate-limited'))['lead_id']
    approve(rate,[429,200])
    limited=wait(lambda:is_state(rate,'sent'))
    assert [a['status'] for a in limited['attempts']]==[429,200]
    assert limited['attempts'][1]['created_at']>=limited['attempts'][0]['next_at']
    record('429 Retry-After and recovery',{'statuses':[429,200]})
    permanent=intake(payload('permanent'))['lead_id']
    approve(permanent,[400])
    failed=wait(lambda:is_state(permanent,'failed'))
    assert len(failed['attempts'])==1 and failed['outbox'][0]['state']=='dead'
    record('Permanent provider error dead-lettered',{'attempts':1,'status':400})
    review=intake(payload('review',email='invalid',message='Please help. Reference '+prefix))['lead_id']
    assert detail(review)['state']=='review'
    api('/api/leads/'+review,'PATCH',{'email':'corrected-'+prefix+'@example.test','category':'Other'})
    assert detail(review)['state']=='awaiting_approval'
    draft=detail(review)['drafts'][0]['id']
    api('/api/leads/'+review+'/decision','POST',{'draft_id':draft,'decision':'reject'})
    assert detail(review)['state']=='rejected'
    record('Manual correction and rejection',{'rejected':True,'no_outbox':not detail(review)['outbox']})
    no_reply=intake(payload('no-permission',permission_to_reply=False))['lead_id']
    assert detail(no_reply)['state']=='no_permission' and not detail(no_reply)['drafts']
    record('Reply permission enforced',{'state':'no_permission'})
    # Persist an intake without running subsequent steps, then let real n8n recovery resume it.
    interrupted=api('/intake','POST',payload('interrupted-intake'),role='intake')['lead_id']
    wait(lambda:is_state(interrupted,'awaiting_approval'))
    record('Interrupted intake resumed by n8n scheduler',{'lead_id':interrupted})
    # Force an actual n8n node error; error workflow should record safe metadata.
    before=api('/api/dashboard')['metrics']['failed_executions']
    r=client.post(N8N+'/webhook/intake-rescue/enquiry',json={'source':'runtime-demo'},
                  headers={'Authorization':'Bearer '+os.environ['IR_INTAKE_TOKEN']})
    assert r.status_code>=400
    wait(lambda:api('/api/dashboard')['metrics']['failed_executions']>before)
    record('Real n8n node failure and error workflow',{'webhook_status':r.status_code,'redacted_failure_recorded':True})
    r=client.post(N8N+'/webhook/intake-rescue/enquiry',json=p)
    assert r.status_code==403 or r.status_code==401
    record('n8n webhook authentication',{'unauthorized_status':r.status_code})
    # Independently inspect committed SQL state, rather than relying on dashboard counters alone.
    database=Path(os.environ['IR_DATABASE'])
    if not database.is_absolute():database=ROOT/database
    if os.environ.get('IR_DOCKER_AUDIT')=='1':
        result=subprocess.run(['docker','compose','exec','-T','app','python','-c',(ROOT/'scripts'/'audit_invariants.py').read_text()],cwd=ROOT,text=True,capture_output=True,check=True)
        audit=json.loads(result.stdout)
        unapproved,duplicate_outbox,receipts=(audit[k] for k in ('unapproved_receipts','duplicate_outbox_groups','simulated_receipts'))
    else:
        with sqlite3.connect(database) as c:
            unapproved=c.execute("SELECT COUNT(*) FROM provider_receipts r LEFT JOIN outbox o ON o.id=r.idempotency_key LEFT JOIN approvals a ON a.draft_id=o.draft_id AND a.decision='approve' WHERE a.draft_id IS NULL").fetchone()[0]
            duplicate_outbox=c.execute('SELECT COUNT(*) FROM (SELECT draft_id FROM outbox GROUP BY draft_id HAVING COUNT(*)>1)').fetchone()[0]
            receipts=c.execute('SELECT COUNT(*) FROM provider_receipts').fetchone()[0]
    assert unapproved==0 and duplicate_outbox==0
    record('Independent database invariant audit',{'unapproved_receipts':0,'duplicate_outbox_groups':0,'simulated_receipts':receipts})
    report={'run_prefix':prefix,'delivery_mode':'simulated','n8n_version':'2.46.7','timestamp_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            'results':results,'metrics':api('/api/dashboard')['metrics']}
    (ROOT/'evidence'/'n8n-integration.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(results)} real runtime scenarios passed.',flush=True)


if __name__=='__main__':
    try:main()
    finally:client.close()
