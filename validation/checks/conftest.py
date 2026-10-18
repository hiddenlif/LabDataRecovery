import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import pytest
import signal
import time
import sqlite3
from concurrent.futures import ThreadPoolExecutor


def stop_uid(uid):
    # Each client has its own UID. Include descendants that changed sessions.
    if os.getuid() != 0:
        raise RuntimeError("Verifier requires root supervision and unprivileged candidate execution")
    for attempt in range(100):
        found = []
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                fields = dict(line.split(':', 1) for line in (proc/'status').read_text().splitlines() if ':' in line)
                if int(fields['Uid'].split()[0]) == uid and not fields['State'].strip().startswith('Z'):
                    found.append(int(proc.name))
            except (FileNotFoundError, ProcessLookupError, KeyError):
                pass
        if not found:
            return
        for pid in found:
            try: os.kill(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        time.sleep(.01)
    raise RuntimeError("Candidate descendants survived cleanup")


class Client:
    def __init__(self, directory, uid):
        self.directory = directory
        self.db = str(directory / "studies.db")
        self.uid = uid

    def write(self, name, value):
        path = self.directory / name
        path.write_text(json.dumps(value, allow_nan=False))
        path.chmod(0o644)
        return str(path)

    def raw(self, args):
        entry = os.environ.get("TG_ENTRY", str(Path(__file__).parents[1] / "entry.py"))
        env = {"PATH": os.environ.get("PATH", ""), "TG_SOURCE": os.environ["TG_SOURCE"],
               "HOME": str(self.directory), "PYTHONDONTWRITEBYTECODE": "1",
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        read_fd, write_fd = os.pipe()
        def restrict():
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
            resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024, 64*1024*1024))
            resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
            if os.getuid() != 0:
                raise RuntimeError("Refusing privileged or unsupervised candidate execution")
            os.setgroups([]); os.setgid(self.uid); os.setuid(self.uid)
            os.write(write_fd,json.dumps({'uid':os.getuid(),'gid':os.getgid(),'groups':os.getgroups()}).encode())
            os.close(write_fd)
        try:
            with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
                completed = subprocess.run([sys.executable, "-I", entry, *map(str, args)], cwd=self.directory,
                                           env=env, stdout=stdout, stderr=stderr, timeout=45,
                                           preexec_fn=restrict, pass_fds=(write_fd,))
                stdout.seek(0); stderr.seek(0)
                out,err=stdout.read(16*1024*1024+1),stderr.read(16*1024*1024+1)
                assert max(len(out),len(err)) <= 16*1024*1024, 'Candidate output exceeded capture limit'
                result=subprocess.CompletedProcess(completed.args,completed.returncode,out.decode(),err.decode())
        finally:
            os.close(write_fd)
            observed=os.read(read_fd,4096)
            os.close(read_fd)
        witness=json.loads(observed)
        assert witness=={'uid':self.uid,'gid':self.uid,'groups':[]}
        with open('/receipt/launch-witnesses.jsonl','a') as stream:
            stream.write(json.dumps(witness)+'\n')
        return result

    def command(self, *args, ok=True):
        try:
            result = self.raw(args)
        finally:
            stop_uid(self.uid)
        if ok:
            assert result.returncode == 0, result.stderr[-2000:]
            return json.loads(result.stdout)
        assert result.returncode == 2, result.stderr[-2000:]
        assert isinstance(json.loads(result.stderr).get('error'),str), 'Expected a documented error response'
        return result

    def parallel(self, commands):
        try:
            with ThreadPoolExecutor(max_workers=len(commands)) as pool:
                return list(pool.map(self.raw, commands))
        finally:
            stop_uid(self.uid)

    def sql(self, query, params=()):
        assert not self.directory.is_symlink() and not Path(self.db).is_symlink()
        with sqlite3.connect(self.db) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(query, params)]

    def analyze(self, data, policy=None, ok=True):
        path = self.write("input.json", data)
        args = ["analyze", path]
        if policy is not None:
            args += ["--policy", self.write("policy.json", policy)]
        output = self.command(*args, ok=ok)
        return output["result"] if ok else output

    def create(self, kind="bridge"):
        return self.command("create", "--db", self.db, "--name", "Independent verification", "--kind", kind)["campaign"]

    def import_data(self, campaign, data):
        return self.command("import", "--db", self.db, "--campaign", campaign, self.write("import.json", data))

    def run(self, campaign, policy=None):
        args = ["run", "--db", self.db, "--campaign", campaign]
        if policy:
            args += ["--policy", self.write("run-policy.json", policy)]
        return self.command(*args)

    def show(self, campaign):
        return self.command("show", "--db", self.db, "--campaign", campaign)

    def review(self, campaign, run, revision, ok=True):
        return self.command("review", "--db", self.db, "--campaign", campaign, "--run", run,
                            "--revision", revision, "--action", "accept", "--reviewer", "Review fixture",
                            "--note", "Checked independent example", ok=ok)


@pytest.fixture
def client():
    directory = Path(tempfile.mkdtemp(prefix="truegate-check-", dir="/tmp"))
    directory.chmod(0o755)
    uid = 20000 + next(UIDS)
    assert os.getuid() == 0, "Run these checks through the Docker verifier"
    os.chown(directory, uid, uid)
    yield Client(directory, uid)
    stop_uid(uid)
    shutil.rmtree(directory, ignore_errors=True)


import itertools
UIDS = itertools.count()

