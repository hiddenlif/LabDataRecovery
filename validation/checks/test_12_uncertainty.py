"""Independent shared-error special cases and cross-module evidence histories."""
import copy
import json
import math
from statistics import NormalDist
import numpy as np
import pytest
from data import screening


def calibrated(seed=91, independent=False, sd=.25):
    data=screening(seed)
    samples=[r for r in data['records'] if r['role']=='sample']
    actual={(r['plate'],r['well']):r['actual_dose']/1000 for r in data['telemetry']}
    sources=[{'id':r['id'],'log_sd':sd} for r in samples] if independent else [{'id':'shared','log_sd':sd}]
    data['calibration']={'revision':'calibration-A','sources':sources,
      'nodes':[{'id':r['id'],'concentration':actual[r['plate'],r['well']],'unit':'uM','loadings':{r['id'] if independent else 'shared':1}} for r in samples],
      'bindings':[{'record_id':r['id'],'node':r['id']} for r in samples]}
    return data


def primary(result): return result['compounds'][0]['channels']['primary']


def test_common_shift_has_exact_sensitivity_and_changes_review(client):
    result=client.analyze(calibrated(),{'max_ic50_um':1.05})
    c=primary(result);u=c['uncertainty']
    assert c['ic50_um']==pytest.approx(.75,rel=.002)
    assert u['source_sensitivity']['shared']==pytest.approx(1,abs=2e-6)
    assert u['calibration_log_variance']==pytest.approx(.25**2,rel=2e-6)
    z=NormalDist().inv_cdf(.975);se=math.sqrt(u['fit_log_variance']+.25**2)
    assert c['interval_um']==pytest.approx([c['ic50_um']*math.exp(-z*se),c['ic50_um']*math.exp(z*se)],rel=2e-6)
    assert result['compounds'][0]['disposition']=='followup_required'
    assert 'primary_potency_uncertain' in result['compounds'][0]['flags']
    assert result['calibration']['revision']=='calibration-A'


def test_independent_well_errors_are_not_a_shared_stock(client):
    data=calibrated(independent=True)
    result=client.analyze(data,{'max_ic50_um':1.05});curve=primary(result)
    # Independent oracle: differentiate analytic logistic response, solve normal equations.
    x=np.log([r['dose_um'] for r in curve['observations']]);b,t=curve['bottom'],curve['top'];h=curve['slope']
    q=1/(1+np.exp(-h*(x-math.log(curve['ic50_um']))));v=(t-b)*q*(1-q)
    J=np.array([1-q,q,-h*v,(x-math.log(curve['ic50_um']))*v]).T
    expected=(-np.linalg.solve(J.T@J,J.T)*h*v)[2]
    actual=curve['uncertainty']['source_sensitivity']
    for observation,sensitivity in zip(curve['observations'],expected):
        assert actual[observation['id']]==pytest.approx(sensitivity,abs=2e-6)
    assert curve['uncertainty']['calibration_log_variance']==pytest.approx(sum(expected**2)*.25**2,rel=3e-6)
    assert result['compounds'][0]['disposition']=='supported_for_review'


def test_shared_source_adds_across_ancestry_before_squaring(client):
    data=calibrated(sd=.1);model=data['calibration']
    old=copy.deepcopy(model['nodes'])
    model['nodes']=[{'id':'stock','concentration':80000,'unit':'nM','loadings':{'shared':1}}]
    model['nodes'] += [{'id':n['id'],'parent':'stock','ratio':n['concentration']/80,'loadings':{'shared':2}} for n in old]
    a=primary(client.analyze(data));assert a['uncertainty']['source_sensitivity']['shared']==pytest.approx(3,abs=2e-6)
    assert a['uncertainty']['calibration_log_variance']==pytest.approx(.09,rel=2e-6)
    model['nodes'].reverse();model['bindings'].reverse();data['records'].reverse()
    b=primary(client.analyze(data));assert b['interval_um']==pytest.approx(a['interval_um'],rel=2e-6)
    for node in model['nodes']:
        if 'parent' in node: node['loadings']['shared']=-1
    c=primary(client.analyze(data));assert c['uncertainty']['calibration_log_variance']==pytest.approx(0,abs=1e-14)


