"""Recover suppressed delivery revisions from immutable bytes and publication order."""
import hashlib
import os
from pathlib import Path
import sqlite3
from .codec import loads, dumps, digest
from .errors import WorkbenchError
from .ingest_resolution import assemble
from .repository import event, now

VERSION='transfer-evidence-v1'
ACTION='transfer_evidence_recovered_v1'


def rows(db,query,args=()):
    return [dict(row) for row in db.execute(query,args)]


def plan(db):
    """Audit published dataset links before attempting retained-delivery recovery."""
    studies=[]
    for campaign in rows(db,'SELECT id FROM campaigns ORDER BY id'):
        cid=campaign['id']
        entry=dict(campaign=cid,status='unaffected',sessions=[],jobs=[],
                   runs=[dict(run=r['id'],dataset=r['dataset'],action='preserved') for r in rows(db,'SELECT id,dataset FROM runs WHERE campaign=? ORDER BY id',(cid,))],
                   decisions=[dict(decision=d['id'],run=d['run'],action='preserved') for d in rows(db,'SELECT id,run FROM decisions WHERE campaign=? ORDER BY id',(cid,))],unresolved=[])
        studies.append(entry)
        for session in rows(db,"SELECT * FROM ingest_sessions WHERE campaign=? AND state='published'",(cid,)):
            if not db.execute('SELECT id FROM datasets WHERE id=?',(session['published_dataset'],)).fetchone():
                entry['status']='blocked';entry['unresolved'].append(dict(reason='Published dataset link is absent'))
    return studies


def public(studies,mode,backup=None):
    return dict(version=VERSION,mode=mode,backup=str(backup) if backup else None,
                studies=[{k:v for k,v in entry.items() if not k.startswith('_')} for entry in studies])


def recover(path,dry_run=False,backup=None):
    path=Path(path).resolve()
    if not path.is_file():raise WorkbenchError('An existing database is required')
    db=sqlite3.connect('file:'+str(path)+'?mode='+('ro' if dry_run else 'rw'),uri=True,isolation_level=None,timeout=30)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN' if dry_run else 'BEGIN IMMEDIATE')
        studies=plan(db)
        if dry_run:
            db.rollback();return public(studies,'dry_run')
        if backup is None:raise WorkbenchError('Apply requires a new backup destination')
        backup=Path(backup).resolve()
        if backup==path or backup.exists():raise WorkbenchError('Choose a new backup destination')
        backup.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        # A separate reader can snapshot while this connection holds the write reservation.
        reader=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
        destination=sqlite3.connect(str(backup))
        try:reader.backup(destination)
        finally:destination.close();reader.close()
        for entry in studies:
            if entry['status']!='recoverable':continue
            cid=entry['campaign']
            for correction in entry['sessions']:
                content=entry['_contents'][correction['session']]
                db.execute('INSERT INTO datasets VALUES (?,?,?,?,?,?)',(correction['to_dataset'],cid,correction['revision'],correction['sha256'],dumps(content),now()))
                db.execute('UPDATE ingest_sessions SET published_dataset=? WHERE id=?',(correction['to_dataset'],correction['session']))
            for job in entry['jobs']:
                db.execute("UPDATE jobs SET dataset=? WHERE id=? AND state='queued'",(job['to_dataset'],job['job']))
            entry['status']='recovered'
            event(db,cid,ACTION,{k:v for k,v in entry.items() if not k.startswith('_')})
        db.commit();return public(studies,'apply',backup)
    except BaseException:
        db.rollback();raise
    finally:db.close()
