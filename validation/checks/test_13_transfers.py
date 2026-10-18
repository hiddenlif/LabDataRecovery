"""Independent rational ledgers, temporal witnesses and persisted correction histories."""
from copy import deepcopy
from fractions import Fraction
import csv
import hashlib
import io
import json
import math
import random
import pytest
from data import screening
from assertions import equivalent, report_text


def vessel(key, qty=100, dose=0, compound='X'):
    return dict(id=key,volume=qty,volume_unit='uL',concentrations={compound:dose} if dose else {},concentration_unit='uM')


def event(key, seq, src, dst, qty, **kw):
    return dict(id=key,revision=kw.pop('revision',1),sequence=seq,source=src,destination=dst,
                status=kw.pop('status','ok'),volume=qty,volume_unit=kw.pop('volume_unit','uL'),**kw)


def dataset(model):
    rows=[dict(id=b['record_id'],plate='P',well='A'+str(i),assay='primary',role='sample',compound='X',dose=0,dose_unit='uM',signal=100)
          for i,b in enumerate(model['bindings'])]
    return dict(kind='screening',records=rows,transfer_history=model)


def small():
    model=dict(revision='A',vessels=[vessel('stock',100,1000),vessel('mix',90),vessel('readout',80)],
               events=[event('one',1,'stock','mix',5,status='partial'),event('two',2,'stock','mix',5),
                       event('serial',3,'mix','readout',20),event('later',4,'stock','mix',10)],
               bindings=[dict(record_id='early',vessel='mix',sequence=1),dict(record_id='middle',vessel='mix',sequence=2),dict(record_id='downstream',vessel='readout',sequence=3)])
    return dataset(model)


def preview(client, data):
    return client.command('transfer-preview',client.write('transfer.json',data))['histories']


def by_record(history): return {b['record_id']:b for b in history['bindings']}


def content_state(state):
    return dict(known=state['known'],volume_ul=state['volume_ul'],
                amounts_pmol=({k:v for k,v in state['amounts_pmol'].items() if v} if state['amounts_pmol'] is not None else None),
                lineage=state['lineage'])


def binding_state(binding):
    return dict(record_id=binding['record_id'],vessel=binding['vessel'],sequence=binding['sequence'],
                compound=binding['compound'],dose_um=binding['dose_um'],status=binding['status'],**content_state(binding))


def physical_history(history):
    return dict(steps=[dict(**{k:e[k] for k in ['id','revision','sequence','source','destination','status','volume_ul']},
                            source_state=content_state(e['source_state']),destination_state=content_state(e['destination_state'])) for e in history['steps']],
                bindings=[binding_state(b) for b in history['bindings']],
                final_vessels=[dict(id=v['id'],**content_state(v)) for v in history['final_vessels']])


def assert_state(actual, expected):
    qty, amounts = expected
    assert actual['known'] is True
    assert actual['volume_ul']==pytest.approx(float(qty),abs=1e-10)
    assert {c:v for c,v in actual['amounts_pmol'].items() if v}==pytest.approx({c:float(v) for c,v in amounts.items() if v},abs=1e-9)


@pytest.mark.parametrize('seed',[17,41,113,307,701])
def test_generated_histories_match_exact_rational_ledger(client,seed):
    rng=random.Random(seed)
    # Oracle stores concentration as rational amounts and applies explicit paired
    # debit/credit entries, without candidate imports or floating-point helpers.
    initial=[vessel('v'+str(i),rng.randrange(100,160),rng.randrange(1,12)) for i in range(5)]
    for v in initial:v['concentrations']['Y']=rng.randrange(1,9)
    ledger={v['id']:(Fraction(v['volume']),{c:Fraction(v['volume'])*value for c,value in v['concentrations'].items()}) for v in initial}
    ops,expected=[],[]
    for seq in range(1,19):
        src,dst=rng.sample(sorted(ledger),2);qty=Fraction(rng.randrange(1,8))
        oldv,olda=ledger[src];dv,da=ledger[dst]
        entries={c:amount*qty/oldv for c,amount in olda.items()}
        ledger[src]=(oldv-qty,{c:a-entries[c] for c,a in olda.items()})
        ledger[dst]=(dv+qty,{c:da.get(c,0)+entries.get(c,0) for c in set(da)|set(entries)})
        ops.append(event('op'+str(seq),seq,src,dst,int(qty)))
        expected.append((deepcopy(ledger[src]),deepcopy(ledger[dst])))
    data=dataset(dict(revision='generated',vessels=initial,events=ops,
                      bindings=[dict(record_id='r'+str(i),vessel='v'+str(i),sequence=18) for i in range(5)]))
    rng.shuffle(data['transfer_history']['events']);h=preview(client,data)[0]
    for step,(src,dst) in zip(h['steps'],expected):
        assert_state(step['source_state'],src);assert_state(step['destination_state'],dst)
    # Global conservation at the final boundary, independently of event ordering.
    assert sum(v['volume_ul'] for v in h['final_vessels'])==pytest.approx(sum(v['volume'] for v in initial))
    for compound in ['X','Y']:
        assert sum(v['amounts_pmol'].get(compound,0) for v in h['final_vessels'])==pytest.approx(sum(v['volume']*v['concentrations'][compound] for v in initial))


