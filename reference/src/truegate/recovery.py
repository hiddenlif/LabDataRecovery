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
    studies=[]
    for campaign in rows(db,'SELECT id FROM campaigns ORDER BY id'):
        cid=campaign['id']
        entry=dict(campaign=cid,status='unaffected',sessions=[],jobs=[],
                   runs=[dict(run=r['id'],dataset=r['dataset'],action='preserved') for r in rows(db,'SELECT id,dataset FROM runs WHERE campaign=? ORDER BY id',(cid,))],
                   decisions=[dict(decision=d['id'],run=d['run'],action='preserved') for d in rows(db,'SELECT id,run FROM decisions WHERE campaign=? ORDER BY id',(cid,))],unresolved=[])
        studies.append(entry)
        old=db.execute('SELECT payload FROM events WHERE campaign=? AND action=? ORDER BY id DESC LIMIT 1',(cid,ACTION)).fetchone()
        if old:
            previous=loads(old['payload']);previous['status']='already_recovered';studies[-1]=previous;continue
        published=rows(db,"SELECT * FROM ingest_sessions WHERE campaign=? AND state='published'",(cid,))
        if not published:continue
        events=rows(db,'SELECT * FROM events WHERE campaign=? ORDER BY id',(cid,))
        try:
            order={}
            for e in events:
                if e['action']=='ingest_published':
                    payload=loads(e['payload']);sid=payload['session']
                    if sid in order:raise WorkbenchError('Ambiguous delivery publication order')
                    order[sid]=(e['id'],payload['dataset'])
            prior=[]
            for e in events:
                if e['action']=='transfer_evidence_recovered_preview':
                    proof=loads(e['payload'])
                    if proof.get('version')!='transfer-evidence-preview-0':raise WorkbenchError('Unknown partial recovery version')
                    prior.append(proof)
            assembled=[]
            for session in published:
                sid=session['id']
                if sid not in order or order[sid][1]!=session['published_dataset']:
                    raise WorkbenchError('Missing or inconsistent delivery publication event')
                manifest=loads(session['manifest'])
                if digest(manifest)!=session['manifest_sha']:raise WorkbenchError('Manifest fingerprint mismatch')
                sources=rows(db,'SELECT * FROM ingest_sources WHERE session=?',(sid,))
                content=assemble(manifest,sources)
                stored=db.execute('SELECT * FROM datasets WHERE id=? AND campaign=?',(session['published_dataset'],cid)).fetchone()
                if not stored or digest(loads(stored['content']))!=stored['sha']:
                    raise WorkbenchError('Referenced dataset is missing or damaged')
                assembled.append((order[sid][0],session,content,digest(content),stored['sha']))
            assembled.sort(key=lambda row:row[0])
            mismatch=[a for a in assembled if a[3]!=a[4]]
            if not mismatch:continue
            last_publication=assembled[-1][0]
            if any(e['action']=='imported' and e['id']>last_publication for e in events):
                raise WorkbenchError('A later direct import prevents inferred current-revision recovery')
            revision=db.execute('SELECT MAX(revision) FROM datasets WHERE campaign=?',(cid,)).fetchone()[0]
            targets={}
            contents={}
            for sequence,session,content,sha,old_sha in assembled:
                sid=session['id'];target=session['published_dataset']
                if sha!=old_sha:
                    revision+=1;target='recovered-'+hashlib.sha256((cid+'\0'+sid).encode()).hexdigest()[:32]
                    if db.execute('SELECT id FROM datasets WHERE id=?',(target,)).fetchone():raise WorkbenchError('Recovered dataset identifier collision')
                    adopted=[]
                    for proof in prior:
                        for item in proof.get('sessions',[]):
                            if item['session']==sid:
                                row=db.execute('SELECT * FROM datasets WHERE id=? AND campaign=?',(item['to_dataset'],cid)).fetchone()
                                if item['from_dataset']!=session['published_dataset'] or item['sha256']!=sha or not row or row['sha']!=sha or digest(loads(row['content']))!=sha:
                                    raise WorkbenchError('Partial recovery provenance differs from retained input')
                                adopted.append(row)
                    if len({r['id'] for r in adopted})>1:raise WorkbenchError('Ambiguous adopted revisions')
                    allocated_revision=revision
                    if adopted:
                        target=adopted[0]['id'];allocated_revision=adopted[0]['revision'];revision-=1
                    entry['sessions'].append(dict(session=sid,from_dataset=session['published_dataset'],to_dataset=target,revision=allocated_revision,sha256=sha,adopted=bool(adopted)))
                    contents[sid]=content
                targets[sid]=target
            entry['current_dataset']=targets[assembled[-1][1]['id']]
            proposed={}
            jobs=rows(db,'SELECT * FROM jobs WHERE campaign=? ORDER BY id',(cid,))
            for job in jobs:
                target=job['dataset']
                if job['state']=='queued':
                    submissions=[e for e in events if e['action']=='job_submitted' and loads(e['payload']).get('job')==job['id']]
                    original=loads(submissions[0]['payload']).get('dataset') if len(submissions)==1 else None
                    justified=original==job['dataset'] or any(j.get('job')==job['id'] and j.get('from_dataset')==original and j.get('to_dataset')==job['dataset'] for proof in prior for j in proof.get('jobs',[]))
                    if len(submissions)!=1 or not justified:
                        raise WorkbenchError('Queued job lacks a unique consistent submission event')
                    if job['staged'] is not None:raise WorkbenchError('Queued job contains staged work')
                    preceding=[a for a in assembled if a[0]<submissions[0]['id']]
                    if preceding:
                        target=targets[preceding[-1][1]['id']]
                    if target!=job['dataset']:
                        entry['jobs'].append(dict(job=job['id'],from_dataset=job['dataset'],to_dataset=target))
                key=(target,job['policy_sha'],job['engine'])
                if key in proposed:raise WorkbenchError('Recovered job keys would collide')
                proposed[key]=job['id']
            entry['status']='recoverable'
            # Authoritative reconstructed content is internal, never a separate truth table.
            entry['_contents']=contents
        except (WorkbenchError,ValueError,KeyError,TypeError,OverflowError) as error:
            entry.update(status='blocked',sessions=[],jobs=[],unresolved=[dict(reason=str(error))])
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
                if not correction.get('adopted'):db.execute('INSERT INTO datasets VALUES (?,?,?,?,?,?)',(correction['to_dataset'],cid,correction['revision'],correction['sha256'],dumps(content),now()))
                db.execute('UPDATE ingest_sessions SET published_dataset=? WHERE id=?',(correction['to_dataset'],correction['session']))
            for job in entry['jobs']:
                db.execute("UPDATE jobs SET dataset=? WHERE id=? AND state='queued'",(job['to_dataset'],job['job']))
            entry['status']='recovered'
            event(db,cid,ACTION,{k:v for k,v in entry.items() if not k.startswith('_')})
        db.commit();return public(studies,'apply',backup)
    except BaseException:
        db.rollback();raise
    finally:db.close()
