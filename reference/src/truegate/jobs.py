"""Durable analysis leases with fencing and atomic publication into review history."""
import time
import uuid
from .database import initialize, transaction
from .repository import get_campaign, latest_dataset, event, now
from .codec import loads, dumps, digest, number, text
from .policy import resolve
from .errors import Conflict, WorkbenchError
from . import ENGINE_VERSION


def find(db, identifier):
    job = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
    if job is None:
        raise WorkbenchError("Unknown job")
    return job


def owner(job, token, clock):
    if job["state"] != "running" or job["token"] != token or job["lease_until"] <= clock:
        raise Conflict("Worker lease is absent, expired or superseded")


class Jobs:
    def __init__(self, path):
        self.path = str(path)
        initialize(self.path)

    def submit(self, campaign, policy=None):
        with transaction(self.path) as db:
            study = get_campaign(db, campaign)
            dataset = latest_dataset(db, campaign)
            settings = resolve(study["kind"], policy)
            key = digest(settings)
            row = db.execute("SELECT id FROM jobs WHERE campaign=? AND dataset=? AND policy_sha=? AND engine=?",
                             (campaign, dataset["id"], key, ENGINE_VERSION)).fetchone()
            if row:
                return {"job": row["id"], "reused": True}
            identifier = uuid.uuid4().hex
            db.execute("INSERT INTO jobs(id,campaign,dataset,policy_sha,policy,engine,state) VALUES (?,?,?,?,?,?,'queued')",
                       (identifier, campaign, dataset["id"], key, dumps(settings), ENGINE_VERSION))
            event(db, campaign, "job_submitted", {"job": identifier, "dataset": dataset["id"]})
            return {"job": identifier, "reused": False}

    def claim(self, identifier, worker, seconds=60):
        worker = text(worker, "worker")
        seconds = number(seconds, "lease seconds", 1, 3600)
        with transaction(self.path) as db:
            job, clock = find(db, identifier), time.time()
            if job["state"] == "complete":
                raise Conflict("Job is already complete")
            if job["state"] == "running" and job["lease_until"] > clock:
                raise Conflict("Job is held by an active worker")
            if job["state"] == "running":
                db.execute("UPDATE job_attempts SET state='expired',ended=? WHERE job=? AND generation=?",
                           (clock, identifier, job["generation"]))
            generation, token = job["generation"] + 1, uuid.uuid4().hex
            db.execute("UPDATE jobs SET state='running',generation=?,token=?,lease_until=?,staged=NULL WHERE id=?",
                       (generation, token, clock + seconds, identifier))
            db.execute("INSERT INTO job_attempts(job,generation,worker,token,started,state) VALUES (?,?,?,?,?,'running')",
                       (identifier, generation, worker, token, clock))
            event(db, job["campaign"], "job_claimed", {"job": identifier, "generation": generation, "worker": worker})
            return {"job": identifier, "token": token, "generation": generation, "lease_until": clock + seconds}

    def heartbeat(self, identifier, token, seconds=60):
        seconds = number(seconds, "lease seconds", 1, 3600)
        with transaction(self.path) as db:
            job, clock = find(db, identifier), time.time()
            owner(job, token, clock)
            expiry = max(job["lease_until"], clock + seconds)
            db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (expiry, identifier))
            return {"job": identifier, "lease_until": expiry}

    def compute(self, identifier, token):
        with transaction(self.path) as db:
            job = find(db, identifier)
            owner(job, token, time.time())
            if job["engine"] != ENGINE_VERSION:
                raise Conflict("Job belongs to a different analysis engine")
            dataset = db.execute("SELECT * FROM datasets WHERE id=?", (job["dataset"],)).fetchone()
            data, policy = loads(dataset["content"]), loads(job["policy"])
            if digest(data) != dataset["sha"] or digest(policy) != job["policy_sha"]:
                raise Conflict("Stored inputs do not match job fingerprints")
        from .engine import analyze
        result = analyze(data, policy)
        with transaction(self.path) as db:
            current = find(db, identifier)
            owner(current, token, time.time())
            db.execute("UPDATE jobs SET staged=? WHERE id=?", (dumps(result), identifier))
        return {"job": identifier, "staged": True}

    def publish(self, identifier, token):
        with transaction(self.path) as db:
            job, clock = find(db, identifier), time.time()
            if job["state"] == "complete" and job["token"] == token:
                return {"job": identifier, "run": job["published_run"], "reused": True}
            owner(job, token, clock)
            if job["staged"] is None:
                raise Conflict("Compute the result before publication")
            result = loads(job["staged"])
            dataset = db.execute("SELECT * FROM datasets WHERE id=?", (job["dataset"],)).fetchone()
            if (digest(loads(dataset["content"])) != dataset["sha"] or
                result["input_sha256"] != dataset["sha"] or result["policy_sha256"] != job["policy_sha"] or
                result["engine_version"] != job["engine"]):
                raise Conflict("Staged result does not match the pinned job inputs")
            existing = db.execute("SELECT * FROM runs WHERE campaign=? AND dataset=? AND policy_sha=? AND engine=?",
                                  (job["campaign"], job["dataset"], job["policy_sha"], job["engine"])).fetchone()
            if existing and existing["status"] != "complete":
                raise Conflict("A synchronous analysis already occupies this run key")
            run = existing["id"] if existing else uuid.uuid4().hex
            if not existing:
                db.execute("INSERT INTO runs(id,campaign,dataset,policy_sha,policy,engine,status,result,created,finished) VALUES (?,?,?,?,?,?,'complete',?,?,?)",
                           (run, job["campaign"], job["dataset"], job["policy_sha"], job["policy"], job["engine"], job["staged"], now(), now()))
            elif existing["result"] != job["staged"]:
                raise Conflict("Existing result differs from the staged result")
            db.execute("UPDATE jobs SET state='complete',published_run=?,staged=NULL WHERE id=?", (run, identifier))
            db.execute("UPDATE job_attempts SET state='complete',ended=? WHERE job=? AND generation=?", (clock, identifier, job["generation"]))
            event(db, job["campaign"], "job_published", {"job": identifier, "run": run, "generation": job["generation"]})
            return {"job": identifier, "run": run, "reused": bool(existing)}