def test_binding_time_and_transitive_correction(client):
    data=small();a=preview(client,data)[0];b=by_record(a)
    assert b['early']['dose_um']==pytest.approx(5000/95)
    assert b['middle']['dose_um']==pytest.approx(100)
    assert b['downstream']['dose_um']==pytest.approx(20)
    assert {x['id'] for x in b['downstream']['lineage']}=={'one','two','serial'}
    assert 'later' not in {x['id'] for x in b['early']['lineage']}
    # Correct a historical physical amount, preserving distinct operation two.
    data['transfer_history']['revision']='B'
    data['transfer_history']['events'].append(event('one',1,'stock','mix',4,revision=2,status='partial'))
    c=by_record(preview(client,data)[0]);assert c['early']['dose_um']==pytest.approx(4000/94)
    assert c['middle']['dose_um']==pytest.approx(9000/99)
    assert c['downstream']['dose_um']==pytest.approx(1800/99)
    assert {x['id']:x['revision'] for x in c['downstream']['lineage']}=={'one':2,'two':1,'serial':1}


def test_duplicate_export_is_not_an_additional_physical_transfer(client):
    data=small();a=preview(client,data)[0]
    data['transfer_history']['events'].append(deepcopy(data['transfer_history']['events'][0]))
    h=preview(client,data)[0];equivalent(physical_history(h),physical_history(a))
    extra=event('extra',5,'stock','mix',5)
    data['transfer_history']['events'].append(extra)
    data['transfer_history']['bindings'].append(dict(record_id='new',vessel='mix',sequence=5))
    data['records'].append(dict(data['records'][0],id='new',well='new'))
    n=by_record(preview(client,data)[0]);equivalent(binding_state(n['early']),binding_state(by_record(a)['early']))
    assert n['new']['dose_um']>n['middle']['dose_um']


@pytest.mark.parametrize('status',['failed','cancelled'])
def test_failed_topup_does_not_undo_delivered_liquid(client,status):
    data=small();data['transfer_history']['events'].append(event('two',2,'stock','mix',0,revision=2,status=status))
    h=preview(client,data)[0];b=by_record(h)
    assert b['middle']['dose_um']==pytest.approx(b['early']['dose_um'])
    assert {x['id'] for x in b['middle']['lineage']}=={'one'}
    assert h['steps'][1]['status']==status


def test_unknown_contents_propagate_only_along_delivered_paths_and_can_be_corrected(client):
    data=small();data['transfer_history']['events'].append(dict(id='one',revision=2,sequence=1,source='stock',destination='mix',status='unknown'))
    b=by_record(preview(client,data)[0]);assert all(x['status']=='unknown' and x['dose_um'] is None for x in b.values())
    result=client.analyze(data)
    assert {e['reason'] for e in result['excluded']}=={'unknown_transfer'}
    assert all(p['dispense_mode']=='transfer_history' for p in result['plates'])
    assert all(not ch['observations'] for c in result['compounds'] for ch in c['channels'].values())
    data['transfer_history']['events'].append(event('one',1,'stock','mix',4,revision=3))
    b=by_record(preview(client,data)[0]);assert b['downstream']['dose_um']==pytest.approx(1800/99)
    data['transfer_history']['vessels'].append(vessel('independent',10,7))
    data['transfer_history']['events'].append(event('nothing',5,'mix','independent',0,status='failed'))
    data['transfer_history']['bindings'].append(dict(record_id='ind',vessel='independent',sequence=5))
    data['records'].append(dict(data['records'][0],id='ind',well='ind'))
    independent=by_record(preview(client,data)[0])['ind']
    assert independent['dose_um']==7 and independent['lineage']==[]


