// One-shot Docker initializer. Never include generated credentials in the repository.
const fs = require('node:fs');
const cp = require('node:child_process');
const path = '/tmp/intake-rescue-credentials.json';
const run = args => cp.execFileSync('n8n',args,{stdio:'inherit'});
const credentials = ['intake','worker'].map(role=>({id:`ir-${role}-auth`,name:`Intake Rescue · ${role[0].toUpperCase()+role.slice(1)}`,type:'httpHeaderAuth',data:{name:'Authorization',value:`Bearer ${process.env[`IR_${role.toUpperCase()}_TOKEN`]}`}}));
try {
  fs.writeFileSync(path,JSON.stringify(credentials),{mode:0o600});
  run(['import:credentials',`--input=${path}`]);
} finally { if(fs.existsSync(path))fs.unlinkSync(path); }
run(['import:workflow','--separate','--input=/workflows']);
for(const id of ['ir-errors','ir-intake','ir-recovery','ir-delivery'])run(['publish:workflow',`--id=${id}`]);
