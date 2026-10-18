"""CLI and persisted-state checks; fixture bytes are generated independently."""
import csv
import io
import json
import hashlib
import copy
import pytest
from data import screening

HEADERS = {'readings':'id plate well revision assay role signal compound dose dose_unit'.split(),
           'telemetry':'plate well revision status actual_dose dose_unit'.split()}

def csv_bytes(kind, rows, bom=False):
    stream=io.StringIO(newline=''); writer=csv.DictWriter(stream,fieldnames=HEADERS[kind])
    writer.writeheader(); writer.writerows(rows)
    return ('\ufeff' if bom else '').encode()+stream.getvalue().encode()

def delivery(seed=91, corrected=False):
    data=screening(seed)
    readings=[dict(r,revision=1) for r in data['records']]
    files={'readings':('readings',csv_bytes('readings',readings,True)),
           'telemetry':('telemetry',csv_bytes('telemetry',data['telemetry']))}
    if corrected:
        row=next(r for r in readings if r['role']=='sample')
        files['correction']=('readings',csv_bytes('readings',[dict(row,revision=2,signal=row['signal']+3)]))
    return files

def opened(client, files, campaign=None, name='delivery', revision=0):
    campaign=campaign or client.create('screening')
    manifest={'delivery_id':name,'expected_revision':revision,'sources':[
        {'id':k,'kind':v[0],'sha256':hashlib.sha256(v[1]).hexdigest()} for k,v in files.items()]}
    result=client.command('ingest-open','--db',client.db,'--campaign',campaign,client.write(name+'.json',manifest))
    return campaign,result['session'],manifest

def command(client, verb, session, ok=True):
    return client.command('ingest-'+verb,'--db',client.db,'--session',session,ok=ok)

def add(client, session, source, raw, ok=True):
    path=client.directory/'source.csv';path.write_bytes(raw);path.chmod(0o644)
    return client.command('ingest-add','--db',client.db,'--session',session,'--source',source,path,ok=ok)

def stage(client, files, **kwargs):
    campaign,session,manifest=opened(client,files,**kwargs)
    for k,(_,raw) in files.items(): assert add(client,session,k,raw)['state']=='accepted'
    return campaign,session,manifest

def test_resume_rejected_attempt_and_incomplete_preview(client):
    files=delivery();c,s,m=opened(client,files)
    command(client,'preview',s,ok=False);command(client,'publish',s,ok=False)
    assert add(client,s,'readings',b'wrong')['state']=='rejected'
    assert add(client,s,'readings',files['readings'][1])['state']=='accepted'
    assert add(client,s,'readings',files['readings'][1])['reused']
    add(client,s,'readings',b'changed',ok=False)
    add(client,s,'unknown',b'x',ok=False)
    state=command(client,'show',s)
    assert [a['state'] for a in state['attempts']]==['rejected','accepted']
    assert len(client.sql('SELECT * FROM datasets'))==0
    assert opened(client,files,campaign=c)[1]==s
    add(client,s,'telemetry',files['telemetry'][1]);result=command(client,'publish',s)
    assert result['revision']==1
    assert command(client,'publish',s)['dataset']==result['dataset']
    assert len(client.sql("SELECT * FROM events WHERE action='ingest_published'"))==1


def test_corrections_arrival_order_and_exact_source_export(client):
    files=delivery(corrected=True);c,s,m=stage(client,files)
    preview=command(client,'preview',s)
    c2,s2,_=stage(client,dict(reversed(list(files.items()))))
    assert command(client,'preview',s2)['input_sha256']==preview['input_sha256']
    assert any(r['reading_revision']==2 for r in preview['input']['ingestion']['record_lineage'])
    published=command(client,'publish',s);run=client.run(c)['run'];client.review(c,run,1)
    destination=client.directory/'report'
    client.command('export','--db',client.db,'--campaign',c,'--run',run,'--directory',destination)
    snapshot=json.loads((destination/'snapshot.json').read_text())
    assert snapshot['input']==preview['input']
    for source in snapshot['input']['ingestion']['sources']:
        assert source['text'].encode()==files[source['id']][1]
        assert hashlib.sha256(source['text'].encode()).hexdigest()==source['sha256']
    from html import unescape
    html=unescape((destination/'index.html').read_text())
    assert m['delivery_id'] in html and all(r['record'] in html for r in preview['input']['ingestion']['record_lineage'])
    client.import_data(c,screening(98));assert client.show(c)['current_review'] is None
    assert command(client,'publish',s)['dataset']==published['dataset']
    command(client,'cancel',s,ok=False)