def test_unit_changes_and_temporal_return_transfers(client):
    data=small();m=data['transfer_history']
    # A temporal A->B->A history is legal, although the static graph is cyclic.
    m['events'].append(event('return',5,'mix','stock',2))
    baseline=preview(client,data)[0]
    for v in m['vessels']:
        v['volume']*=1000;v['volume_unit']='nL'
        v['concentrations']={c:x*1000 for c,x in v['concentrations'].items()};v['concentration_unit']='nM'
    for e in m['events']:e['volume']/=1000;e['volume_unit']='mL'
    m['vessels'].reverse();m['events'].reverse();m['bindings'].reverse();data['records'].reverse()
    changed=preview(client,data)[0]
    equivalent(physical_history(changed),physical_history(baseline))


@pytest.mark.parametrize('fault',['obsolete_conflict','change_identity','duplicate_sequence','unknown_vessel','overdraw','boolean_sequence','float_revision','negative_volume','unknown_with_volume','zero_success','nonzero_failure','duplicate_binding','control_binding','duplicate_vessel','binding_future','overflow','empty_solute','nonlist_events'])
def test_invalid_history_rejected_before_storage(client,fault):
    data=small();m=data['transfer_history'];e=m['events'][0]
    if fault=='obsolete_conflict':m['events'] += [dict(e,volume=3),dict(e,revision=2,volume=4)]
    elif fault=='change_identity':m['events'].append(dict(e,revision=2,source='readout'))
    elif fault=='duplicate_sequence':m['events'].append(dict(e,id='different'))
    elif fault=='unknown_vessel':e['source']='missing'
    elif fault=='overdraw':e['volume']=1000
    elif fault=='boolean_sequence':e['sequence']=True
    elif fault=='float_revision':e['revision']=1.0
    elif fault=='negative_volume':e['volume']=-1
    elif fault=='unknown_with_volume':e['status']='unknown'
    elif fault=='zero_success':e['volume']=0
    elif fault=='nonzero_failure':e['status']='failed'
    elif fault=='duplicate_binding':m['bindings'].append(deepcopy(m['bindings'][0]))
    elif fault=='control_binding':data['records'][0]['role']='vehicle'
    elif fault=='duplicate_vessel':m['vessels'].append(deepcopy(m['vessels'][0]))
    elif fault=='binding_future':m['bindings'][0]['sequence']=999
    elif fault=='overflow':m['vessels'][0].update(volume=1e308,volume_unit='mL')
    elif fault=='empty_solute':m['vessels'][0]['concentrations']={'':2}
    else:m['events']={}
    client.command('transfer-preview',client.write('bad.json',data),ok=False)
    c=client.create('screening');client.command('import','--db',client.db,'--campaign',c,client.write('bad.json',data),ok=False)
    assert client.show(c)['datasets']==[]


def curve_data():
    data=screening(709);events=[];vessels=[];bindings=[]
    actual={(e['plate'],e['well']):e['actual_dose']/1000 for e in data.pop('telemetry')}
    for i,row in enumerate(r for r in data['records'] if r['role']=='sample'):
        src,dst='s'+str(i),'d'+str(i);target=actual[row['plate'],row['well']]
        vessels += [vessel(src,100,target*10, row['compound']),vessel(dst,90)]
        events += [event('a'+str(i),2*i+1,src,dst,5,status='partial'),event('b'+str(i),2*i+2,src,dst,5)]
        bindings.append(dict(record_id=row['id'],vessel=dst,sequence=2*i+2))
        row.update(dose=0)  # Actual contents must not be pre-excluded by nominal zero.
    data['transfer_history']=dict(revision='curve-A',vessels=vessels,events=events,bindings=bindings)
    return data


