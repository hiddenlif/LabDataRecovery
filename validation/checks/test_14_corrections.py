"""Coupled correction decisions using original evidence and version-bound studies."""
from copy import deepcopy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import pytest
from assertions import report_text
from test_11_ingestion import stage, command as ingest_command
from test_07_recovery import command as job_command, submit

FIXTURE=Path(__file__).parent/'fixtures/correction-incident'


def data(name='initial.json'):
    return json.loads((FIXTURE/name).read_text())


def existing(client):
    shutil.copyfile(FIXTURE/'study.db',client.db)
    os.chown(client.db,client.uid,client.uid)
    return json.loads((FIXTURE/'identifiers.json').read_text())


def early(analysis):
    return next(b for b in analysis['result']['transfer_history'][0]['bindings'] if b['record_id']=='early')


def export_snapshot(client,campaign,run,name):
    destination=client.directory/name
    client.command('export','--db',client.db,'--campaign',campaign,'--run',run,'--directory',destination)
    assert client.command('verify-report',destination)['verified']
    return json.loads((destination/'snapshot.json').read_text()),destination


@pytest.mark.parametrize('initial_volume,corrected_volume',[(20,15),(26,18)])
def test_equal_doses_do_not_reuse_changed_evidence_or_review(client,initial_volume,corrected_volume):
    first=data();changed=data('corrected.json')
    first['transfer_history']['events'][0]['volume']=initial_volume
    changed['transfer_history']['events'][0]['volume']=corrected_volume
    # Retain the original revision record with matching original volume.
    changed['transfer_history']['events'][-1]['volume']=initial_volume
    c=client.create('screening');one=client.import_data(c,first)
    old=client.run(c);client.review(c,old['run'],1)
    two=client.import_data(c,changed)
    assert two['revision']==2 and not two['reused'], 'Equal measured concentrations do not identify the same input evidence'
    assert two['dataset']!=one['dataset'] and two['sha256']!=one['sha256']
    assert client.show(c)['current_review'] is None
    client.review(c,old['run'],1,ok=False)
    new=client.run(c);client.review(c,new['run'],2)
    assert early(old['analysis'])['dose_um']==pytest.approx(100)
    assert early(new['analysis'])['dose_um']==pytest.approx(100)
    assert early(new['analysis'])['volume_ul']==pytest.approx(corrected_volume)
    repeat=client.import_data(c,changed)
    assert repeat['reused'] and repeat['dataset']==two['dataset']
    assert client.show(c)['current_review']['run']==new['run']


def test_queued_compute_keeps_the_original_equal_dose_history(client):
    ids=existing(client);job=ids['queued_job']
    token=job_command(client,'job-claim',job,worker='later')['token']
    job_command(client,'job-compute',job,token)
    staged=json.loads(client.sql('SELECT staged FROM jobs WHERE id=?',(job,))[0]['staged'])
    binding=early(staged)
    assert binding['volume_ul']==pytest.approx(20), 'Pinned fingerprint cannot label the current revision\'s physical evidence'
    assert binding['lineage']==[{'id':'load','revision':1}]
    original=client.sql('SELECT sha FROM datasets WHERE revision=1')[0]['sha']
    assert staged['input_sha256']==original
    observations=[o for c in staged['result']['compounds'] for ch in c['channels'].values() for o in ch['observations']]
    assert observations and all(o['transfer_binding']['volume_ul']==pytest.approx(20 if o['id']=='early' else 15) for o in observations)


def test_delayed_publication_reuses_pinned_run_without_displacing_current_review(client):
    ids=existing(client);job=ids['queued_job'];c=ids['campaign']
    before=client.show(c)['current_review']
    token=job_command(client,'job-claim',job,worker='later')['token']
    job_command(client,'job-compute',job,token)
    published=job_command(client,'job-publish',job,token)
    assert published['run']==ids['previous_run'] and published['reused']
    assert job_command(client,'job-publish',job,token)==published
    assert client.show(c)['current_review']==before
    assert client.sql("SELECT COUNT(*) AS n FROM runs WHERE status='complete'")[0]['n']==2


