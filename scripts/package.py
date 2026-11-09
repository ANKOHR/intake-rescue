"""Create a source-only ZIP and checksummed manifest. Never package local state."""
from pathlib import Path
import hashlib
import json
import os
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.runtime','.venv','node_modules','data','__pycache__','.pytest_cache'}
MANIFEST=ROOT/'evidence'/'PACKAGE-MANIFEST.json'


def included(path):
    rel=path.relative_to(ROOT)
    return (path.is_file() and not any(part in EXCLUDED for part in rel.parts)
            and path.name!='.env' and path.suffix not in ('.pyc','.db','.db-shm','.db-wal')
            and path!=MANIFEST)


files=[]
for folder,dirs,names in os.walk(ROOT):
    dirs[:]=[name for name in dirs if name not in EXCLUDED]
    files.extend(p for name in names if included(p:=Path(folder)/name))
files.sort(key=lambda p:p.as_posix())
# Bound traversal with explicit exclusions when inspecting the final list; secrets themselves
# are never read into a manifest. The ZIP is outside the repository to avoid recursive inclusion.
MANIFEST.parent.mkdir(exist_ok=True)
MANIFEST.write_text(json.dumps({'algorithm':'SHA-256','files':{
    p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
target=ROOT.parent/'Intake-Rescue-Sparrow-Works.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    for p in [*files,MANIFEST]:z.write(p,Path(ROOT.name)/p.relative_to(ROOT))
with zipfile.ZipFile(target) as z:
    bad=z.testzip()
    assert bad is None,bad
    assert all('/.env' not in name or name.endswith('/.env.example') for name in z.namelist())
print(json.dumps({'archive':target.name,'files':len(files)+1,'bytes':target.stat().st_size,
                  'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},indent=2))