def test_zero_error_confidence_and_legacy_fit(client):
    data=calibrated(sd=0);a=primary(client.analyze(data));legacy=copy.deepcopy(data);legacy.pop('calibration')
    b=primary(client.analyze(legacy))
    assert a['ic50_um']==pytest.approx(b['ic50_um'],rel=2e-6)
    assert a['interval_um']==pytest.approx(b['interval_um'],rel=2e-5)
    data['calibration']['sources'][0]['log_sd']=.12
    narrow=primary(client.analyze(data,{'uncertainty_confidence':.8}));wide=primary(client.analyze(data,{'uncertainty_confidence':.99}))
    assert narrow['ic50_um']==pytest.approx(wide['ic50_um'],rel=1e-8)
    assert wide['interval_um'][0]<narrow['interval_um'][0]<narrow['interval_um'][1]<wide['interval_um'][1]
    client.analyze(data,{'uncertainty_confidence':1},ok=False)


@pytest.mark.parametrize('fault',['cycle','missing_parent','unknown_source','negative_ratio','duplicate_node','duplicate_binding','unknown_record','control_binding','disagree','negative_sd','nested','wrong_kind'])
def test_invalid_calibration_is_never_silently_ignored(client,fault):
    data=calibrated();m=data['calibration'];node=m['nodes'][0]
    if fault in {'cycle','missing_parent','negative_ratio'}:
        node.pop('concentration');node.pop('unit');node.update(parent=node['id'] if fault=='cycle' else 'missing',ratio=-1 if fault=='negative_ratio' else 1)
    elif fault=='unknown_source':node['loadings']={'absent':1}
    elif fault=='duplicate_node':m['nodes'].append(copy.deepcopy(node))
    elif fault=='duplicate_binding':m['bindings'].append(copy.deepcopy(m['bindings'][0]))
    elif fault=='unknown_record':m['bindings'][0]['record_id']='absent'
    elif fault=='control_binding':m['bindings'][0]['record_id']=next(r['id'] for r in data['records'] if r['role']=='vehicle')
    elif fault=='disagree':node['concentration']*=2
    elif fault=='negative_sd':m['sources'][0]['log_sd']=-.1
    elif fault=='wrong_kind':
        from data import bridge
        data=dict(bridge(),calibration=m)
    else:
        data={'kind':'screening','campaigns':[{'id':'a','entities':[{'local_id':data['records'][0].get('compound','compound-91'),'type':'sequence','value':'ACDE','target':'T'}],'records':data['records'],'telemetry':data['telemetry'],'calibration':m}]}
    client.analyze(data,ok=False)


def test_missing_binding_is_unresolved_but_failed_well_stays_excluded(client):
    data=calibrated();row=next(r for r in data['records'] if r['role']=='sample' and r['assay']=='primary')
    data['calibration']['bindings']=[b for b in data['calibration']['bindings'] if b['record_id']!=row['id']]
    result=client.analyze(data);assert primary(result)['status']=='calibration_unresolved'
    assert primary(result)['interval_um'] is None and result['compounds'][0]['disposition']=='insufficient_evidence'
    for event in data['telemetry']:
        if (event['plate'],event['well'])==(row['plate'],row['well']):event['status']='failed'
    result=client.analyze(data);assert primary(result)['status']=='fit'
    assert {'id':row['id'],'reason':'failed'} in result['excluded']


def test_campaign_scoping_preserves_shared_sources(client):
    data=calibrated();m=data['calibration'];m['bindings']=[dict(b,campaign='first') for b in m['bindings']]
    first={'id':'first','entities':[{'local_id':'compound-91','type':'sequence','value':'ACDE','target':'T'}],'records':data['records'],'telemetry':data['telemetry']}
    second=copy.deepcopy(first);second['id']='second'
    m['bindings'] += [dict(b,campaign='second') for b in list(m['bindings'])]
    envelope={'kind':'screening','campaigns':[second,first],'calibration':m}
    result=client.analyze(envelope);c=primary(result)
    assert len(result['compounds'])==1 and c['n']==54
    assert c['uncertainty']['calibration_log_variance']==pytest.approx(.0625,rel=2e-6)
    envelope['calibration']['bindings'][0]['campaign']='unknown';client.analyze(envelope,ok=False)


