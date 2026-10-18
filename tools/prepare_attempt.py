"""Export only the public candidate, verifying the task manifest first."""
from pathlib import Path
import sys,json,hashlib,shutil
ROOT=Path(__file__).resolve().parents[1]
if len(sys.argv)!=2:raise SystemExit('Usage: python3 tools/prepare_attempt.py /absolute/fresh/workspace')
target=Path(sys.argv[1]).expanduser().resolve()
if target==ROOT or target.is_relative_to(ROOT):raise SystemExit('Choose a workspace outside the author repository')
if target.exists():raise SystemExit('Choose a new destination')
manifest=json.loads((ROOT/'task/manifest.json').read_text())
source=ROOT/'task/candidate'
for rel,sha in manifest['candidate_files'].items():
    p=source/rel
    if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:raise SystemExit('Candidate hash mismatch: '+rel)
target.mkdir(parents=True)
for rel in manifest['candidate_files']:
    p=target/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/rel,p)
print('Public-only task prepared:',target)
