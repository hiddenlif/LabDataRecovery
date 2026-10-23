"""Exact shared-error invariants for the documented local approximation."""
import math
import pytest
from truegate.examples import screening
from truegate.engine import analyze


def calibration(data):
    actual={(e['plate'],e['well']):e['actual_dose']/1000 for e in data['telemetry']}
    samples=[r for r in data['records'] if r['role']=='sample']
    return {'revision':'stock-A','sources':[{'id':'stock','log_sd':.2}],
            'nodes':[{'id':r['id'],'concentration':actual[r['plate'],r['well']],'unit':'uM','loadings':{'stock':1}} for r in samples],
            'bindings':[{'record_id':r['id'],'node':r['id']} for r in samples]}


def test_common_log_shift_does_not_average_away(tmp_path):
    data=screening();data['calibration']=calibration(data)
    result=analyze(data)['result']
    fitted=[c for compound in result['compounds'] for c in compound['channels'].values() if c['status']=='fit']
    assert fitted
    for curve in fitted:
        assert curve['uncertainty']['source_sensitivity']['stock']==pytest.approx(1,abs=2e-6)
        assert curve['uncertainty']['calibration_log_variance']==pytest.approx(.04,rel=2e-6)
        assert curve['interval_um'][0]<curve['ic50_um']<curve['interval_um'][1]


def test_missing_primary_binding_cannot_claim_supported_evidence():
    data=screening();data['calibration']=calibration(data)
    missing=next(r for r in data['records'] if r['role']=='sample' and r['assay']=='primary')
    data['calibration']['bindings']=[b for b in data['calibration']['bindings'] if b['record_id']!=missing['id']]
    result=analyze(data)['result']
    compound=next(c for c in result['compounds'] if c['compound']==missing['compound'])
    assert compound['channels']['primary']['status']=='calibration_unresolved'
    assert compound['disposition']=='insufficient_evidence'