def test_changed_calibration_is_pinned_through_jobs_and_reports(client):
    data=calibrated(sd=.1);c=client.create('screening');client.import_data(c,data)
    job=client.command('job-submit','--db',client.db,'--campaign',c)['job']
    token=client.command('job-claim','--db',client.db,'--job',job,'--worker','calibration')['token']
    data['calibration']['revision']='calibration-B';data['calibration']['sources'][0]['log_sd']=.3
    assert client.import_data(c,data)['revision']==2
    assert client.command('job-submit','--db',client.db,'--campaign',c)['job']!=job
    client.command('job-compute','--db',client.db,'--job',job,'--token',token)
    run=client.command('job-publish','--db',client.db,'--job',job,'--token',token)['run']
    client.review(c,run,2,ok=False)
    destination=client.directory/'historical-calibration'
    client.command('export','--db',client.db,'--campaign',c,'--run',run,'--directory',destination)
    snapshot=json.loads((destination/'snapshot.json').read_text())
    assert snapshot['superseded'] and snapshot['input']['calibration']['revision']=='calibration-A'
    assert primary(snapshot['analysis']['result'])['uncertainty']['calibration_log_variance']==pytest.approx(.01,rel=2e-6)
    html=(destination/'index.html').read_text();assert 'calibration-A' in html
    # Wording/visibility of the approximation is a manual-review criterion, not an exact-string requirement.
    assert snapshot['analysis']['result']['calibration']['method']=='first_order_log_dose'
    current=client.run(c);assert primary(current['analysis']['result'])['uncertainty']['calibration_log_variance']==pytest.approx(.09,rel=2e-6)


def test_nonuniform_sensitivity_matches_small_refit_perturbation(client):
    data=calibrated(sd=.03)
    for i,node in enumerate(data['calibration']['nodes']):node['loadings']['shared']=.25+(i%7)*.12
    central=primary(client.analyze(data));epsilon=1e-4;estimates=[]
    for direction in [-1,1]:
        changed=copy.deepcopy(data);nodes={n['id']:n for n in changed['calibration']['nodes']}
        for n in nodes.values():n['concentration']*=math.exp(direction*epsilon*n['loadings']['shared'])
        pairs={(r['plate'],r['well']):r['id'] for r in changed['records']}
        for t in changed['telemetry']:t['actual_dose']=nodes[pairs[t['plate'],t['well']]]['concentration']*1000
        estimates.append(math.log(primary(client.analyze(changed))['ic50_um']))
    numerical=(estimates[1]-estimates[0])/(2*epsilon)
    # Refitting includes residual curvature omitted by the documented Gauss-Newton approximation.
    assert central['uncertainty']['source_sensitivity']['shared']==pytest.approx(numerical,abs=.002)


def test_extreme_finite_uncertainty_and_confidence_are_json_safe(client):
    data=calibrated(sd=1e308)
    curve=primary(client.analyze(data))
    assert curve['status']=='uncertainty_unbounded' and curve['interval_um'] is None
    assert curve['uncertainty']['calibration_log_variance'] is None
    curve=primary(client.analyze(calibrated(sd=.01),{'uncertainty_confidence':.9999999999999999}))
    assert curve['status']=='fit' and all(math.isfinite(v) for v in curve['interval_um'])


def test_nominal_replacement_empty_sources_and_unused_graph_validation(client):
    data=calibrated(sd=0);data.pop('telemetry')
    for row in data['records']:
        if row['role']=='sample':row['dose']*=5
    model=data['calibration'];model['sources']=[]
    for node in model['nodes']:node['loadings']={}
    curve=primary(client.analyze(data))
    assert curve['ic50_um']==pytest.approx(.75,rel=.002)
    assert curve['uncertainty']['source_sensitivity']=={} and curve['uncertainty']['calibration_log_variance']==0
    model['nodes'].append({'id':'unused','parent':'absent','ratio':1,'loadings':{}})
    client.analyze(data,ok=False)
