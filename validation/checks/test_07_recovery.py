import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from data import bridge


def submit(client, campaign):
    return client.command('job-submit', '--db', client.db, '--campaign', campaign)['job']


def command(client, verb, job, token=None, ok=True, **options):
    args = [verb, '--db', client.db, '--job', job]
    if token: args += ['--token', token]
    for key, value in options.items(): args += ['--' + key.replace('_','-'), value]
    return client.command(*args, ok=ok)


def setup(client):
    c = client.create()
    client.import_data(c, bridge())
    return c, submit(client,c)


def expire(client, job):
    # Controlled clock fault: change real persisted expiry, not the app's response.
    client.sql('UPDATE jobs SET lease_until=0 WHERE id=?', (job,))


def test_expired_stage_is_quarantined_and_old_worker_fenced(client):
    c, job = setup(client)
    old = command(client,'job-claim',job,worker='first')['token']
    command(client,'job-compute',job,old)
    assert client.sql('SELECT staged FROM jobs WHERE id=?',(job,))[0]['staged'] is not None
    assert client.sql('SELECT * FROM runs') == []
    command(client,'job-claim',job,worker='early',ok=False)
    expire(client,job)
    command(client,'job-heartbeat',job,old,ok=False)
    command(client,'job-publish',job,old,ok=False)
    new = command(client,'job-claim',job,worker='replacement')
    assert new['generation'] == 2 and new['token'] != old
    assert client.sql('SELECT staged FROM jobs WHERE id=?',(job,))[0]['staged'] is None
    for verb in ['job-compute','job-heartbeat','job-publish']:
        command(client,verb,job,old,ok=False)
    command(client,'job-publish',job,new['token'],ok=False)
    command(client,'job-compute',job,new['token'])
    run = command(client,'job-publish',job,new['token'])['run']
    assert command(client,'job-publish',job,new['token'])['run'] == run
    command(client,'job-claim',job,worker='late',ok=False)
    rows = client.sql('SELECT * FROM runs')
    assert len(rows) == 1 and rows[0]['status'] == 'complete'
    assert json.loads(rows[0]['result'])['result']['ratio'] == pytest.approx(1.04)
    assert [r['state'] for r in client.sql('SELECT state FROM job_attempts ORDER BY generation')] == ['expired','complete']
    assert len(client.sql("SELECT * FROM events WHERE action='job_published'")) == 1
    client.review(c,run,1)


def test_simultaneous_claims_have_one_winner(client):
    _, job = setup(client)
    base = ['job-claim','--db',client.db,'--job',job,'--worker']
    attempts = client.parallel([base+['alpha'],base+['beta']])
    assert sorted(r.returncode for r in attempts) == [0,2]
    assert len(client.sql("SELECT * FROM job_attempts WHERE state='running'")) == 1
    assert client.sql('SELECT generation FROM jobs')[0]['generation'] == 1


def test_job_pins_revision_and_policy_through_historical_export(client):
    c, job = setup(client)
    assert submit(client,c) == job
    lease = command(client,'job-claim',job,worker='worker')
    client.import_data(c,bridge([1.12]*8))
    second = submit(client,c)
    assert second != job
    command(client,'job-compute',job,lease['token'])
    run = command(client,'job-publish',job,lease['token'])['run']
    assert json.loads(client.sql('SELECT result FROM runs WHERE id=?',(run,))[0]['result'])['result']['ratio'] == pytest.approx(1.04)
    client.review(c,run,2,ok=False)
    destination = client.directory/'history'
    client.command('export','--db',client.db,'--campaign',c,'--run',run,'--directory',destination)
    snapshot=json.loads((destination/'snapshot.json').read_text())
    assert snapshot['superseded'] is True and snapshot['dataset_revision'] == 1
    assert snapshot['analysis']['result']['ratio'] == pytest.approx(1.04)
    policy = client.write('other-policy.json',{'equivalence_high':1.3})
    third=client.command('job-submit','--db',client.db,'--campaign',c,'--policy',policy)['job']
    assert third not in {job,second}


