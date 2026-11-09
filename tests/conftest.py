import pytest
from fastapi.testclient import TestClient
from app.domain import Store
from app.main import create_app


@pytest.fixture
def clock():
    class Clock:
        value = 1804800000.0
        def __call__(self):
            return self.value
        def advance(self, seconds=60):
            self.value += seconds
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return Store(tmp_path/'test.db',clock=clock)


@pytest.fixture
def payload():
    return {'source':'website','event_id':'evt-001','name':'Alex Example',
            'email':' Alex@Example.test ','phone':'07700 900123',
            'message':'Please send a quote for an intake workflow.', 'permission_to_reply':True}


@pytest.fixture
def keys():
    return {role: role+'-synthetic-unit-test-token-00000000' for role in ('admin','intake','worker','simulator')}


@pytest.fixture
def client(store,keys):
    with TestClient(create_app(store,keys)) as client:
        yield client


def prepare(store,payload):
    lead=store.ingest(payload)['lead_id']
    store.qualify(lead)
    store.draft(lead)
    return lead


def approve(store,payload):
    lead=prepare(store,payload)
    draft=store.detail(lead)['drafts'][0]['id']
    store.decide(lead,draft,'approve','test-operator')
    return lead