def test_reconstructed_doses_reach_fits_and_plate_modes(client):
    data=curve_data();result=client.analyze(data);primary=result['compounds'][0]['channels']['primary']
    assert primary['ic50_um']==pytest.approx(.75,rel=.002)
    assert result['compounds'][0]['channels']['orthogonal']['ic50_um']==pytest.approx(1,rel=.002)
    assert all(p['dispense_mode']=='transfer_history' for p in result['plates'])
    binding=by_record(result['transfer_history'][0])
    assert result['transfer_history'][0]['revision']=='curve-A'
    for observation in primary['observations']:
        assert observation['dose_source']=='transfer_history' and observation.get('transfer_binding')
        assert observation['dose_um']==pytest.approx(binding[observation['id']]['dose_um'],rel=1e-9)
    data['transfer_history']['bindings'].pop()
    assert any(e['reason']=='missing_transfer_binding' for e in client.analyze(data)['excluded'])


def test_legacy_plates_and_uncertainty_cannot_override_contents(client):
    data=curve_data();nominal=screening(709)
    keep={r['id'] for r in data['records'] if r['assay']=='primary' and r['role']=='sample'}
    data['transfer_history']['bindings']=[b for b in data['transfer_history']['bindings'] if b['record_id'] in keep]
    for row in data['records']:
        if row['assay']!='primary':row['dose']=next((r.get('dose',0) for r in nominal['records'] if r['id']==row['id']),0)
    out=client.analyze(data);assert {p['dispense_mode'] for p in out['plates']}=={'nominal','transfer_history'}
    conflict=next(e for e in nominal['telemetry'] if e['plate']=='plate-primary');data['telemetry']=[conflict]
    client.analyze(data,ok=False);data.pop('telemetry')
    data=curve_data();h=preview(client,data)[0]
    data['calibration']={'revision':'error-A','sources':[],'nodes':[dict(id=b['record_id'],concentration=b['dose_um'],unit='uM',loadings={}) for b in h['bindings']],
                         'bindings':[dict(record_id=b['record_id'],node=b['record_id']) for b in h['bindings']]}
    client.analyze(data)
    data['calibration']['nodes'][0]['concentration']*=2
    client.analyze(data,ok=False)


def test_campaign_local_histories_survive_canonical_identity(client):
    first=small();second=small()
    second['transfer_history']['vessels'][0]['concentrations']['X']=2000
    campaigns=[dict(id=name,entities=[dict(local_id='X',type='sequence',value='ACDE',target='T')],records=d['records'],transfer_history=d['transfer_history']) for name,d in [('one',first),('two',second)]]
    data={'kind':'screening','campaigns':campaigns};h={x['campaign']:x for x in preview(client,data)}
    assert set(h)=={'one','two'}
    a={(b['vessel'],b['sequence']):b['dose_um'] for b in h['one']['bindings']}
    b={(b['vessel'],b['sequence']):b['dose_um'] for b in h['two']['bindings']}
    assert b==pytest.approx({k:v*2 for k,v in a.items()})
    assert {b['record_id'] for b in h['one']['bindings']}.isdisjoint({b['record_id'] for b in h['two']['bindings']})
    client.analyze(data)
    data['transfer_history']=first['transfer_history'];client.analyze(data,ok=False)


def test_pinned_jobs_current_reviews_and_historical_report(client):
    data=curve_data();c=client.create('screening');client.import_data(c,data)
    job=client.command('job-submit','--db',client.db,'--campaign',c)['job']
    token=client.command('job-claim','--db',client.db,'--job',job,'--worker','w')['token']
    changed=deepcopy(data);changed['transfer_history']['revision']='curve-B'
    for v in changed['transfer_history']['vessels']:
        v['concentrations']={k:x*2 for k,x in v['concentrations'].items()}
    client.import_data(c,changed)
    client.command('job-compute','--db',client.db,'--job',job,'--token',token)
    old=client.command('job-publish','--db',client.db,'--job',job,'--token',token)['run']
    client.review(c,old,1,ok=False)
    new=client.run(c);assert new['analysis']['result']['compounds'][0]['channels']['primary']['ic50_um']==pytest.approx(1.5,rel=.002)
    client.review(c,new['run'],2)
    directory=client.directory/'old-report'
    client.command('export','--db',client.db,'--campaign',c,'--run',old,'--directory',directory)
    snap=json.loads((directory/'snapshot.json').read_text());assert snap['input']==data and snap['superseded']
    assert snap['analysis']['result']['compounds'][0]['channels']['primary']['ic50_um']==pytest.approx(.75,rel=.002)
    visible=report_text((directory/'index.html').read_text())
    assert 'curve-A' in visible
    assert data['transfer_history']['bindings'][0]['vessel'] in visible
    rows=list(csv.DictReader((directory/'transfer-bindings.csv').open()))
    expected=by_record(snap['analysis']['result']['transfer_history'][0])
    assert len(rows)==len(expected)
    for row in rows:
        values=list(row.values());assert 'curve-A' in values
        matches=[key for key in expected if key in values];assert len(matches)==1
        witness=expected.pop(matches[0])
        assert witness['vessel'] in values
        lists=[]
        for value in values:
            try:parsed=json.loads(value)
            except (ValueError,TypeError):continue
            if isinstance(parsed,list):lists.append(parsed)
        assert witness['lineage'] in lists
    assert not expected
    assert client.command('verify-report',directory)['verified']
    (directory/'transfer-bindings.csv').write_text('replaced')
    client.command('verify-report',directory,ok=False)