def test_publication_fault_is_atomic_and_retryable(client):
    c,s,_=stage(client,delivery())
    client.sql("CREATE TRIGGER ingestion_fault BEFORE UPDATE ON ingest_sessions WHEN NEW.state='published' BEGIN SELECT RAISE(ABORT,'interruption'); END")
    command(client,'publish',s,ok=False)
    assert not client.sql('SELECT * FROM datasets')
    assert not client.sql("SELECT * FROM events WHERE action IN ('imported','ingest_published')")
    assert command(client,'show',s)['state']=='open'
    client.sql('DROP TRIGGER ingestion_fault');assert command(client,'publish',s)['revision']==1


def test_competing_deliveries_have_one_publication(client):
    c,s,_=stage(client,delivery());_,t,_=stage(client,delivery(92),campaign=c,name='other')
    calls=[['ingest-publish','--db',client.db,'--session',x] for x in [s,t]]
    assert sorted(r.returncode for r in client.parallel(calls))==[0,2]
    assert len(client.sql('SELECT * FROM datasets'))==1
    loser=next(x for x in [s,t] if command(client,'show',x)['state']=='open')
    assert command(client,'preview',loser)['base_current'] is False
    command(client,'publish',loser,ok=False)


@pytest.mark.parametrize('damage',['bytes','cache','manifest'])
def test_publish_uses_bound_original_evidence(client,damage):
    _,s,_=stage(client,delivery());before=command(client,'preview',s)
    if damage=='bytes': client.sql("UPDATE ingest_sources SET raw=? WHERE source_id='readings'",(b'bad',))
    elif damage=='manifest': client.sql("UPDATE ingest_sessions SET manifest='{}'")
    else: client.sql("UPDATE ingest_sources SET parsed='[]'")
    if damage=='cache':
        assert command(client,'preview',s)['input_sha256']==before['input_sha256']
        command(client,'publish',s)
    else:
        command(client,'publish',s,ok=False);assert not client.sql('SELECT * FROM datasets')


def test_duplicate_and_conflicting_reading_revisions(client):
    files=delivery();files['duplicate']=files['readings'];c,s,_=stage(client,files)
    data=command(client,'preview',s)['input'];assert all(len(r['sources'])==2 for r in data['ingestion']['record_lineage'])
    changed=screening()['records'][0];files['conflict']=('readings',csv_bytes('readings',[dict(changed,revision=1,signal=changed['signal']+1)]))
    _,s2,_=stage(client,files,name='conflict',campaign=c)
    command(client,'preview',s2,ok=False);assert not client.sql('SELECT * FROM datasets')


@pytest.mark.parametrize('raw',[b'id,id\nx,x\n', b'\xff', b'id,plate,well,revision,assay,role,signal,compound,dose,dose_unit\nx,p,w,1,primary,sample,nan,c,1,uM\n'])
def test_bad_source_is_durable_rejection_not_partial_import(client,raw):
    files={'readings':('readings',raw)};_,s,_=opened(client,files)
    result=add(client,s,'readings',raw)
    assert result['state']=='rejected' and result['diagnostics']
    assert command(client,'show',s)['attempts'][0]['state']=='rejected'
    command(client,'publish',s,ok=False);assert not client.sql('SELECT * FROM datasets')


def test_cancelled_session_keeps_evidence_and_rejects_work(client):
    files=delivery();_,s,_=stage(client,files);before=command(client,'show',s)['attempts']
    command(client,'cancel',s);command(client,'cancel',s)
    for verb in ['preview','publish']: command(client,verb,s,ok=False)
    add(client,s,'readings',files['readings'][1],ok=False)
    assert command(client,'show',s)['attempts']==before
    assert len(client.sql("SELECT * FROM events WHERE action='ingest_cancelled'"))==1


