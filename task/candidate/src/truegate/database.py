"""SQLite transaction boundaries and additive schema migrations."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3

MIGRATIONS = [
    """
    CREATE TABLE campaigns(id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL);
    CREATE TABLE datasets(id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaigns(id),
      revision INTEGER NOT NULL, sha TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL,
      UNIQUE(campaign, revision));
    CREATE TABLE runs(id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaigns(id),
      dataset TEXT NOT NULL REFERENCES datasets(id), policy_sha TEXT NOT NULL, policy TEXT NOT NULL,
      engine TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('running','complete','failed')),
      result TEXT, error TEXT, created TEXT NOT NULL, finished TEXT,
      UNIQUE(campaign,dataset,policy_sha,engine));
    CREATE TABLE decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, campaign TEXT NOT NULL REFERENCES campaigns(id),
      run TEXT NOT NULL REFERENCES runs(id), action TEXT NOT NULL, reviewer TEXT NOT NULL,
      note TEXT NOT NULL, created TEXT NOT NULL);
    """,
    """
    CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, campaign TEXT NOT NULL REFERENCES campaigns(id),
      action TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
    CREATE INDEX datasets_campaign_revision ON datasets(campaign,revision);
    CREATE INDEX decisions_campaign_id ON decisions(campaign,id);
    CREATE INDEX events_campaign_id ON events(campaign,id);
    """,
    """
    CREATE TABLE jobs(id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaigns(id),
      dataset TEXT NOT NULL REFERENCES datasets(id), policy_sha TEXT NOT NULL, policy TEXT NOT NULL,
      engine TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('queued','running','complete')),
      generation INTEGER NOT NULL DEFAULT 0, token TEXT, lease_until REAL,
      staged TEXT, published_run TEXT REFERENCES runs(id),
      UNIQUE(campaign,dataset,policy_sha,engine));
    CREATE TABLE job_attempts(job TEXT NOT NULL REFERENCES jobs(id), generation INTEGER NOT NULL,
      worker TEXT NOT NULL, token TEXT NOT NULL, started REAL NOT NULL, ended REAL,
      state TEXT NOT NULL CHECK(state IN ('running','expired','complete')),
      PRIMARY KEY(job,generation));
    """,
    """
    CREATE TABLE ingest_sessions(id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaigns(id),
      delivery_key TEXT NOT NULL, manifest TEXT NOT NULL, manifest_sha TEXT NOT NULL,
      expected_revision INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('open','published','cancelled')),
      published_dataset TEXT REFERENCES datasets(id), created TEXT NOT NULL, UNIQUE(campaign,delivery_key));
    CREATE TABLE ingest_sources(session TEXT NOT NULL REFERENCES ingest_sessions(id), source_id TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('pending','accepted','rejected')), raw BLOB, sha TEXT, parsed TEXT,
      diagnostics TEXT NOT NULL, PRIMARY KEY(session,source_id));
    CREATE TABLE ingest_attempts(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
      session TEXT NOT NULL, source_id TEXT NOT NULL, sha TEXT NOT NULL, state TEXT NOT NULL,
      diagnostics TEXT NOT NULL, FOREIGN KEY(session,source_id) REFERENCES ingest_sources(session,source_id));
    """,
]


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    return db


def initialize(path):
    with transaction(path) as db:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise ValueError("Database was written by a newer application")
        for i, migration in enumerate(MIGRATIONS[version:], start=version + 1):
            for statement in migration.split(";"):
                if statement.strip():
                    db.execute(statement)
            db.execute(f"PRAGMA user_version={i}")


@contextmanager
def transaction(path):
    db = connect(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

