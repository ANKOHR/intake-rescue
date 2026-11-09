"""Disposable local recording aid. Only fixed synthetic intake; no outbound approval endpoint."""
from pathlib import Path
import html
import json
import os
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from config import load,ROOT
load()
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import httpx
import uvicorn

RUN='recording-'+str(int(time.time()))
PAYLOAD={'source':'portfolio-form','event_id':RUN,'name':'Alex Portfolio','email':'alex.portfolio@example.test',
         'message':'Please send a quote for an enquiry intake workflow. Reference '+RUN+'.',
         'permission_to_reply':True}
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
receipts=[]
@app.get('/')
def page():
    return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Intake Rescue · Live webhook proof</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f2f1eb;color:#232b27;font:18px Arial}header{background:#202923;color:#faf9ef;padding:30px 6vw;letter-spacing:3px}main{max-width:1250px;margin:42px auto;padding:0 35px}h1{font:48px Georgia;margin:12px 0}small{font-size:12px;color:#56705a;letter-spacing:2px}.columns{display:grid;grid-template-columns:1.1fr 1fr;gap:28px}section{background:#fcfbf7;border:1px solid #d8ddd0;padding:28px;border-radius:4px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.7 Consolas,monospace;background:#edf0e6;padding:20px}button{background:#305c43;color:#fff;border:0;padding:16px 22px;border-radius:3px;font:16px Arial;margin:12px 8px 12px 0;cursor:pointer}button:disabled{opacity:.5}p{line-height:1.6}.safe{color:#426346;font-size:15px}</style>
<header>SPARROW WORKS / INTAKE RESCUE</header><main><small>LIVE LOCAL DEMONSTRATION · SYNTHETIC DATA</small><h1>One enquiry. Repeated safely.</h1><p>Both buttons send this exact payload through the genuine n8n production webhook.</p><div class="columns"><section><h2>Synthetic enquiry</h2><pre>'''+html.escape(json.dumps(PAYLOAD,indent=2))+'''</pre><button id="first">Submit enquiry</button><button id="repeat">Repeat same webhook</button><p class="safe">Authentication stays server-side. No customer mailbox is connected.</p></section><section><h2>Observed webhook receipts</h2><pre id="receipts">No requests sent yet.</pre><p>Compare the lead IDs and the duplicate flag. The second request must return the original lead.</p><h2>Delivery proof</h2><pre id="proof">Awaiting enquiry.</pre><button id="refresh">Refresh delivery proof</button></section></div></main><script>
async function send(){const r=await fetch('/submit',{method:'POST'});document.getElementById('receipts').textContent=JSON.stringify(await r.json(),null,2);await proof();}
async function proof(){const r=await fetch('/proof');document.getElementById('proof').textContent=JSON.stringify(await r.json(),null,2);}
document.getElementById('first').onclick=send;document.getElementById('repeat').onclick=send;document.getElementById('refresh').onclick=proof;
</script></html>''')
@app.post('/submit')
def submit():
    r=httpx.post('http://127.0.0.1:5678/webhook/intake-rescue/enquiry',json=PAYLOAD,
        headers={'Authorization':'Bearer '+os.environ['IR_INTAKE_TOKEN']},timeout=30)
    body=r.json()
    receipts.append({'http_status':r.status_code,**body})
    (ROOT/'.runtime'/'recording-receipts.json').write_text(json.dumps(receipts,indent=2))
    return {'deliveries':receipts}
@app.get('/proof')
def proof():
    if not receipts or not receipts[0].get('lead_id'):return {'state':'Awaiting enquiry'}
    r=httpx.get('http://127.0.0.1:8765/api/leads/'+receipts[0]['lead_id'],headers={'Authorization':'Bearer '+os.environ['IR_ADMIN_TOKEN']})
    d=r.json()
    import sqlite3
    with sqlite3.connect(ROOT/'data'/'intake.db') as c:
        count=c.execute('SELECT COUNT(*) FROM provider_receipts WHERE idempotency_key IN (SELECT id FROM outbox WHERE draft_id IN (SELECT id FROM drafts WHERE lead_id=?))',(d['id'],)).fetchone()[0]
    return {'lead_id':d['id'],'state':d['state'],'approved':any(x['state']=='approved' for x in d['drafts']),
            'attempt_statuses':[a['status'] for a in d['attempts']],'simulated_receipts':count,'real_emails_sent':0}

if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8899,access_log=False)
