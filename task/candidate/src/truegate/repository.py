"""Immutable input revisions, content-bound analyses and append-only review events."""
from datetime import datetime, timezone
import uuid
from .database import initialize, transaction
from .codec import dumps, loads, digest, text
from .schema import validate, KINDS
from .policy import resolve
from .errors import WorkbenchError, Conflict
from . import ENGINE_VERSION


def now():
    return datetime.now(timezone.utc).isoformat()


def event(db, campaign, action, payload):
    db.execute("INSERT INTO events(campaign,action,payload,created) VALUES (?,?,?,?)",
               (campaign, action, dumps(payload), now()))


def get_campaign(db, campaign):
    row = db.execute("SELECT * FROM campaigns WHERE id=?", (campaign,)).fetchone()
    if row is None:
        raise WorkbenchError("Unknown campaign")
    return row


def latest_dataset(db, campaign):
    row = db.execute("SELECT * FROM datasets WHERE campaign=? ORDER BY revision DESC LIMIT 1", (campaign,)).fetchone()
    if row is None:
        raise WorkbenchError("Campaign has no dataset")
    return row


def store_dataset(db, campaign, data):
    from .registry import normalize_input
    validate(normalize_input(data))
    sha = digest(data)
    study = get_campaign(db, campaign)
    if study["kind"] != data["kind"]:
        raise WorkbenchError("Dataset kind differs from campaign")
    latest = db.execute("SELECT * FROM datasets WHERE campaign=? ORDER BY revision DESC LIMIT 1", (campaign,)).fetchone()
    from .dispensing import measurement_key
    if latest and (latest["sha"] == sha or measurement_key(loads(latest["content"])) == measurement_key(data)):
        return {"dataset": latest["id"], "revision": latest["revision"], "sha256": latest["sha"], "reused": True}
    revision = latest["revision"] + 1 if latest else 1
    identifier = uuid.uuid4().hex
    db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?)", (identifier, campaign, revision, sha, dumps(data), now()))
    event(db, campaign, "imported", {"dataset": identifier, "revision": revision, "sha256": sha})
    return {"dataset": identifier, "revision": revision, "sha256": sha, "reused": False}


