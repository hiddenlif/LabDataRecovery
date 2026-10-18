"""Run public tests in an unprivileged, read-only, network-disabled container."""
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
subprocess.run(['docker','run','--rm','--network','none','--read-only','--user','65534:65534','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','96','--memory','1g','--cpus','2','--tmpfs','/tmp:rw,nosuid,nodev,size=128m,mode=1777','--mount',f'type=bind,source={ROOT / "application"},target=/app,readonly','--workdir','/app','--env','PYTHONPATH=/app/src','--entrypoint','python','truegate-screening-evidence-verifier:0.7.3','-m','pytest','tests','-q','-p','no:cacheprovider','--basetemp=/tmp/pytest'],check=True)
