"""Generate reviewable native n8n nodes; no credentials or tokens in exports."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = {'httpHeaderAuth': {'id':'ir-worker-auth','name':'Intake Rescue · Worker'}}
INTAKE = {'httpHeaderAuth': {'id':'ir-intake-auth','name':'Intake Rescue · Intake'}}


def node(name,kind,params,x,y=300,version=1,**extra):
    return dict(id=name.lower().replace(' ','-'),name=name,type='n8n-nodes-base.'+kind,
                typeVersion=version,position=[x,y],parameters=params,**extra)


def http(name,path,x,y=300,method='POST',body=None):
    params={'method':method,'url':"={{ $env.IR_API_URL + '"+path+"' }}",
            'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth',
            'options':{'timeout':10000}}
    if body:
        params.update(sendBody=True,specifyBody='json',jsonBody=body)
    return node(name,'httpRequest',params,x,y,4.2,credentials=WORKER,retryOnFail=True,maxTries=3,waitBetweenTries=1000)


def dynamic_http(name,endpoint,x):
    n=http(name,'',x)
    n['parameters']['url']="={{ $env.IR_API_URL + '/internal/leads/' + $json.lead_id + '/"+endpoint+"' }}"
    return n


def webhook(name,path,x,credential=WORKER,response='onReceived',y=180):
    return node(name,'webhook',{'httpMethod':'POST','path':path,'authentication':'headerAuth','responseMode':response,'options':{}},x,y,2,credentials=credential,webhookId='ir-'+name.replace(' ','-').lower())


def schedule(x=0):
    return node('Every 5 seconds','scheduleTrigger',{'rule':{'interval':[{'field':'seconds','secondsInterval':5}]}},x,420,1.2)


def split(name,field,x):
    return node(name,'splitOut',{'fieldToSplitOut':field,'options':{}},x,300,1)


def sticky(text,x,y,width=460,height=180):
    return node('Note '+str(x)+str(y),'stickyNote',{'content':text,'width':width,'height':height},x,y,1)


def write(id,name,nodes,edges,error=True):
    connections={}
    for source,target,*branch in edges:
        b=branch[0] if branch else 0
        main=connections.setdefault(source,{'main':[]})['main']
        while len(main)<=b: main.append([])
        main[b].append({'node':target,'type':'main','index':0})
    workflow={'id':id,'name':name,'active':False,'nodes':nodes,'connections':connections,
              'settings':{'executionOrder':'v1','saveDataErrorExecution':'none','saveDataSuccessExecution':'none',
                          'saveExecutionProgress':False,'timezone':'Europe/London','executionTimeout':60},
              'pinData':{},'tags':[]}
    if error: workflow['settings']['errorWorkflow']='ir-errors'
    (ROOT/'n8n'/f'{id}.json').write_text(json.dumps(workflow,indent=2)+'\n',encoding='utf-8')


def main():
    (ROOT/'n8n').mkdir(exist_ok=True)
    normalize=node('Extract source envelope','set',{'mode':'raw','jsonOutput':'={{ JSON.stringify($json.body) }}','options':{}},220,300,3.4)
    persist=http('Validate normalize and persist','/intake',440,body='={{ JSON.stringify($json) }}')
    persist['credentials']=INTAKE
    duplicate=node('Repeated submission?','if',{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict'},'conditions':[{'id':'duplicate','leftValue':'={{ $json.duplicate }}','rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}},660,300,2.2)
    qualify=dynamic_http('Qualify and route','qualify',900)
    draft=dynamic_http('Generate approval draft','draft',1120)
    respond=node('Return durable intake receipt','respondToWebhook',{'respondWith':'json','responseBody':"={{ JSON.stringify($('Validate normalize and persist').item.json) }}",'options':{}},1350,300,1.4)
    write('ir-intake','Intake Rescue · 01 Lead intake',[
        webhook('Authenticated enquiry','intake-rescue/enquiry',0,INTAKE,'responseNode',300),normalize,persist,duplicate,qualify,draft,respond,
        sticky('## Intake → human control\nEach source supplies a stable event_id. Validation and identity constraints commit atomically in SQLite.\nDuplicate events return the original receipt; conflicting event payloads fail.',200,20,650),
        sticky('## No send step here\nUncertain/invalid records → review.\nValid permissioned records → a pending draft.\nThe dashboard records a decision on the exact draft revision.',900,20,600)],
        [('Authenticated enquiry','Extract source envelope'),('Extract source envelope',persist['name']),(persist['name'],duplicate['name']),
         (duplicate['name'],respond['name'],0),(duplicate['name'],qualify['name'],1),(qualify['name'],draft['name']),(draft['name'],respond['name'])])
    recover=http('Recover expired delivery leases','/internal/recover',220)
    pending=http('Find interrupted intake stages','/internal/pending',440,method='GET')
    each=split('Each unfinished enquiry','leads',660)
    qualify=dynamic_http('Resume qualification','qualify',880)
    draft=dynamic_http('Resume draft generation','draft',1100)
    write('ir-recovery','Intake Rescue · 02 Interrupted intake recovery',[
        schedule(),webhook('Run recovery now','intake-rescue/recover',0),recover,pending,each,qualify,draft,
        sticky('## Durable resumption\nEvery 5 seconds (or authenticated manual tick): expire stale delivery leases, then resume received/qualified leads. Stage APIs are idempotent.\nReview and approval are never bypassed.',240,20,850)],
        [('Every 5 seconds',recover['name']),('Run recovery now',recover['name']),(recover['name'],pending['name']),(pending['name'],each['name']),(each['name'],qualify['name']),(qualify['name'],draft['name'])])
    claim=http('Claim one approved follow-up','/internal/outbox/claim',220)
    each=split('Each exclusively leased job','jobs',440)
    send=http('Call simulated delivery adapter','/internal/deliver',660,body='={{ JSON.stringify($json) }}')
    # Retries must be database scheduled; blindly retrying this node would reuse an expired lease.
    send['retryOnFail']=False
    branch=node('Delivery confirmed?','if',{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict'},'conditions':[{'id':'sent','leftValue':'={{ $json.state }}','rightValue':'sent','operator':{'type':'string','operation':'equals'}}],'combinator':'and'},'options':{}},880,300,2.2)
    success=node('Simulated receipt recorded','noOp',{},1100,220)
    retry=node('Retry or dead-letter stored','noOp',{},1100,420)
    write('ir-delivery','Intake Rescue · 03 Approved delivery and retries',[
        schedule(),webhook('Run delivery now','intake-rescue/deliver',0),claim,each,send,branch,success,retry,
        sticky('## Approval gate + leased outbox\nClaim succeeds only for a queued approved draft. One claim per tick. 30-second lease; HTTP timeout 5 seconds. Stable outbox ID is the provider idempotency key.',150,20,650),
        sticky('## Bounded retries\n429 / 5xx / transport failure → due_at + backoff.\n4 attempts maximum, then dead-letter.\nPermanent 4xx → manual attention. Never send directly from the dashboard.',900,20,560)],
        [('Every 5 seconds',claim['name']),('Run delivery now',claim['name']),(claim['name'],each['name']),(each['name'],send['name']),(send['name'],branch['name']),(branch['name'],success['name'],0),(branch['name'],retry['name'],1)])
    error=http('Record redacted execution failure','/internal/orchestration-error',260,
               body="={{ JSON.stringify({workflow_id:$json.workflow.id, execution_id:$json.execution.id || 'trigger', node:$json.execution.lastNodeExecuted || 'unknown'}) }}")
    write('ir-errors','Intake Rescue · 04 Orchestration error ledger',[
        node('Workflow failed','errorTrigger',{},0),error,
        sticky('## Redacted operational evidence\nStore workflow ID, execution ID and node name only. Raw exception bodies and payloads are deliberately excluded.\nIf the service is down, inspect n8n failed execution metadata.',0,20,660)],
        [('Workflow failed',error['name'])],error=False)


if __name__=='__main__': main()
