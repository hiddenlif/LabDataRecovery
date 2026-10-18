from copy import deepcopy
import pytest
from data import bridge, screening
from test_07_recovery import command, setup
from test_08_identity import campaign, envelope


def test_analysis_failure_leaves_no_stage_or_run(client):
    c=client.create()
    data=bridge(); data['records'][0]['method']='unknown'
    client.import_data(c,data)
    job=client.command('job-submit','--db',client.db,'--campaign',c)['job']
    token=command(client,'job-claim',job,worker='w')['token']
    command(client,'job-compute',job,token,ok=False)
    assert client.sql('SELECT staged FROM jobs')[0]['staged'] is None
    assert client.sql('SELECT * FROM runs')==[]


def test_completed_job_rejects_wrong_token(client):
    _,job=setup(client)
    token=command(client,'job-claim',job,worker='w')['token']
    command(client,'job-compute',job,token); command(client,'job-publish',job,token)
    command(client,'job-publish',job,'wrong',ok=False)
    assert len(client.sql("SELECT * FROM events WHERE action='job_published'"))==1


@pytest.mark.parametrize('variant',['duplicate_entity','records','telemetry','alphabet'])
def test_invalid_campaign_envelopes_are_rejected(client,variant):
    data=envelope(campaign('A'))
    if variant=='duplicate_entity': data['campaigns'][0]['entities']*=2
    elif variant=='alphabet': data['campaigns'][0]['entities'][0]['value']='ABCD'
    else: data[variant]=[]
    client.analyze(data,ok=False)


def test_sequence_unknown_stop_symbols_and_legacy_names(client):
    result=client.analyze(envelope(campaign('A','ACDEX*'),campaign('B','a c d e x *')))
    assert len(result['compounds'])==1
    assert result['identity_catalog'][0]['value']=='ACDEX*'
    flat=screening(123)
    assert client.analyze(flat)['compounds'][0]['compound']=='compound-123'
