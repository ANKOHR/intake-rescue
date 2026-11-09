from pathlib import Path
import json
import os
import signal
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import load,ROOT
load()
import httpx
from app.domain import Store

headers=lambda role:{'Authorization':'Bearer '+os.environ['IR_'+role.upper()+'_TOKEN'],'X-Operator':'restart-verifier'}
base='http://127.0.0.1:8765'
p={'source':'restart-proof','event_id':'restart-'+str(int(time.time())),'name':'Casey Restart',
   'email':'casey-'+str(int(time.time()))+'@example.test','message':'Please send pricing. Restart test '+str(time.time()),'permission_to_reply':True}
with httpx.Client(timeout=30) as c:
    r=c.post('http://127.0.0.1:5678/webhook/intake-rescue/enquiry',json=p,headers=headers('intake'))
    r.raise_for_status();lead=r.json()['lead_id']
    d=c.get(base+'/api/leads/'+lead,headers=headers('admin')).json()
    c.post(base+'/api/leads/'+lead+'/decision',headers=headers('admin'),json={'draft_id':d['drafts'][0]['id'],'decision':'approve'}).raise_for_status()
    job=c.post(base+'/internal/outbox/claim',headers=headers('worker')).json()['jobs'][0]
    db=Store(ROOT/'data'/'intake.db')
    payload=db.delivery_payload(**job)
    receipt=c.post(base+'/simulator/send',headers=headers('simulator'),json=payload)
    receipt.raise_for_status()
    print('Simulator receipt persisted before application termination.',flush=True)
    # Supervisor supplies the PID of the service it started in this task.
    os.kill(int(sys.argv[1]),signal.SIGTERM)
    with open(ROOT/'.runtime'/'app-server.log','ab') as log:
        proc=subprocess.Popen([sys.executable,str(ROOT/'scripts'/'serve.py')],cwd=ROOT,env=os.environ,
                              stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    (ROOT/'.runtime'/'app.pid').write_text(str(proc.pid))
    until=time.monotonic()+55
    final=None
    while time.monotonic()<until:
        try:
            response=c.get(base+'/api/leads/'+lead,headers=headers('admin'))
            if response.status_code==200 and response.json()['state']=='sent':
                final=response.json();break
        except httpx.RequestError:pass
        time.sleep(.5)
    assert final,'n8n did not recover the expired lease after application restart'
    assert [a['outcome'] for a in final['attempts']]==['interrupted','sent']
    assert len(final['outbox'])==1
    with db.connect() as sql:
        count=sql.execute('SELECT COUNT(*) FROM provider_receipts WHERE idempotency_key=?',(job['outbox_id'],)).fetchone()[0]
    assert count==1
    repeated=c.post('http://127.0.0.1:5678/webhook/intake-rescue/enquiry',json=p,headers=headers('intake')).json()
    assert repeated['duplicate'] and repeated['lead_id']==lead
    stale=c.post(base+'/internal/deliver',headers=headers('worker'),json=job)
    assert stale.status_code==409
    report={'result':'PASS','lead_id':lead,'outbox_id':job['outbox_id'],'real_process_terminated':int(sys.argv[1]),
            'replacement_pid':proc.pid,'attempt_outcomes':[a['outcome'] for a in final['attempts']],
            'provider_receipts_for_key':count,'stale_worker_status':stale.status_code,'event_survived_restart':True,
            'recovery_driver':'real n8n 5-second scheduler'}
    (ROOT/'evidence'/'process-restart.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS actual process restart, n8n lease recovery, one provider receipt, stale-worker fence and persisted duplicate prevention.',flush=True)
