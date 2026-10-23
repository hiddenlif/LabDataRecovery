"""Small public witnesses for reconstructing physical liquid additions."""
from copy import deepcopy
import pytest
from truegate.transfer_history import replay
from truegate.errors import WorkbenchError


def model():
    return {'revision':'A','vessels':[
        {'id':'stock','volume':20,'volume_unit':'uL','concentrations':{'X':100},'concentration_unit':'uM'},
        {'id':'well','volume':10,'volume_unit':'uL','concentrations':{},'concentration_unit':'uM'}],
        'events':[{'id':'first','revision':1,'sequence':1,'source':'stock','destination':'well','status':'ok','volume':5,'volume_unit':'uL'},
                  {'id':'second','revision':1,'sequence':2,'source':'stock','destination':'well','status':'partial','volume':5,'volume_unit':'uL'}],
        'bindings':[{'record_id':'r','vessel':'well','sequence':1}]}


def test_early_measurement_keeps_earlier_contents():
    result=replay(model())
    assert result['bindings'][0]['volume_ul']==15
    assert result['bindings'][0]['amounts_pmol']['X']==500
    assert result['final_vessels'][1]['volume_ul']==20
    assert result['final_vessels'][1]['amounts_pmol']['X']==1000


def test_corrected_operation_replaces_evidence_and_duplicate_export_adds_no_liquid():
    m=model();m['events'] += [dict(m['events'][0],revision=2,volume=2),deepcopy(m['events'][1])]
    m['events'].reverse();r=replay(m)
    assert r['bindings'][0]['amounts_pmol']['X']==200
    assert r['bindings'][0]['volume_ul']==12
    assert len(r['steps'])==2


def test_failure_of_distinct_later_operation_preserves_first_delivery():
    m=model();m['events'][1].update(status='failed',volume=0)
    r=replay(m)
    assert r['final_vessels'][1]['amounts_pmol']['X']==500
    assert r['final_vessels'][1]['lineage']==[{'id':'first','revision':1}]


def test_unknown_and_corrected_measurements():
    m=model();m['events'][0].update(status='unknown');m['events'][0].pop('volume');m['events'][0].pop('volume_unit')
    assert replay(m)['bindings'][0]['known'] is False
    m['events'].append(dict(m['events'][0],revision=2,status='ok',volume=3,volume_unit='uL'))
    assert replay(m)['bindings'][0]['amounts_pmol']['X']==300


def test_historical_conflicts_and_overdraw_are_errors():
    m=model();m['events'] += [dict(m['events'][0],volume=2),dict(m['events'][0],revision=2,volume=3)]
    with pytest.raises(WorkbenchError):replay(m)
    m=model();m['events'][1]['volume']=30
    with pytest.raises(WorkbenchError):replay(m)


def test_equivalent_units_do_not_create_a_false_revision_conflict():
    m=model();m['vessels'][0]['volume']=2000
    m['events']=[dict(m['events'][0],volume=1.001,volume_unit='mL'),dict(m['events'][0],volume=1001,volume_unit='uL')]
    result=replay(m)
    assert len(result['steps'])==1
    assert result['steps'][0]['volume_ul']==1001


def test_empty_optional_history_has_no_physical_effect():
    result=replay({'revision':'empty','vessels':[],'events':[],'bindings':[]})
    assert result['steps']==[] and result['bindings']==[] and result['final_vessels']==[]


def test_history_observations_serialize_the_documented_revision_marker():
    from pathlib import Path
    from truegate.codec import load
    from truegate.engine import analyze
    data=load(Path(__file__).parents[1]/'examples/transfer-history/initial.json')
    result=analyze(data)['result']
    observations=[o for c in result['compounds'] for ch in c['channels'].values() for o in ch['observations']]
    assert observations
    assert all('calibration_revision' in o and o['calibration_revision'] is None and o['transfer_binding'] for o in observations)
