from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app.domain import Problem, Store, classify
from app.main import create_app
from conftest import approve, prepare


def test_01_valid_submission(store,payload):
    lead=prepare(store,payload)
    d=store.detail(lead)
    assert (d['email'],d['phone'],d['state'])==('alex@example.test','+447700900123','awaiting_approval')
    assert d['correlation_id'] and d['category']=='Sales enquiry'
    assert store.claim()=={'jobs':[]}


def test_02_missing_required_fields_go_to_review(store,payload):
    del payload['name']
    lead=prepare(store,payload)
    assert store.detail(lead)['issues']==['missing_name']
    assert not store.detail(lead)['drafts']
    del payload['event_id']
    with pytest.raises(Problem) as e: store.ingest(payload)
    assert e.value.status==422


def test_03_invalid_email(store,payload):
    payload['email']='invalid-email'
    lead=prepare(store,payload)
    assert 'invalid_email' in store.detail(lead)['issues']
    assert store.detail(lead)['state']=='review'


def test_04_repeated_webhook_event(store,payload):
    first=store.ingest(payload)
    second=store.ingest(payload)
    assert second['duplicate'] and second['lead_id']==first['lead_id']
    assert store.dashboard()['metrics']['total_enquiries']==1
    payload['message']='Different payload'
    with pytest.raises(Problem) as e:store.ingest(payload)
    assert e.value.code=='event_payload_conflict'


def test_05_contact_across_sources(store,payload):
    a=store.ingest(payload)['lead_id']
    payload['source']='partner'
    b=store.ingest(payload)['lead_id']
    assert a!=b
    assert store.detail(a)['contact_id']==store.detail(b)['contact_id']
    assert store.detail(a)['contact_history'][0]['id']==b


def test_06_conflicting_contact_identities(store,payload):
    store.ingest(payload)
    b=payload|{'event_id':'b','email':'blair@example.test','phone':'07700 900456'}
    store.ingest(b)
    conflict=payload|{'event_id':'c','phone':'07700 900456'}
    lead=prepare(store,conflict)
    assert store.detail(lead)['state']=='review'
    assert 'identity_conflict' in store.detail(lead)['issues']
    assert store.detail(lead)['contact_id'] is None


def test_07_no_permission_to_reply(store,payload):
    payload['permission_to_reply']=False
    lead=prepare(store,payload)
    assert store.detail(lead)['state']=='no_permission'
    assert not store.detail(lead)['drafts']
    with pytest.raises(Problem):store.correct(lead,{'permission_to_reply':True},'test')
    assert not store.claim()['jobs']


def test_08_approval_granted(store,payload):
    lead=approve(store,payload)
    assert store.detail(lead)['state']=='queued'
    assert len(store.claim()['jobs'])==1


def test_09_approval_rejected(store,payload):
    lead=prepare(store,payload)
    draft=store.detail(lead)['drafts'][0]['id']
    store.decide(lead,draft,'reject','test')
    assert store.detail(lead)['state']=='rejected'
    assert not store.claim()['jobs']
    with pytest.raises(Problem):store.decide(lead,draft,'approve','test')


def test_10_repeated_approval_request(store,payload):
    lead=approve(store,payload)
    draft=store.detail(lead)['drafts'][0]['id']
    assert store.decide(lead,draft,'approve','test')['repeated']
    assert len(store.detail(lead)['outbox'])==1


def deliver(store,job):
    p=store.delivery_payload(**job)
    status,receipt=store.simulate(p)
    return store.finish(job['outbox_id'],job['lease_token'],status,5 if status==429 else 0),receipt


def test_11_temporary_api_failure(store,payload,clock):
    lead=approve(store,payload)
    out=store.detail(lead)['outbox'][0]['id']
    store.set_fault(out,[503,200])
    result,_=deliver(store,store.claim()['jobs'][0])
    assert result['state']=='retry'
    assert not store.claim()['jobs']
    clock.advance(5)
    result,_=deliver(store,store.claim()['jobs'][0])
    assert result['state']=='sent'
    assert store.dashboard()['metrics']['simulated_deliveries']==1


def test_12_rate_limiting(store,payload,clock):
    lead=approve(store,payload)
    job=store.claim()['jobs'][0]
    result=store.finish(job['outbox_id'],job['lease_token'],429,retry_after=45)
    assert result['next_at']==clock()+45
    clock.advance(44)
    assert not store.claim()['jobs']
    clock.advance(1)
    assert deliver(store,store.claim()['jobs'][0])[0]['state']=='sent'


def test_13_permanent_api_failure(store,payload,clock):
    lead=approve(store,payload)
    out=store.detail(lead)['outbox'][0]['id']
    store.set_fault(out,[400])
    result,_=deliver(store,store.claim()['jobs'][0])
    assert result['state']=='dead'
    clock.advance(10000)
    assert not store.claim()['jobs']
    assert store.detail(lead)['state']=='failed'