class Repository:
    def __init__(self, path):
        self.path = str(path)
        initialize(self.path)

    def create(self, name, kind):
        name = text(name, "campaign name")
        if kind not in KINDS:
            raise WorkbenchError("Unknown study kind")
        campaign = uuid.uuid4().hex
        with transaction(self.path) as db:
            db.execute("INSERT INTO campaigns VALUES (?,?,?,?)", (campaign, name, kind, now()))
            event(db, campaign, "created", {"kind": kind})
        return {"campaign": campaign, "name": name, "kind": kind}

    def import_data(self, campaign, data):
        with transaction(self.path) as db:
            return store_dataset(db, campaign, data)

    def run(self, campaign, policy=None):
        with transaction(self.path) as db:
            study = get_campaign(db, campaign)
            dataset = latest_dataset(db, campaign)
            settings = resolve(study["kind"], policy)
            key = digest(settings)
            old = db.execute("SELECT * FROM runs WHERE campaign=? AND dataset=? AND policy_sha=? AND engine=?",
                             (campaign, dataset["id"], key, ENGINE_VERSION)).fetchone()
            if old and old["status"] == "complete":
                return {"run": old["id"], "reused": True, "analysis": loads(old["result"])}
            if old and old["status"] == "running":
                raise Conflict("An identical analysis is already running")
            identifier = old["id"] if old else uuid.uuid4().hex
            if old:
                db.execute("UPDATE runs SET status='running',error=NULL,finished=NULL WHERE id=?", (identifier,))
            else:
                db.execute("INSERT INTO runs(id,campaign,dataset,policy_sha,policy,engine,status,created) VALUES (?,?,?,?,?,?,'running',?)",
                           (identifier, campaign, dataset["id"], key, dumps(settings), ENGINE_VERSION, now()))
            event(db, campaign, "analysis_started", {"run": identifier, "dataset": dataset["id"]})
        try:
            from .engine import analyze
            result = analyze(loads(dataset["content"]), settings)
        except Exception as exc:
            with transaction(self.path) as db:
                db.execute("UPDATE runs SET status='failed',error=?,finished=? WHERE id=?", (str(exc), now(), identifier))
                event(db, campaign, "analysis_failed", {"run": identifier, "error": str(exc)})
            raise
        with transaction(self.path) as db:
            db.execute("UPDATE runs SET status='complete',result=?,finished=? WHERE id=?", (dumps(result), now(), identifier))
            event(db, campaign, "analysis_completed", {"run": identifier, "result_sha256": digest(result)})
        return {"run": identifier, "reused": False, "analysis": result}

    def review(self, campaign, run, action, reviewer, note, expected_revision):
        if action not in {"accept", "hold", "reject"}:
            raise WorkbenchError("Review action must be accept, hold or reject")
        text(reviewer, "reviewer"); text(note, "review note")
        with transaction(self.path) as db:
            get_campaign(db, campaign)
            latest = latest_dataset(db, campaign)
            result = db.execute("SELECT * FROM runs WHERE id=? AND campaign=?", (run, campaign)).fetchone()
            if not result or result["status"] != "complete":
                raise WorkbenchError("A complete analysis from this campaign is required")
            if result["dataset"] != latest["id"] or expected_revision != latest["revision"]:
                raise Conflict("Dataset changed; refresh the campaign and analyze its current revision")
            cursor = db.execute("INSERT INTO decisions(campaign,run,action,reviewer,note,created) VALUES (?,?,?,?,?,?)",
                                (campaign, run, action, reviewer, note, now()))
            event(db, campaign, "reviewed", {"run": run, "decision": cursor.lastrowid, "action": action})
            return {"decision": cursor.lastrowid, "action": action, "run": run}

    def show(self, campaign):
        with transaction(self.path) as db:
            study = dict(get_campaign(db, campaign))
            datasets = [dict(r) for r in db.execute("SELECT id,revision,sha,created FROM datasets WHERE campaign=? ORDER BY revision", (campaign,))]
            runs = [dict(r) for r in db.execute("SELECT id,dataset,policy_sha,engine,status,error,created,finished FROM runs WHERE campaign=? ORDER BY created,id", (campaign,))]
            decisions = [dict(r) for r in db.execute("SELECT * FROM decisions WHERE campaign=? ORDER BY id", (campaign,))]
            latest_id = datasets[-1]["id"] if datasets else None
            current_runs = {r["id"] for r in runs if r["dataset"] == latest_id and r["status"] == "complete"}
            active = [d for d in decisions if d["run"] in current_runs]
            study.update(datasets=datasets, runs=runs, decisions=decisions,
                         current_review=active[-1] if active else None,
                         current_revision=datasets[-1]["revision"] if datasets else None,
                         events=[dict(r) for r in db.execute("SELECT * FROM events WHERE campaign=? ORDER BY id", (campaign,))])
            return study

    def snapshot(self, campaign, run):
        with transaction(self.path) as db:
            study = dict(get_campaign(db, campaign))
            result = db.execute("SELECT * FROM runs WHERE id=? AND campaign=?", (run, campaign)).fetchone()
            if not result or result["status"] != "complete":
                raise WorkbenchError("A complete analysis from this campaign is required")
            dataset = db.execute("SELECT * FROM datasets WHERE id=?", (result["dataset"],)).fetchone()
            if digest(loads(dataset["content"])) != dataset["sha"]:
                raise Conflict("Stored dataset content does not match its fingerprint")
            analysis = loads(result["result"])
            if analysis["input_sha256"] != dataset["sha"] or analysis["policy_sha256"] != result["policy_sha"]:
                raise Conflict("Analysis lineage does not match its recorded inputs")
            decision = db.execute("SELECT * FROM decisions WHERE campaign=? AND run=? ORDER BY id DESC LIMIT 1", (campaign, run)).fetchone()
            latest = latest_dataset(db, campaign)
            return {"campaign": study, "run": run, "dataset_revision": dataset["revision"],
                    "superseded": latest["id"] != dataset["id"], "input": loads(dataset["content"]),
                    "analysis": analysis, "review": dict(decision) if decision else None}

