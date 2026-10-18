"""Build pinned verifier inputs and bind a local runtime inventory."""
from pathlib import Path
import subprocess,json,os,tempfile,hashlib
ROOT=Path(__file__).resolve().parents[1]
subprocess.run(['python3',str(ROOT/'tools/verify_files.py')],check=True)
subprocess.run(['docker','info'],check=True,capture_output=True)
env=os.environ.copy()
with tempfile.TemporaryDirectory(prefix='truegate-buildx-') as directory:
    env['BUILDX_CONFIG']=directory
    subprocess.run(['docker','build','-t','truegate-screening-evidence-verifier:0.7.3',str(ROOT/'validation')],check=True,env=env)
image=subprocess.check_output(['docker','image','inspect','truegate-screening-evidence-verifier:0.7.3','--format','{{.Id}}'],text=True).strip()
inventory=json.loads((ROOT/'validation/expected-cases.json').read_text())
inventory['image_id']=image
inventory['build_provenance']={'package_inventory_sha256':hashlib.sha256((ROOT/'SHA256SUMS.json').read_bytes()).hexdigest(),'dockerfile_sha256':hashlib.sha256((ROOT/'validation/Dockerfile').read_bytes()).hexdigest(),'note':'Local build from verified packaged inputs; historical receipt bindings are unchanged.'}
(ROOT/'validation/runtime-inventory.local.json').write_text(json.dumps(inventory,indent=2)+'\n')
print('Built local verifier:',image)
