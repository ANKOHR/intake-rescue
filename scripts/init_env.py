import secrets
from pathlib import Path
from config import ROOT

target=ROOT/'.env'
if target.exists():
    raise SystemExit('.env already exists; preserved')
template=(ROOT/'.env.example').read_text()
for key in ('IR_INTAKE_TOKEN','IR_WORKER_TOKEN','IR_ADMIN_TOKEN','IR_SIMULATOR_TOKEN','N8N_ENCRYPTION_KEY'):
    template=template.replace(key+'=GENERATE_ME',key+'='+secrets.token_urlsafe(36))
target.write_text(template,encoding='utf-8')
print('Generated .env with independent random local tokens. Keep it private.')
