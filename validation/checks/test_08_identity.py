from assertions import equivalent, report_text
from copy import deepcopy
import json
import pytest
from data import screening


def campaign(name,value='ACDE',local='compound-91',registry=None,target='CD19',kind='sequence'):
    d=screening()
    for row in d['records']:
        if row['role']=='sample': row['compound']=local
    entity={'local_id':local,'type':kind,'value':value,'target':target}
    if registry: entity['registry_id']=registry
    return {'id':name,'entities':[entity],'records':d['records'],'telemetry':d['telemetry']}


def envelope(*campaigns): return {'kind':'screening','campaigns':list(campaigns)}


def test_equal_identity_pools_aliases_and_keeps_plate_telemetry_local(client):
    a,b=campaign('A'),campaign('B','a c\nd e',local='different')
    b['telemetry'].append(dict(b['telemetry'][0],revision=2,status='failed'))
    data=envelope(a,b)
    result=client.analyze(data)
    assert len(result['compounds'])==1 and len(result['plates'])==8
    assert len(result['identity_catalog'][0]['aliases'])==2
    assert len(result['excluded'])==1
    sources={r['id']:r for r in result['source_records']}
    assert sources[result['excluded'][0]['id']]['campaign']=='B'
    assert len(sources)==len(a['records'])+len(b['records'])
    assert sum(c['n'] for c in result['compounds'][0]['channels'].values())==215
    data['campaigns'].reverse()
    for c in data['campaigns']:
        c['records'].reverse(); c['telemetry'].reverse()
    equivalent(client.analyze(data), result)


def test_distinct_constructs_and_targets_do_not_pool(client):
    result=client.analyze(envelope(campaign('A'),campaign('B','ACDF'),campaign('C',target='BCMA')))
    assert len(result['compounds'])==3
    assert all(c['channels']['primary']['n']==27 for c in result['compounds'])
    assert len(result['identity_catalog'])==3


def test_smiles_case_is_identity_significant(client):
    result=client.analyze(envelope(campaign('A','c1ccccc1',kind='smiles'),campaign('B','C1CCCCC1',kind='smiles')))
    assert len(result['compounds'])==2


def test_long_and_delimiter_like_identifiers_remain_distinct(client):
    a,b=campaign('A'*200,local='X'*200,registry='R'*200),campaign('B'*200,local='X'*200,registry='R'*200)
    for c in [a,b]:
        for row in c['records']:
            row['id']=row['id'].ljust(200,'x')
    result=client.analyze(envelope(a,b))
    assert len(result['compounds'])==1 and len(result['source_records'])==280
    assert len({r['id'] for r in result['source_records']})==280
    assert result['identity_catalog'][0]['aliases'][0]['registry_id']=='R'*200


@pytest.mark.parametrize('variant',['nested','global','undefined','duplicate'])
def test_identity_conflicts_are_atomic_import_failures(client,variant):
    a,b,c=campaign('A',registry='R1'),campaign('B',registry='R2'),campaign('C','ACDF')
    if variant=='global': b=campaign('B','ACDF',registry='R1')
    if variant=='undefined': b=campaign('B'); b['entities']=[]
    if variant=='duplicate': b=campaign('A')
    data=envelope(a,b,c)
    target=client.create('screening')
    client.command('import','--db',client.db,'--campaign',target,client.write('bad.json',data),ok=False)
    assert client.sql('SELECT * FROM datasets')==[]
    assert not client.sql("SELECT * FROM events WHERE action='imported'")


def test_original_envelope_and_identity_map_survive_export(client):
    original=envelope(campaign('A::B',local='C'),campaign('A',local='B::C'))
    # These pairs would alias if a delimiter were used as the namespace encoding.
    for row in original['campaigns'][1]['records']:
        row['id']='B::'+row['id']; row['plate']='B::'+row['plate']
    for event in original['campaigns'][1]['telemetry']:
        event['plate']='B::'+event['plate']
    c=client.create('screening')
    imported=client.import_data(c,original)
    run=client.run(c)
    assert run['analysis']['input_sha256']==imported['sha256']
    later=deepcopy(original)
    later['campaigns'][0]['entities'][0]['target']='different target'
    client.import_data(c,later)
    dest=client.directory/'identity-report'
    client.command('export','--db',client.db,'--campaign',c,'--run',run['run'],'--directory',dest)
    snapshot=json.loads((dest/'snapshot.json').read_text())
    assert snapshot['input']==original
    assert snapshot['superseded'] is True
    assert len(snapshot['analysis']['result']['source_records'])==280
    assert len({r['id'] for r in snapshot['analysis']['result']['source_records']})==280
    assert len(snapshot['analysis']['result']['plates'])==8
    visible = report_text((dest/'index.html').read_text())
    for fact in ['ACDE', 'CD19', 'sequence', 'A::B', 'B::C']:
        assert fact in visible, f'Missing identity fact in HTML: {fact}'
    client.command('verify-report',dest)