def test_heartbeat_and_synchronous_result_reuse(client):
    c, job = setup(client)
    run = client.run(c)['run']
    claim = command(client,'job-claim',job,worker='w',lease_seconds=60)
    extended = command(client,'job-heartbeat',job,claim['token'],lease_seconds=1)
    assert extended['lease_until'] >= claim['lease_until']
    command(client,'job-compute',job,claim['token'])
    assert command(client,'job-publish',job,claim['token'])['run'] == run
    assert len(client.sql('SELECT * FROM runs')) == 1
    expire(client,job)
    assert command(client,'job-publish',job,claim['token'])['run'] == run


def test_publication_rolls_back_if_attempt_transition_is_interrupted(client):
    _,job=setup(client)
    token=command(client,'job-claim',job,worker='w')['token']
    command(client,'job-compute',job,token)
    client.sql("CREATE TRIGGER publication_fault BEFORE UPDATE ON job_attempts WHEN NEW.state='complete' BEGIN SELECT RAISE(ABORT,'injected interruption'); END")
    command(client,'job-publish',job,token,ok=False)
    assert client.sql('SELECT * FROM runs')==[]
    assert client.sql("SELECT * FROM events WHERE action='job_published'")==[]
    assert client.sql('SELECT state FROM jobs')[0]['state']=='running'
    client.sql('DROP TRIGGER publication_fault')
    command(client,'job-publish',job,token)
    assert len(client.sql('SELECT * FROM runs'))==1


@pytest.mark.parametrize('seconds',[0,3601,float('inf')])
def test_invalid_lease_does_not_create_attempt(client,seconds):
    _,job=setup(client)
    command(client,'job-claim',job,worker='w',lease_seconds=seconds,ok=False)
    assert client.sql('SELECT * FROM job_attempts')==[]


def test_staged_fingerprint_tampering_blocks_publication(client):
    _,job=setup(client)
    token=command(client,'job-claim',job,worker='w')['token']
    command(client,'job-compute',job,token)
    staged=json.loads(client.sql('SELECT staged FROM jobs')[0]['staged'])
    staged['input_sha256']='wrong'
    client.sql('UPDATE jobs SET staged=?',(json.dumps(staged),))
    command(client,'job-publish',job,token,ok=False)
    assert client.sql('SELECT * FROM runs')==[]


def test_migration_preserves_existing_analysis_and_review(client):
    c=client.create(); client.import_data(c,bridge())
    run=client.run(c)['run']; client.review(c,run,1)
    before={t:client.sql('SELECT * FROM '+t) for t in ['datasets','runs','decisions']}
    for table in ['ingest_attempts','ingest_sources','ingest_sessions']: client.sql('DROP TABLE '+table)
    client.sql('DROP TABLE job_attempts'); client.sql('DROP TABLE jobs'); client.sql('PRAGMA user_version=2')
    submit(client,c)
    assert client.sql('PRAGMA user_version')[0]['user_version']==4
    for table,rows in before.items(): assert client.sql('SELECT * FROM '+table)==rows


@pytest.mark.parametrize('state',['running','different'])
def test_conflicting_synchronous_run_prevents_publication(client,state):
    c,job=setup(client)
    token=command(client,'job-claim',job,worker='w')['token']
    command(client,'job-compute',job,token)
    client.run(c)
    if state=='running': client.sql("UPDATE runs SET status='running',result=NULL")
    else: client.sql("UPDATE runs SET result='{}'")
    command(client,'job-publish',job,token,ok=False)
    assert client.sql('SELECT state FROM jobs')[0]['state']=='running'
    assert len(client.sql('SELECT * FROM runs'))==1
    assert not client.sql("SELECT * FROM events WHERE action='job_published'")


@pytest.mark.parametrize('field,value',[('engine','unavailable'),('policy_sha','wrong')])
def test_corrupt_pinned_job_cannot_compute(client,field,value):
    _,job=setup(client)
    token=command(client,'job-claim',job,worker='w')['token']
    client.sql('UPDATE jobs SET '+field+'=? WHERE id=?',(value,job))
    command(client,'job-compute',job,token,ok=False)
    assert client.sql('SELECT staged FROM jobs')[0]['staged'] is None
    assert not client.sql('SELECT * FROM runs')
