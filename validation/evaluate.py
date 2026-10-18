"""Run independent checks against a source checkout without exposing author files."""
import argparse
import hashlib
import json
import shutil
import stat
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
IMAGE = "truegate-screening-evidence-verifier:0.7.3"


def fingerprint(source):
    result = {}
    for path in sorted((source / "src").rglob("*.py")):
        if path.is_symlink():
            raise ValueError("Source symlinks are not accepted")
        result[str(path.relative_to(source))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def payload_fingerprint(source):
    """Bind executable resources and configuration as well as Python modules."""
    ignored = {'.git', '.venv', '__pycache__', '.pytest_cache', 'reports'}
    result = {}
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        if set(relative.parts) & ignored:
            continue
        if path.is_symlink():
            raise ValueError(f'Payload symlinks are not supported: {relative}')
        if path.is_file():
            result[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--checks", choices=["all", "01", "02", "03", "04", "05", "06", "07", "08", "10", "08-full", "10-full", "11", "11-full", "11r2", "11r2-full", "11r3", "11r3-full", "11r4", "11r4-full"], default="all")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    if not (source / "src/truegate/cli.py").is_file():
        parser.error("Source must contain src/truegate/cli.py")
    if args.output.exists():
        parser.error("Receipt directory already exists; choose a fresh location")
    subprocess.run(["docker", "info"], check=True, capture_output=True)
    if args.build:
        subprocess.run(["docker", "build", "-t", IMAGE, str(HERE)], check=True)
    image_id = subprocess.check_output(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True).strip()
    args.output.mkdir(parents=True, mode=0o700)
    output = args.output.resolve()
    before = fingerprint(source)
    payload_before = payload_fingerprint(source)
    modes_before = {p: stat.S_IMODE((source/p).stat().st_mode) for p in payload_before}
    snapshot = tempfile.TemporaryDirectory(prefix='truegate-evaluation-')
    mounted_source = Path(snapshot.name)
    mounted_source.chmod(0o755)
    for relative in payload_before:
        destination = mounted_source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    if payload_fingerprint(mounted_source) != payload_before:
        snapshot.cleanup()
        raise ValueError('Payload changed while copying evaluation snapshot')
    name = "truegate-check-" + uuid.uuid4().hex[:12]
    volume = name + "-receipts"
    subprocess.run(["docker", "volume", "create", volume], check=True, capture_output=True)
    command = ["docker", "run", "--name", name, "--network", "none", "--read-only",
               "--cpus", "2", "--memory", "1g", "--pids-limit", "96", "--cap-drop", "ALL",
               "--cap-add", "SETUID", "--cap-add", "SETGID", "--cap-add", "CHOWN",
               "--cap-add", "DAC_OVERRIDE", "--cap-add", "KILL", "--security-opt", "no-new-privileges",
               "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
               "--mount", f"type=bind,source={mounted_source},target=/candidate,readonly",
               "--mount", f"type=volume,source={volume},target=/receipt", image_id, args.checks]
    started = time.monotonic()
    with (output / "output.log").open("w") as log:
        try:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)
            exit_code = 124
        finally:
            copied = subprocess.run(["docker", "cp", name + ":/receipt/.", str(output)], capture_output=True, text=True)
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
            snapshot.cleanup()
    after = fingerprint(source)
    payload_after = payload_fingerprint(source)
    modes_after = {p: stat.S_IMODE((source/p).stat().st_mode) for p in payload_after}
    receipt_path = output / "result.json"
    result = json.loads(receipt_path.read_text()) if receipt_path.exists() else {"accepted": False, "infrastructure_error": "No trusted result"}
    result.update(container_exit_code=exit_code, image_id=image_id, source_files=before,
                  source_unchanged=before == after, payload_files=payload_before,
                  payload_modes=modes_before,
                  payload_unchanged=payload_before == payload_after and modes_before == modes_after,
                  source_snapshot='Only enumerated payload files are mounted; excluded directories are unavailable',
                  wall_seconds=round(time.monotonic() - started, 3),
                  trusted_receipts="native Docker volume, root-only, copied after container exit",
                  receipt_copy_exit_code=copied.returncode)
    result["accepted"] = bool(result.get("accepted") and exit_code == 0 and before == after and payload_before == payload_after and modes_before == modes_after and copied.returncode == 0)
    receipt_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"source_files", "payload_files", "payload_modes"}}, indent=2))
    raise SystemExit(0 if result["accepted"] else 1)


if __name__ == "__main__":
    main()
