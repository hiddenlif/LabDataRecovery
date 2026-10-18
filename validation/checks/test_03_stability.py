from assertions import equivalent, report_text
import math
from copy import deepcopy
import pytest
from scipy.stats import t
from data import stability


def independent_bound(rows, hour, confidence):
    xs = [r["time"] / 60 for r in rows]
    ys = [r["value"] for r in rows]
    ws = [r["weight"] for r in rows]
    s0 = sum(ws); s1 = sum(w*x for w,x in zip(ws,xs)); s2 = sum(w*x*x for w,x in zip(ws,xs))
    sy = sum(w*y for w,y in zip(ws,ys)); sxy = sum(w*x*y for w,x,y in zip(ws,xs,ys))
    determinant = s0*s2 - s1*s1
    intercept = (s2*sy-s1*sxy)/determinant
    slope = (s0*sxy-s1*sy)/determinant
    variance = sum(w*(y-intercept-slope*x)**2 for w,x,y in zip(ws,xs,ys))/(len(rows)-2)
    se = math.sqrt(max(0, variance*(s2-2*hour*s1+hour*hour*s0)/determinant))
    return intercept+slope*hour - t.ppf(confidence,len(rows)-2)*se


def test_fast_batch_limits_study(client):
    result = client.analyze(stability())
    assert result["supported_time_h"] == pytest.approx(30, abs=1e-6)
    assert result["limiting_batches"] == ["fast"]
    assert next(b for b in result["batches"] if b["batch"] == "slow")["supported_time_h"] == 45


def test_noisy_weighted_bound_matches_scalar_reference(client):
    data = stability(True)
    rows = [r for r in data["records"] if r["batch"] == "fast"]
    lower, upper = 0.0, 45.0
    for _ in range(80):
        mid = (lower+upper)/2
        if independent_bound(rows, mid, .95) >= 70:
            lower = mid
        else:
            upper = mid
    result = client.analyze(data)
    assert result["supported_time_h"] == pytest.approx((lower+upper)/2, abs=1e-6)


def test_incomplete_batch_blocks_overall_claim(client):
    data = stability()
    data["records"] += [{"id": "extra", "batch": "new", "time": 0, "time_unit": "h", "value": 99, "weight": 1}]
    result = client.analyze(data)
    assert result["status"] == "incomplete"
    assert result["supported_time_h"] is None
    assert result["incomplete_batches"] == ["new"]


def test_confidence_and_extrapolation_limits(client):
    data = stability(True)
    low = client.analyze(data, {"confidence": .90})
    high = client.analyze(data, {"confidence": .99})
    assert high["supported_time_h"] < low["supported_time_h"]
    assert client.analyze(data, {"max_time_h": 12})["supported_time_h"] == 12


def test_time_unit_equivalence(client):
    data = stability(True)
    first = client.analyze(data)
    for row in data["records"]:
        row["time"] /= 60
        row["time_unit"] = "h"
    equivalent(client.analyze(data), first)


def test_initial_failure_reports_zero(client):
    data = stability()
    for row in data["records"]:
        if row["batch"] == "fast":
            row["value"] -= 40
    assert client.analyze(data)["supported_time_h"] == 0

