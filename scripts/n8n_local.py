"""Run pinned n8n with project-local state, import credentials via a short-lived file."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from config import load, ROOT

env=dict(load())
env.setdefault('N8N_USER_FOLDER',str(ROOT/'.runtime'))
cli=env.get('IR_N8N_CLI',str(ROOT/'.runtime'/'node_modules'/'n8n'/'bin'/'n8n'))
command=['node',cli]
def run(*args):
    subprocess.run(command+list(args),env=env,cwd=ROOT,check=True)

mode=sys.argv[1] if len(sys.argv)>1 else 'start'
if mode=='import':
    credentials=[{'id':'ir-'+role+'-auth','name':'Intake Rescue · '+role.title(),'type':'httpHeaderAuth',
                  'data':{'name':'Authorization','value':'Bearer '+env['IR_'+role.upper()+'_TOKEN']}}
                 for role in ('intake','worker')]
    folder=ROOT/'.runtime'
    folder.mkdir(exist_ok=True)
    fd,path=tempfile.mkstemp(suffix='.json',dir=folder)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(credentials,f)
        run('import:credentials','--input='+path)
    finally:
        Path(path).unlink(missing_ok=True)
    run('import:workflow','--separate','--input='+str(ROOT/'n8n'))
    # Publishing registers these on the local instance only. No public deployment.
    for wid in ('ir-errors','ir-intake','ir-recovery','ir-delivery'):
        run('publish:workflow','--id='+wid)
else:
    run(*sys.argv[1:] if len(sys.argv)>1 else ['start'])
