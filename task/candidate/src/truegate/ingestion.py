"""Durable source staging and atomic publication into ordinary study revisions."""
import hashlib
import re
import uuid
from .codec import require, text, integer, dumps, loads, digest
from .database import initialize, transaction
from .repository import get_campaign, event, now, store_dataset
from .instrument_files import parse
from .ingest_resolution import assemble
from .errors import WorkbenchError, Conflict


def manifest_contract(manifest):
    require(manifest, ['delivery_id','expected_revision','sources'], 'manifest')
    delivery = text(manifest['delivery_id'], 'delivery_id')
    if delivery != manifest['delivery_id']:
        raise WorkbenchError('delivery_id must be trimmed')
    integer(manifest['expected_revision'], 'expected_revision')
    if not isinstance(manifest['sources'], list) or not manifest['sources']:
        raise WorkbenchError('sources must be a nonempty array')
    seen = set()
    for source in manifest['sources']:
        require(source, ['id','kind','sha256'], 'source')
        identifier = text(source['id'], 'source id')
        if identifier != source['id'] or identifier in seen:
            raise WorkbenchError('Source IDs must be unique and trimmed')
        seen.add(identifier)
        if source['kind'] not in {'readings','telemetry','transfer_history'}:
            raise WorkbenchError('Source kind must be readings, telemetry or transfer_history')
        if not isinstance(source['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', source['sha256']):
            raise WorkbenchError('Source sha256 must be lowercase hexadecimal')
    if not any(s['kind'] == 'readings' for s in manifest['sources']):
        raise WorkbenchError('At least one readings source is required')
    if sum(s['kind']=='transfer_history' for s in manifest['sources']) > 1:
        raise WorkbenchError('A delivery accepts one complete transfer history source')
    # Source list order has no semantic meaning; all other supplied fields remain bound.
    return dict(manifest, sources=sorted(manifest['sources'], key=lambda s:s['id']))


def session_row(db, identifier):
    row = db.execute('SELECT * FROM ingest_sessions WHERE id=?', (identifier,)).fetchone()
    if row is None:
        raise WorkbenchError('Unknown ingestion session')
    if digest(loads(row['manifest'])) != row['manifest_sha']:
        raise Conflict('Stored manifest fingerprint mismatch')
    return row


def current_revision(db, campaign):
    return db.execute('SELECT COALESCE(MAX(revision),0) FROM datasets WHERE campaign=?', (campaign,)).fetchone()[0]


class Ingestion:
    def __init__(self, path):
        self.path = str(path)
        initialize(path)

    def open(self, campaign, manifest):
        manifest = manifest_contract(manifest)
        key = digest(manifest)
        with transaction(self.path) as db:
            if get_campaign(db, campaign)['kind'] != 'screening':
                raise WorkbenchError('Instrument ingestion requires a screening campaign')
            old = db.execute('SELECT * FROM ingest_sessions WHERE campaign=? AND delivery_key=?',
                             (campaign, manifest['delivery_id'])).fetchone()
            if old:
                if old['manifest_sha'] != key:
                    raise Conflict('Delivery identifier already binds another manifest')
                return {'session':old['id'], 'state':old['state'], 'reused':True}
            if current_revision(db, campaign) != manifest['expected_revision']:
                raise Conflict('Campaign revision changed before opening the delivery')
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO ingest_sessions VALUES (?,?,?,?,?,?,?,NULL,?)',
                       (identifier, campaign, manifest['delivery_id'], dumps(manifest), key,
                        manifest['expected_revision'], 'open', now()))
            for source in manifest['sources']:
                db.execute("INSERT INTO ingest_sources(session,source_id,state,diagnostics) VALUES (?,?,'pending','[]')",
                           (identifier, source['id']))
            event(db, campaign, 'ingest_opened', {'session':identifier, 'manifest_sha256':key})
            return {'session':identifier, 'state':'open', 'reused':False}

    def add(self, identifier, source_id, raw):
        if len(raw) > 20*1024*1024:
            raise WorkbenchError('Source exceeds 20 MiB')
        sha = hashlib.sha256(raw).hexdigest()
        with transaction(self.path) as db:
            session = session_row(db, identifier)
            if session['state'] != 'open':
                raise Conflict('Ingestion session is not open')
            manifest = loads(session['manifest'])
            spec = next((s for s in manifest['sources'] if s['id'] == source_id), None)
            if spec is None:
                raise WorkbenchError('Source is not declared in the manifest')
            previous = db.execute('SELECT * FROM ingest_sources WHERE session=? AND source_id=?',
                                  (identifier, source_id)).fetchone()
            if previous['state'] == 'accepted':
                if previous['sha'] != sha:
                    raise Conflict('An accepted source cannot be replaced')
                return {'source':source_id, 'state':'accepted', 'reused':True, 'diagnostics':[]}
            if sha != spec['sha256']:
                rows, errors = [], [{'line':0, 'error':'Source fingerprint differs from manifest'}]
            else:
                rows, errors = parse(raw, spec['kind'])
            state = 'rejected' if errors else 'accepted'
            db.execute('UPDATE ingest_sources SET state=?,raw=?,sha=?,parsed=?,diagnostics=? WHERE session=? AND source_id=?',
                       (state, raw, sha, dumps(rows), dumps(errors), identifier, source_id))
            db.execute('INSERT INTO ingest_attempts(session,source_id,sha,state,diagnostics) VALUES (?,?,?,?,?)',
                       (identifier, source_id, sha, state, dumps(errors)))
            return {'source':source_id, 'state':state, 'reused':False, 'rows':len(rows), 'diagnostics':errors}

    def show(self, identifier):
        with transaction(self.path) as db:
            session = dict(session_row(db, identifier))
            session['manifest'] = loads(session['manifest'])
            sources = [dict(r) for r in db.execute('SELECT source_id,state,sha,diagnostics FROM ingest_sources WHERE session=? ORDER BY source_id', (identifier,))]
            for source in sources:
                source['diagnostics'] = loads(source['diagnostics'])
            attempts = [dict(r) for r in db.execute('SELECT sequence,source_id,sha,state,diagnostics FROM ingest_attempts WHERE session=? ORDER BY sequence', (identifier,))]
            for attempt in attempts:
                attempt['diagnostics'] = loads(attempt['diagnostics'])
            session.update(sources=sources, attempts=attempts)
            return session

    def preview(self, identifier):
        with transaction(self.path) as db:
            session = session_row(db, identifier)
            if session['state'] == 'cancelled':
                raise Conflict('Ingestion session was cancelled')
            data = assemble(loads(session['manifest']), db.execute('SELECT * FROM ingest_sources WHERE session=?', (identifier,)).fetchall())
            return {'session':identifier, 'input_sha256':digest(data), 'input':data,
                    'base_current':current_revision(db, session['campaign']) == session['expected_revision']}

    def publish(self, identifier):
        with transaction(self.path) as db:
            session = session_row(db, identifier)
            if session['state'] == 'published':
                dataset = db.execute('SELECT * FROM datasets WHERE id=?', (session['published_dataset'],)).fetchone()
                return {'dataset':dataset['id'], 'revision':dataset['revision'], 'sha256':dataset['sha'], 'reused':True}
            if session['state'] != 'open':
                raise Conflict('Ingestion session is not open')
            if current_revision(db, session['campaign']) != session['expected_revision']:
                raise Conflict('Campaign advanced; open a delivery against the current revision')
            data = assemble(loads(session['manifest']), db.execute('SELECT * FROM ingest_sources WHERE session=?', (identifier,)).fetchall())
            result = store_dataset(db, session['campaign'], data)
            db.execute("UPDATE ingest_sessions SET state='published',published_dataset=? WHERE id=?", (result['dataset'], identifier))
            event(db, session['campaign'], 'ingest_published', {'session':identifier, 'dataset':result['dataset']})
            return result

    def cancel(self, identifier):
        with transaction(self.path) as db:
            session = session_row(db, identifier)
            if session['state'] == 'published':
                raise Conflict('Published evidence cannot be cancelled')
            if session['state'] != 'cancelled':
                db.execute("UPDATE ingest_sessions SET state='cancelled' WHERE id=?", (identifier,))
                event(db, session['campaign'], 'ingest_cancelled', {'session':identifier})
            return {'session':identifier, 'state':'cancelled'}
