"""Validate deliverable completeness, evidence, local links and accidental secret inclusion."""
from pathlib import Path
import json
import os
import re
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
excluded={'.git','.runtime','.venv','node_modules','data','__pycache__','.pytest_cache'}
files=[]
for folder,dirs,names in os.walk(ROOT):
    dirs[:]=[name for name in dirs if name not in excluded]
    files.extend(Path(folder)/name for name in names if name!='.env' and not name.endswith('.pyc'))

for required in ['README.md','compose.yaml','.env.example','Dockerfile','runtime/package-lock.json',
                 'app/migrations/001_initial.sql','docs/ARCHITECTURE.md','docs/SECURITY-AND-FAILURES.md',
                 'docs/HANDOVER.md','docs/TEST-RESULTS.md','docs/LIMITATIONS.md','docs/CASE-STUDY.md',
                 'docs/DEMO.md','docs/CLIENT-EXPLANATION.md','evidence/browser-qa.json']:
    assert (ROOT/required).is_file(),required

for file in files:
    if file.suffix=='.md':
        for link in re.findall(r'\]\(([^)]+)\)',file.read_text(encoding='utf-8')):
            if '://' not in link and not link.startswith('#'):
                assert (file.parent/link.split('#')[0]).exists(),(file.relative_to(ROOT),link)

for file in (ROOT/'n8n').glob('*.json'):
    workflow=json.loads(file.read_text(encoding='utf-8'))
    names={n['name'] for n in workflow['nodes']}
    for source,connection in workflow['connections'].items():
        assert source in names
        for outputs in connection['main']:
            assert all(edge['node'] in names for edge in outputs)
    assert workflow['active'] is False,'Exports must not silently activate on import'

suite=ET.parse(ROOT/'evidence'/'unit-tests.xml').getroot().find('testsuite')
assert int(suite.attrib['tests'])==49 and suite.attrib['failures']=='0' and suite.attrib['errors']=='0'
runtime=json.loads((ROOT/'evidence'/'n8n-integration.json').read_text())
assert len(runtime['results'])==14 and all(r['result']=='PASS' for r in runtime['results'])
restart=json.loads((ROOT/'evidence'/'process-restart.json').read_text())
assert restart['result']=='PASS' and restart['provider_receipts_for_key']==1

# Scan only deliverable candidates. Keep private values out of diagnostics.
secrets=[]
if (ROOT/'.env').exists():
    for line in (ROOT/'.env').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key,value=line.split('=',1)
            if key.endswith('_TOKEN') or key=='N8N_ENCRYPTION_KEY':secrets.append(value)
owner=ROOT/'.runtime'/'owner.json'
if owner.exists():secrets.append(json.loads(owner.read_text())['password'])
for file in files:
    content=file.read_bytes()
    assert not any(value and value.encode() in content for value in secrets),('private value in deliverable',file.relative_to(ROOT))

print(json.dumps({'result':'PASS','deliverable_files_checked':len(files),'unit_tests':49,
                  'real_n8n_scenarios':14,'actual_restart':'PASS','markdown_links':'PASS',
                  'workflow_graphs':'PASS','private_value_scan':'PASS'},indent=2))