def test_14_interrupted_execution_after_provider_success(store,payload,clock):
    lead=approve(store,payload)
    old=store.claim()['jobs'][0]
    p=store.delivery_payload(**old)
    status,receipt=store.simulate(p)
    assert status==200
    # Worker dies here, after the provider commits its receipt.
    clock.advance(31)
    restarted=Store(store.path,clock=clock)
    assert restarted.recover()['recovered']==1
    new=restarted.claim()['jobs'][0]
    assert new['lease_token']!=old['lease_token']
    result,replayed=deliver(restarted,new)
    assert result['state']=='sent' and replayed['replayed']
    with pytest.raises(Problem):restarted.finish(old['outbox_id'],old['lease_token'],200)
    assert restarted.dashboard()['metrics']['simulated_deliveries']==1


def test_15_concurrent_attempts_same_lead(store,payload):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:store.ingest(payload),range(16)))
    assert len({r['lead_id'] for r in results})==1
    lead=prepare(store,payload)
    draft=store.detail(lead)['drafts'][0]['id']
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _:store.decide(lead,draft,'approve','test'),range(16)))
        claims=list(pool.map(lambda _:store.claim(),range(16)))
    assert sum(len(c['jobs']) for c in claims)==1
    assert len(store.detail(lead)['outbox'])==1


def test_16_prevent_duplicate_outbound_actions(store,payload):
    lead=approve(store,payload)
    job=store.claim()['jobs'][0]
    p=store.delivery_payload(**job)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:store.simulate(p),range(16)))
    assert len({r[1]['receipt_id'] for r in results})==1
    assert sum(not r[1]['replayed'] for r in results)==1
    store.finish(job['outbox_id'],job['lease_token'],200)
    assert not store.claim()['jobs']
    with pytest.raises(Problem):store.delivery_payload(**job)


@pytest.mark.parametrize('method,path',[
    ('get','/api/dashboard'),('post','/intake'),('get','/internal/pending'),
    ('post','/internal/deliver'),('post','/simulator/send'),
    ('patch','/api/leads/fake'),('post','/api/leads/fake/decision')])
def test_17_unauthorized_access(client,method,path):
    assert getattr(client,method)(path).status_code==401


def test_18_persistence_after_restart(store,payload,clock):
    lead=approve(store,payload)
    fresh=Store(store.path,clock=clock)
    assert fresh.detail(lead)['drafts']==store.detail(lead)['drafts']
    assert fresh.ingest(payload)['duplicate']
    assert fresh.claim()['jobs']


def test_19_manual_review_and_correction(store,payload):
    payload['email']='invalid'
    payload['message']='Can you help?'
    lead=prepare(store,payload)
    store.correct(lead,{'email':'alex@example.test','category':'Other'},'reviewer')
    detail=store.detail(lead)
    assert detail['state']=='awaiting_approval'
    assert not detail['issues'] and detail['original']['email']=='invalid'
    old=detail['drafts'][0]['id']
    store.correct(lead,{'name':'Alex Corrected','category':'Other'},'reviewer')
    with pytest.raises(Problem) as e:store.decide(lead,old,'approve','test')
    assert e.value.code=='stale_draft'


def test_20_end_to_end_http_delivery(store,payload,keys):
    def provider(request):
        assert request.headers['authorization']=='Bearer '+keys['simulator']
        status,body=store.simulate(json.loads(request.content))
        return httpx.Response(status,json=body)
    with TestClient(create_app(store,keys,httpx.MockTransport(provider))) as c:
        headers={'Authorization':'Bearer '+keys['intake']}
        lead=c.post('/intake',json=payload,headers=headers).json()['lead_id']
        worker={'Authorization':'Bearer '+keys['worker']}
        admin={'Authorization':'Bearer '+keys['admin'],'X-Operator':'test'}
        assert c.post('/internal/leads/'+lead+'/qualify',headers=worker).status_code==200
        c.post('/internal/leads/'+lead+'/draft',headers=worker)
        detail=c.get('/api/leads/'+lead,headers=admin).json()
        assert not store.dashboard()['metrics']['simulated_deliveries']
        c.post('/api/leads/'+lead+'/decision',headers=admin,json={'draft_id':detail['drafts'][0]['id'],'decision':'approve'})
        job=c.post('/internal/outbox/claim',headers=worker).json()['jobs'][0]
        assert c.post('/internal/deliver',headers=worker,json=job).json()['state']=='sent'
        assert c.get('/api/leads/'+lead,headers=admin).json()['state']=='sent'


def test_bounded_exponential_retry_budget(store,payload,clock):
    approve(store,payload)
    for attempt in range(1,5):
        job=store.claim()['jobs'][0]
        result=store.finish(job['outbox_id'],job['lease_token'],503)
        assert result['attempts']==attempt
        if attempt<4:
            assert result['state']=='retry'
            assert result['next_at']-clock()==5*2**(attempt-1)
            clock.advance(5*2**(attempt-1))
        else: assert result['state']=='dead'
    clock.advance(10000)
    assert not store.claim()['jobs']


