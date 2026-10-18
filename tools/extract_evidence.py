"""Safely extract verified retained evidence into a new directory."""
from pathlib import Path
import sys,tarfile,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
if len(sys.argv)!=4 or sys.argv[1] not in {'trial-01','trial-02','trial-03'} or sys.argv[2] not in {'final','source-states'}:
    raise SystemExit('Usage: python3 tools/extract_evidence.py trial-01 final /absolute/new/directory')
trial=ROOT/'evidence/trials'/sys.argv[1];kind=sys.argv[2];target=Path(sys.argv[3]).expanduser().resolve()
if target.exists():raise SystemExit('Choose a new destination')
archive=trial/(kind+'.tar.gz');inventory=json.loads((trial/(kind+'-inventory.json')).read_text())
assert hashlib.sha256(archive.read_bytes()).hexdigest()==inventory['sha256']
with tarfile.open(archive,'r:gz') as data:
    members=data.getmembers()
    assert len(members)==len(inventory['files'])
    for m in members:
        rel=Path(m.name)
        assert m.isfile() and not rel.is_absolute() and '..' not in rel.parts
        content=data.extractfile(m).read()
        assert hashlib.sha256(content).hexdigest()==inventory['files'][m.name]
        out=target/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(content)
print('Verified evidence extracted to',target)
