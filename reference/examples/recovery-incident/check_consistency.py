"""Inspect retained evidence and waiting-work consistency on a database copy.

Run: PYTHONPATH=src python examples/recovery-incident/check_consistency.py COPY.db
Read-only diagnostics; incomplete coverage, not an acceptance oracle.
"""
import json, sqlite3, sys
from truegate.codec import loads, digest
from truegate.ingest_resolution import assemble

def inspect(path):
    violations=[];unresolved=[]
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for campaign, in db.execute('SELECT id FROM campaigns ORDER BY id'):
            events=[dict(r) for r in db.execute('SELECT * FROM events WHERE campaign=? ORDER BY id',(campaign,))]
            deliveries=[];local=[]
            try:
                publications=[e['id'] for e in events if e['action']=='ingest_published']
                if publications and any(e['action']=='imported' and e['id']>max(publications) for e in events):
                    raise ValueError('Later direct input requires review')
                for e in events:
                    if e['action']!='ingest_published':continue
                    sid=loads(e['payload'])['session']
                    session=db.execute('SELECT * FROM ingest_sessions WHERE id=?',(sid,)).fetchone()
                    manifest=loads(session['manifest'])
                    sources=[dict(r) for r in db.execute('SELECT * FROM ingest_sources WHERE session=?',(sid,))]
                    content=assemble(manifest,sources)
                    for descriptor in manifest['sources']:
                        if descriptor['kind']=='transfer_history':
                            model=loads(bytes(next(s for s in sources if s['source_id']==descriptor['id'])['raw']).decode('utf-8-sig'))
                            codec=descriptor.get('codec','transfer-history/2')
                            if codec=='transfer-history/1':
                                for binding in model['bindings']:binding['sequence']-=1
                            elif codec!='transfer-history/2':raise ValueError('Unsupported retained format')
                            content['transfer_history']=model
                    sha=digest(content)
                    linked=db.execute('SELECT sha FROM datasets WHERE id=?',(session['published_dataset'],)).fetchone()
                    deliveries.append((e['id'],sid,sha))
                    if linked is None or linked['sha']!=sha:local.append(dict(campaign=campaign,session=sid,check='retained-input-binding'))
                for job in db.execute("SELECT * FROM jobs WHERE campaign=? AND state='queued'",(campaign,)):
                    submitted=[e for e in events if e['action']=='job_submitted' and loads(e['payload']).get('job')==job['id']]
                    if len(submitted)!=1:raise ValueError('Ambiguous submission context')
                    prior=[d for d in deliveries if d[0]<submitted[0]['id']]
                    if prior:
                        row=db.execute('SELECT sha FROM datasets WHERE id=?',(job['dataset'],)).fetchone()
                        if not row or row['sha']!=prior[-1][2]:local.append(dict(campaign=campaign,job=job['id'],check='waiting-input-context'))
                violations.extend(local)
            except Exception as exc:
                unresolved.append(dict(campaign=campaign,error=str(exc)))
    return dict(violations=violations,unresolved=unresolved,scope='Partial read-only consistency diagnostics; unresolved evidence requires review')
if __name__=='__main__':
    report=inspect(sys.argv[1]);print(json.dumps(report,indent=2));sys.exit(bool(report['violations']))