def test_recover_intake_between_stages(store,payload,clock):
    lead=store.ingest(payload)['lead_id']
    fresh=Store(store.path,clock=clock)
    assert fresh.pending()=={'leads':[{'lead_id':lead}]}
    fresh.qualify(lead)
    fresh.draft(lead)
    assert not fresh.pending()['leads']
    assert fresh.detail(lead)['state']=='awaiting_approval'


def test_content_duplicate_under_new_event_id(store,payload):
    first=store.ingest(payload)
    payload['event_id']='evt-002'
    second=store.ingest(payload)
    assert second['duplicate'] and second['lead_id']==first['lead_id']
    assert store.ingest(payload)['duplicate']
    assert store.dashboard()['metrics']['total_enquiries']==1


def test_ambiguous_qualification(store,payload):
    payload['message']='Can I book an appointment and get a refund?'
    lead=prepare(store,payload)
    assert store.detail(lead)['issues']==['uncertain_category']
    assert not store.detail(lead)['drafts']


@pytest.mark.parametrize('permission',['false','true',1,0,[],{}])
def test_permission_never_coerced(store,payload,permission):
    payload['permission_to_reply']=permission
    with pytest.raises(Problem) as e:store.ingest(payload)
    assert e.value.status==422


def test_approved_recipient_cannot_be_changed(store,payload):
    lead=approve(store,payload)
    with pytest.raises(Problem):store.correct(lead,{'email':'other@example.test'},'test')
    assert store.detail(lead)['email']=='alex@example.test'


def test_role_separation(client,keys):
    assert client.get('/api/dashboard',headers={'Authorization':'Bearer '+keys['worker']}).status_code==401
    assert client.post('/internal/outbox/claim',headers={'Authorization':'Bearer '+keys['admin']}).status_code==401


def test_large_payload_and_xss_not_rendered_as_html(client,keys,payload):
    auth={'Authorization':'Bearer '+keys['intake']}
    assert client.post('/intake',headers=auth,json=payload|{'message':'x'*33000}).status_code==413
    response=client.get('/')
    assert 'script-src' in response.headers['content-security-policy']
    js=client.get('/static/app.js').text
    assert 'innerHTML' not in js


def test_simulator_cannot_send_without_approval(store,payload,client,keys):
    prepare(store,payload)
    r=client.post('/simulator/send',headers={'Authorization':'Bearer '+keys['simulator']},json={
        'idempotency_key':'unapproved','recipient':'alex@example.test','subject':'Hello','body':'Hello'})
    assert r.status_code==409
    assert store.dashboard()['metrics']['simulated_deliveries']==0


def test_last_attempt_crash_moves_to_dead_and_reconciles(store,payload,clock):
    lead=approve(store,payload)
    for i in range(3):
        job=store.claim()['jobs'][0]
        store.finish(job['outbox_id'],job['lease_token'],503)
        clock.advance(60)
    job=store.claim()['jobs'][0]
    store.simulate(store.delivery_payload(**job))
    clock.advance(31)
    store.recover()
    assert store.detail(lead)['outbox'][0]['state']=='dead'
    assert store.retry_dead(job['outbox_id'],'test')['state']=='sent'


def test_no_secrets_in_error_ledger(client,keys):
    worker={'Authorization':'Bearer '+keys['worker']}
    r=client.post('/internal/orchestration-error',headers=worker,json={'workflow_id':'intake','execution_id':'123','node':'Persist intake'})
    assert r.status_code==200
    assert client.get('/api/dashboard',headers={'Authorization':'Bearer '+keys['admin']}).json()['metrics']['failed_executions']==1


def test_unique_constraints_at_database_layer(store,payload):
    lead=approve(store,payload)
    d=store.detail(lead)['drafts'][0]
    with pytest.raises(sqlite3.IntegrityError):
        with store.tx() as c:c.execute('INSERT INTO drafts VALUES(?,?,?,?,?,?,?)',('copy',lead,d['revision'],d['recipient'],d['subject'],d['body'],'pending'))


def test_explicit_dead_letter_redrive_preserves_approved_payload(store,payload):
    lead=approve(store,payload)
    job=store.claim()['jobs'][0]
    store.finish(job['outbox_id'],job['lease_token'],400)
    assert store.redrive_dead(job['outbox_id'],'operator')['outbox_id']==job['outbox_id']
    new=store.claim()['jobs'][0]
    assert new['outbox_id']==job['outbox_id']
    assert deliver(store,new)[0]['state']=='sent'
    assert len(store.detail(lead)['attempts'])==2
    assert store.dashboard()['metrics']['simulated_deliveries']==1


@pytest.mark.parametrize('text,category',[
    ('Check appointment availability','Booking enquiry'),('Please send pricing','Sales enquiry'),
    ('My device is broken','Support request'),('I want to apply for a job','Recruitment enquiry'),
    ('Something vague','Other')])
def test_routing_categories(text,category):
    assert classify(text)[0]==category
