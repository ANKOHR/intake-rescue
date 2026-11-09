import hmac
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .domain import Problem, Store


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    draft_id: str
    decision: str
    simulation_faults: list[int] | None = Field(default=None,max_length=10)


class Job(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outbox_id: str
    lease_token: str


class Fault(BaseModel):
    statuses: list[int] = Field(max_length=10)


def create_app(store=None, secrets=None, transport=None):
    keys = secrets or {role:os.environ.get('IR_' + role.upper() + '_TOKEN','')
                       for role in ('intake','worker','admin','simulator')}
    if any(len(v)<24 for v in keys.values()) or len(set(keys.values())) != 4:
        raise RuntimeError('Four distinct IR_*_TOKEN values of at least 24 characters are required')
    db = store or Store(os.environ.get('IR_DATABASE','data/intake.db'),
                        base_delay=int(os.environ.get('IR_BASE_DELAY','5')),
                        lease_seconds=int(os.environ.get('IR_LEASE_SECONDS','30')))
    provider_url = os.environ.get('IR_SIMULATOR_URL','http://127.0.0.1:8765/simulator/send')
    parsed = urlsplit(provider_url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.path != '/simulator/send':
        raise RuntimeError('Only the loopback simulated provider is supported')
    app = FastAPI(title='Sparrow Works · Intake Rescue', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = db

    @app.exception_handler(Problem)
    async def problem_handler(request, exc):
        return JSONResponse({'error':exc.code}, status_code=exc.status)

    @app.middleware('http')
    async def guard(request: Request, call_next):
        path = request.url.path
        role = ('admin' if path.startswith('/api/') else
                'worker' if path.startswith('/internal/') else
                'simulator' if path.startswith('/simulator/') else
                'intake' if path == '/intake' else None)
        if role and not hmac.compare_digest(request.headers.get('authorization',''), 'Bearer ' + keys[role]):
            return JSONResponse({'error':'unauthorized'}, status_code=401)
        if request.method in ('POST','PATCH','PUT'):
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 32768:
                    return JSONResponse({'error':'payload_too_large'}, status_code=413)
                chunks.append(chunk)
            # Starlette caches the body for downstream JSON parsing.
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def actor(request):
        value = request.headers.get('x-operator','')
        if not re.fullmatch(r'[A-Za-z0-9_. -]{1,80}', value):
            raise Problem(422, 'operator_name_required')
        return value

    @app.get('/health')
    def health():
        with db.connect() as c:
            c.execute('SELECT 1').fetchone()
        return {'status':'ok','delivery_mode':'simulated'}

    @app.post('/intake')
    def intake(payload: dict):
        return db.ingest(payload)

    @app.post('/internal/leads/{lead_id}/qualify')
    def qualify(lead_id: str):
        return db.qualify(lead_id)

    @app.post('/internal/leads/{lead_id}/draft')
    def draft(lead_id: str):
        return db.draft(lead_id)

    @app.get('/internal/pending')
    def pending():
        return db.pending()

    @app.post('/internal/recover')
    def recover():
        return db.recover()

    @app.post('/internal/orchestration-error')
    def orchestration_error(payload: dict):
        # Never retain the raw n8n exception: it may contain request data or headers.
        def safe(key):
            value = payload.get(key,'unknown')
            return re.sub(r'[^A-Za-z0-9_. -]', '', str(value))[:100]
        with db.tx() as c:
            c.execute('INSERT INTO orchestration_failures(workflow_id,execution_id,node,created_at) VALUES(?,?,?,?)',
                      (safe('workflow_id'),safe('execution_id'),safe('node'),db.clock()))
        return {'recorded':True}

    @app.post('/internal/outbox/claim')
    def claim():
        return db.claim()

    @app.post('/internal/deliver')
    def deliver(job: Job):
        payload = db.delivery_payload(job.outbox_id,job.lease_token)
        status, retry_after = 0, 0
        try:
            with httpx.Client(transport=transport,timeout=5,follow_redirects=False) as client:
                r = client.post(provider_url,json=payload,headers={'Authorization':'Bearer ' + keys['simulator']})
                status = r.status_code
                try:
                    retry_after = float(r.headers.get('retry-after','0'))
                    if not 0 <= retry_after <= 3600:
                        retry_after = 0
                except ValueError:
                    retry_after = 0
        except httpx.RequestError:
            pass
        return db.finish(job.outbox_id,job.lease_token,status,retry_after)

    @app.post('/simulator/send')
    def simulate(payload: dict):
        if set(payload) != {'idempotency_key','recipient','subject','body'} or any(not isinstance(v,str) for v in payload.values()):
            raise Problem(422,'invalid_simulator_payload')
        status, body = db.simulate(payload)
        return JSONResponse(body,status_code=status,headers={'Retry-After':'5'} if status==429 else {})

    @app.get('/api/dashboard')
    def dashboard():
        return db.dashboard()

    @app.get('/api/leads/{lead_id}')
    def detail(lead_id: str):
        return db.detail(lead_id)

    @app.patch('/api/leads/{lead_id}')
    def correct(lead_id: str, patch: dict, request: Request):
        return db.correct(lead_id,patch,actor(request))

    @app.post('/api/leads/{lead_id}/decision')
    def decision(lead_id: str, payload: Decision, request: Request):
        return db.decide(lead_id,payload.draft_id,payload.decision,actor(request),payload.simulation_faults)

    @app.post('/api/outbox/{outbox_id}/fault')
    def fault(outbox_id: str, payload: Fault, request: Request):
        actor(request)
        db.set_fault(outbox_id,payload.statuses)
        return {'configured':True}

    @app.post('/api/outbox/{outbox_id}/reconcile')
    def reconcile(outbox_id: str, request: Request):
        return db.retry_dead(outbox_id,actor(request))

    @app.post('/api/outbox/{outbox_id}/redrive')
    def redrive(outbox_id: str, payload: dict, request: Request):
        if payload != {'confirm':'retry-approved-draft'}:
            raise Problem(422,'explicit_redrive_confirmation_required')
        return db.redrive_dead(outbox_id,actor(request))

    static = Path(__file__).with_name('static')
    app.mount('/static',StaticFiles(directory=static),name='static')

    @app.get('/')
    def index():
        return FileResponse(static/'index.html')

    return app