def test_instrument_history_bytes_publish_atomically_and_ignore_parsed_cache(client):
    data=curve_data();stream=io.StringIO(newline='')
    fields=['id','plate','well','revision','assay','role','signal','compound','dose','dose_unit']
    w=csv.DictWriter(stream,fieldnames=fields);w.writeheader();w.writerows(dict(r,revision=1) for r in data['records'])
    raw={'readings':stream.getvalue().encode(),'history':json.dumps(data['transfer_history']).encode()}
    manifest={'delivery_id':'transfers','expected_revision':0,'sources':[dict(id=k,kind='readings' if k=='readings' else 'transfer_history',sha256=hashlib.sha256(v).hexdigest()) for k,v in raw.items()]}
    c=client.create('screening');s=client.command('ingest-open','--db',client.db,'--campaign',c,client.write('manifest.json',manifest))['session']
    for key in ['history','readings']:
        path=client.directory/(key+'.dat');path.write_bytes(raw[key]);path.chmod(0o644)
        assert client.command('ingest-add','--db',client.db,'--session',s,'--source',key,path)['state']=='accepted'
    before=client.command('ingest-preview','--db',client.db,'--session',s)
    client.sql("UPDATE ingest_sources SET parsed='[]'")
    assert client.command('ingest-preview','--db',client.db,'--session',s)==before
    client.sql("CREATE TRIGGER stop_transfer_publish BEFORE UPDATE ON ingest_sessions WHEN NEW.state='published' BEGIN SELECT RAISE(ABORT,'interruption'); END")
    client.command('ingest-publish','--db',client.db,'--session',s,ok=False)
    assert client.show(c)['datasets']==[]
    client.sql('DROP TRIGGER stop_transfer_publish')
    publication=client.command('ingest-publish','--db',client.db,'--session',s)
    assert client.command('ingest-publish','--db',client.db,'--session',s)['dataset']==publication['dataset']
    result=client.run(c)['analysis']['result'];assert result['compounds'][0]['channels']['primary']['ic50_um']==pytest.approx(.75,rel=.002)
    assert client.show(c)['current_revision']==1


def test_aliases_of_one_solute_add_without_losing_mass(client):
    d=dataset(dict(revision='aliases',vessels=[vessel('source',10,2)],events=[],bindings=[dict(record_id='r',vessel='source',sequence=0)]))
    d['transfer_history']['vessels'][0]['concentrations']['Y']=5
    entities=[dict(local_id=x,type='sequence',value='ACDE',target='T') for x in ['X','Y']]
    env={'kind':'screening','campaigns':[dict(id='a',entities=entities,records=d['records'],transfer_history=d['transfer_history'])]}
    assert preview(client,env)[0]['bindings'][0]['dose_um']==7


def test_large_operation_ordinals_do_not_round_through_float(client):
    d=small();m=d['transfer_history'];offset=2**53
    for e in m['events']:e['sequence']+=offset
    for b in m['bindings']:b['sequence']+=offset
    first=m['events'][0];first['revision']=offset
    m['events'].append(dict(first,revision=offset+1,volume=4))
    b=by_record(preview(client,d)[0]);assert b['early']['dose_um']==pytest.approx(4000/94)
    assert b['early']['lineage'][0]['revision']==offset+1
