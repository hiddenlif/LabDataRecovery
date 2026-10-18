"""Numerical witnesses derived without importing the candidate or its estimators."""
import math
import numpy as np
import pytest
from data import bridge, stability, screening, counts
from test_03_stability import independent_bound


def percentile(values, probability):
    values = sorted(values)
    position = (len(values) - 1) * probability
    index = math.floor(position)
    return values[index] + (position - index) * (values[min(index + 1, len(values) - 1)] - values[index])


@pytest.mark.parametrize('seed,confidence', [(13, .8), (701, .97)])
def test_bridge_interval_matches_scalar_resampling(client, seed, confidence):
    ratios = [.61, .82, .94, 1.02, 1.08, 1.19, 1.37, 1.62]
    policy = {'seed': seed, 'confidence': confidence, 'bootstrap_samples': 251}
    sizes = [7, 1, 2, 3, 1, 4, 1, 2]
    data = bridge(ratios, sizes)
    for row in data['records']:
        if row['method'] == 'candidate':
            donor, sample = int(row['donor'][1:]), int(row['sample'][1:])
            row['value'] *= math.exp(.04*(sample-(sizes[donor]-1)/2))
            row['value'] *= .9 if row['id'].endswith('-0') else 1.1
    result = client.analyze(data, policy)
    logs = list(map(math.log, ratios))
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = [sum(logs[int(i)] for i in rng.integers(0, len(logs), len(logs))) / len(logs)
             for _ in range(policy['bootstrap_samples'])]
    alpha = 1 - confidence
    expected = [math.exp(percentile(draws, p)) for p in [alpha/2, 1-alpha/2]]
    assert result['interval'] == pytest.approx(expected, rel=1e-10, abs=1e-12)
    jackknife = [math.exp(sum(v for j, v in enumerate(logs) if j != i)/(len(logs)-1))
                 for i in range(len(logs))]
    assert result['leave_one_donor_out_range'] == pytest.approx([min(jackknife), max(jackknife)], rel=1e-10)


def binomial_cdf(k, n, p):
    return sum(math.comb(n, j) * p**j * (1-p)**(n-j) for j in range(k+1))


def probability_for_tail(k, n, target):
    left, right = 0., 1.
    for _ in range(90):
        mid = (left + right)/2
        if binomial_cdf(k, n, mid) > target:
            left = mid
        else:
            right = mid
    return (left + right)/2


def exact_interval(k, n, alpha):
    # Invert finite binomial sums, independent of the candidate's Beta quantiles.
    return (0. if k == 0 else probability_for_tail(k-1, n, 1-alpha/2),
            1. if k == n else probability_for_tail(k, n, alpha/2))


@pytest.mark.parametrize('blank_events', [0, 3, 20])
def test_count_endpoints_match_binomial_tail_inversion(client, blank_events):
    rows = [{'id': 'blank', 'batch': 'a', 'level': 'blank', 'events': blank_events,
             'total': 20, 'expected_fraction': 0}]
    rows += [{'id': f's{i}', 'batch': 'a', 'level': 'dose', 'events': k,
              'total': 20, 'expected_fraction': .2} for i, k in enumerate([0, 4, 20])]
    result = client.analyze({'kind': 'rare_events', 'records': rows})
    alpha = .05/4
    assert result['interval_alpha'] == pytest.approx(alpha, abs=1e-14)
    blo, bhi = exact_interval(blank_events, 20, alpha)
    assert result['background']['a']['interval'] == pytest.approx([blo, bhi], abs=1e-10)
    for row, observed in zip(rows[1:], result['samples']):
        lo, hi = exact_interval(row['events'], 20, alpha)
        assert observed['interval'] == pytest.approx([max(0, lo-bhi), max(0, hi-blo)], abs=1e-10)
        assert observed['net_fraction'] == pytest.approx(max(0, (row['events']-blank_events)/20), abs=1e-12)


def test_every_reported_stability_bound_matches_scalar_formula(client):
    data = stability(True)
    confidence = .975
    result = client.analyze(data, {'confidence': confidence})
    for batch in result['batches']:
        rows = [r for r in data['records'] if r['batch'] == batch['batch']]
        for point in batch['curve']:
            assert point['lower_mean_bound'] == pytest.approx(
                independent_bound(rows, point['time_h'], confidence), abs=1e-8)


@pytest.mark.parametrize('potency,slope', [(.12, .85), (2.4, 1.7), (4.8, 1.05)])
def test_screening_recovers_varied_known_curves(client, potency, slope):
    data = screening(502)
    for row in data['records']:
        if row['role'] == 'sample' and row['assay'] in {'primary', 'orthogonal'}:
            vehicle = 16000 if row['assay'] == 'primary' else 8000
            midpoint = potency if row['assay'] == 'primary' else potency*1.3
            inhibition = 6 + 88/(1+(midpoint/row['dose'])**slope)
            row['signal'] = vehicle - (vehicle-200)*inhibition/100
    result = client.analyze(data)
    for assay, expected in [('primary', potency), ('orthogonal', potency*1.3)]:
        curve = result['compounds'][0]['channels'][assay]
        assert curve['status'] == 'fit'
        assert curve['ic50_um'] == pytest.approx(expected, rel=.02)


@pytest.mark.parametrize('reverse', [False, True])
def test_blank_and_nonblank_cannot_share_conflicting_level(client, reverse):
    data = counts()
    data['records'][0]['level'] = 'low'
    if reverse:
        data['records'].reverse()
    client.analyze(data, ok=False)
