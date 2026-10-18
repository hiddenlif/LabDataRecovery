import math
from copy import deepcopy
import pytest
from scipy.stats import beta
from data import counts


def test_zero_blank_retains_uncertainty(client):
    result = client.analyze(counts())
    alpha = (1-.95)/(16+2)
    expected = 1-(alpha/2)**(1/1000000)
    assert result["background"]["one"]["interval"][1] == pytest.approx(expected, abs=1e-12)
    assert result["interval_alpha"] == pytest.approx(alpha)


def test_blank_correction_and_conservative_bounds(client):
    result = client.analyze(counts(blank=250))
    row = next(s for s in result["samples"] if s["id"] == "one-low-0")
    alpha = result["interval_alpha"]
    lo = beta.ppf(alpha/2,1250,1000000-1250+1) - beta.ppf(1-alpha/2,251,1000000-250)
    hi = beta.ppf(1-alpha/2,1251,1000000-1250) - beta.ppf(alpha/2,250,1000000-250+1)
    assert row["net_fraction"] == pytest.approx(.001)
    assert row["interval"] == pytest.approx([lo,hi], abs=1e-12)


def test_missing_batch_blank_rejected(client):
    data = counts()
    data["records"] = [r for r in data["records"] if r["id"] != "two-blank"]
    client.analyze(data, ok=False)


def test_high_level_failure_prevents_disconnected_loq(client):
    data = counts()
    for row in data["records"]:
        if row["level"] == "high":
            row["events"] //= 2
    result = client.analyze(data)
    assert next(x for x in result["levels"] if x["level"] == "low")["qualified"]
    assert result["candidate_loq_fraction"] is None


def test_level_requires_all_batches_and_replicates(client):
    data = counts()
    data["records"] = [r for r in data["records"] if not (r["batch"] == "two" and r["level"] == "low")]
    result = client.analyze(data)
    assert result["candidate_loq_fraction"] == .01


def test_precision_failure_is_preserved(client):
    data = counts()
    for row in data["records"]:
        if row["level"] == "low":
            row["events"] = 500 if row["id"].endswith("0") else 1500
    result = client.analyze(data, {"max_relative_error": .9, "max_cv": .1})
    assert not next(x for x in result["levels"] if x["level"] == "low")["qualified"]

