import argparse
import json
import os
from pathlib import Path
import uuid
import httpx
from config import load, ROOT
load()
p=argparse.ArgumentParser()
p.add_argument('sample',nargs='?',default='valid-enquiry.json')
p.add_argument('--new-event',action='store_true',help='Create a distinct synthetic enquiry, including different content')
args=p.parse_args()
payload=json.loads((ROOT/'samples'/args.sample).read_text())
if args.new_event:
    suffix=uuid.uuid4().hex[:8]
    payload['event_id']+='-'+suffix
    payload['message']+=' Reference '+suffix+'.'
r=httpx.post('http://127.0.0.1:'+os.environ.get('N8N_PORT','5678')+'/webhook/intake-rescue/enquiry',
             json=payload,headers={'Authorization':'Bearer '+os.environ['IR_INTAKE_TOKEN']},timeout=30)
print(json.dumps({'status':r.status_code,'receipt':r.json()},indent=2))
r.raise_for_status()