def test_published_delivery_flows_through_leased_job(client):
    c,s,_=stage(client,delivery());command(client,'publish',s)
    job=client.command('job-submit','--db',client.db,'--campaign',c)['job']
    token=client.command('job-claim','--db',client.db,'--job',job,'--worker','ingest-worker')['token']
    for verb in ['job-compute','job-publish']:
        result=client.command(verb,'--db',client.db,'--job',job,'--token',token)
    stored=client.sql('SELECT result FROM runs WHERE id=?',(result['run'],))[0]
    assert json.loads(stored['result'])['result']['compounds'][0]['channels']['primary']['ic50_um']==pytest.approx(.75,rel=.002)


def test_schema_upgrade_preserves_existing_jobs_and_reviews(client):
    c=client.create();from data import bridge
    client.import_data(c,bridge());run=client.run(c)['run'];client.review(c,run,1)
    job=client.command('job-submit','--db',client.db,'--campaign',c)['job']
    before={t:client.sql('SELECT * FROM '+t) for t in ['datasets','runs','decisions','jobs']}
    for t in ['ingest_attempts','ingest_sources','ingest_sessions']:client.sql('DROP TABLE '+t)
    client.sql('PRAGMA user_version=3');client.show(c)
    assert client.sql('PRAGMA user_version')[0]['user_version']==4
    for t,rows in before.items(): assert client.sql('SELECT * FROM '+t)==rows

@pytest.mark.parametrize('kind,row',[
    ('readings',{'id':'c','plate':'p','well':'w','revision':1,'assay':'primary','role':'vehicle','signal':100,'compound':'hidden'}),
    ('telemetry',{'plate':'p','well':'w','revision':1,'status':'failed','actual_dose':2,'dose_unit':'uM'})])
def test_fields_that_should_be_empty_are_rejected(client,kind,row):
    files=delivery();raw=csv_bytes(kind,[row]);files['bad']=(kind,raw)
    _,s,_=opened(client,files);result=add(client,s,'bad',raw)
    assert result['state']=='rejected' and result['diagnostics'][0]['line']==2


def test_quoted_multiline_csv_reports_physical_line_and_accepts_reordered_columns(client):
    columns=list(reversed(HEADERS['readings']))
    row={'id':'r','plate':'p','well':'w','revision':1,'assay':'primary','role':'sample','signal':10,'compound':'compound,\ncontinued','dose':1,'dose_unit':'uM'}
    stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=columns);w.writeheader();w.writerow(row)
    raw=stream.getvalue().encode();_,s,_=opened(client,{'readings':('readings',raw)})
    assert add(client,s,'readings',raw)['state']=='accepted'
    assert command(client,'preview',s)['input']['records'][0]['compound']=='compound,\ncontinued'
    row['signal']='invalid';stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=columns);w.writeheader();w.writerow(row);raw=stream.getvalue().encode()
    _,t,_=opened(client,{'readings':('readings',raw)})
    result=add(client,t,'readings',raw)
    assert result['state']=='rejected' and result['diagnostics'][0]['line']==3


def test_conflicting_superseded_revision_and_telemetry_are_errors(client):
    files=delivery(corrected=True)
    row=next(r for r in screening()['records'] if r['role']=='sample')
    files['old-conflict']=('readings',csv_bytes('readings',[dict(row,revision=1,signal=row['signal']+1)]))
    _,s,_=stage(client,files);command(client,'preview',s,ok=False)
    files=delivery();event=screening()['telemetry'][0]
    files['transfer-conflict']=('telemetry',csv_bytes('telemetry',[dict(event,actual_dose=event['actual_dose']*2)]))
    _,t,_=stage(client,files);command(client,'publish',t,ok=False)


def test_large_revision_identity_is_not_rounded_through_float(client):
    files=delivery();rows=[dict(r,revision=9007199254740992) for r in screening()['records']]
    corrected=dict(rows[0],revision=9007199254740993,signal=rows[0]['signal']+1)
    files['readings']=('readings',csv_bytes('readings',rows+[corrected]))
    _,s,_=stage(client,files);data=command(client,'preview',s)['input']
    lineage=next(r for r in data['ingestion']['record_lineage'] if r['record']==corrected['id'])
    assert lineage['reading_revision']==9007199254740993
    assert next(r for r in data['records'] if r['id']==corrected['id'])['signal']==corrected['signal']