def test_historical_exports_retain_the_complete_previous_result(client):
    ids=existing(client);c=ids['campaign']
    original=json.loads(client.sql('SELECT result FROM runs WHERE id=?',(ids['previous_run'],))[0]['result'])
    snapshot,directory=export_snapshot(client,c,ids['previous_run'],'prior-report')
    assert snapshot['superseded'] and snapshot['dataset_revision']==1
    assert snapshot['input']==data()
    assert snapshot['analysis']==original, 'Historical result is not a live projection of the newest equal-dose input'
    assert early(snapshot['analysis'])['volume_ul']==pytest.approx(20)
    assert 'evidence-1' in report_text((directory/'index.html').read_text())
    rows=list(csv.DictReader((directory/'transfer-bindings.csv').open()))
    row=next(row for row in rows if 'early' in row.values())
    assert 'evidence-1' in row.values() and 'intermediate' in row.values()
    parsed=[]
    for value in row.values():
        try:parsed.append(json.loads(value))
        except (ValueError,TypeError):pass
    assert [{'id':'load','revision':1}] in parsed
    assert any(isinstance(x,(int,float)) and not isinstance(x,bool) and x==20 for x in parsed)


def test_a_precomputed_job_stays_publishable_after_an_equal_dose_correction(client):
    c=client.create('screening');client.import_data(c,data());job=submit(client,c)
    token=job_command(client,'job-claim',job,worker='early')['token']
    job_command(client,'job-compute',job,token)
    client.import_data(c,data('corrected.json'))
    old=job_command(client,'job-publish',job,token)['run']
    current=client.run(c);client.review(c,current['run'],2)
    snapshot,_=export_snapshot(client,c,old,'computed-before-correction')
    assert snapshot['superseded'] and early(snapshot['analysis'])['volume_ul']==pytest.approx(20)
    assert client.show(c)['current_review']['run']==current['run']


def files(model):
    stream=io.StringIO(newline='')
    fields='id plate well revision assay role signal compound dose dose_unit'.split()
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    writer.writerows(dict(r,revision=1) for r in data()['records'])
    return {'readings':('readings',stream.getvalue().encode()),'history':('transfer_history',(json.dumps(model)+'\n').encode())}


def test_source_acceptance_and_complete_delivery_identity_are_distinct(client):
    ids=existing(client);c=ids['campaign'];before=client.show(c)
    invalid=deepcopy(data('corrected.json')['transfer_history'])
    invalid['bindings'][1]['record_id']='missing-reading'
    _,session,_=stage(client,files(invalid),campaign=c,name='unmatched',revision=2)
    assert all(s['state']=='accepted' for s in ingest_command(client,'show',session)['sources'])
    ingest_command(client,'publish',session,ok=False)
    # Opening/staging is allowed to record its own evidence; failed publication is not.
    after=client.show(c)
    assert after['datasets']==before['datasets'] and after['current_review']==before['current_review']
    assert not client.sql("SELECT * FROM events WHERE action='ingest_published'")
    valid=deepcopy(data('corrected.json')['transfer_history'])
    _,legal,_=stage(client,files(valid),campaign=c,name='matched',revision=2)
    published=ingest_command(client,'publish',legal)
    assert published['revision']==3 and client.show(c)['current_review'] is None
    preview=ingest_command(client,'preview',legal)
    stored=json.loads(client.sql('SELECT content FROM datasets WHERE id=?',(published['dataset'],))[0]['content'])
    assert stored==preview['input']
    assert {s['text'].encode() for s in stored['ingestion']['sources']}=={v[1] for v in files(valid).values()}
    assert ingest_command(client,'publish',legal)['dataset']==published['dataset']


def test_unknown_evidence_and_resolved_overdraw_follow_different_paths(client):
    c=client.create('screening');unknown=data()
    operation=unknown['transfer_history']['events'][0]
    operation['status']='unknown';operation.pop('volume');operation.pop('volume_unit')
    client.import_data(c,unknown);job=submit(client,c)
    token=job_command(client,'job-claim',job,worker='unknown-first')['token']
    client.import_data(c,data('corrected.json'))
    job_command(client,'job-compute',job,token)
    old=job_command(client,'job-publish',job,token)['run']
    snap,_=export_snapshot(client,c,old,'unknown-history')
    assert early(snap['analysis'])['status']=='unknown' and early(snap['analysis'])['dose_um'] is None
    impossible=data('corrected.json');impossible['transfer_history']['events'][0]['volume']=10
    before=client.show(c)
    path=client.write('impossible.json',impossible)
    client.command('import','--db',client.db,'--campaign',c,path,ok=False)
    assert client.show(c)==before
    assert client.run(c)['analysis']['input_sha256']==client.sql('SELECT sha FROM datasets WHERE revision=2')[0]['sha']
