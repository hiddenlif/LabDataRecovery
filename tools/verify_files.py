"""Verify packaged file hashes; --write explicitly refreshes the upload inventory."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'SHA256SUMS.json'
IGNORED={'.git','.venv','__pycache__','.pytest_cache','local-runs'}
def files():
    result={}
    for p in sorted(ROOT.rglob('*')):
        rel=p.relative_to(ROOT)
        if any(k in IGNORED for k in rel.parts) or p.name.endswith('.local.json') or p==MANIFEST:continue
        if p.is_symlink():raise SystemExit('Unexpected symlink: '+str(rel))
        if p.is_file():result[str(rel)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result
if '--write' in sys.argv:
    MANIFEST.write_text(json.dumps(files(),indent=2)+'\n')
expected=json.loads(MANIFEST.read_text())
for rel,sha in expected.items():
    p=ROOT/rel
    if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
        raise SystemExit('Package differs from upload inventory: '+rel)
print('Verified',len(expected),'packaged files')
