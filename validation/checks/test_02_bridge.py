from assertions import equivalent, report_text
from copy import deepcopy
import math
import random
import pytest
from data import bridge


def test_donor_weighting_not_well_weighting(client):
    ratios = [1.7, .95, .97, .99, 1.01, 1.03, 1.05, 1.07]
    result = client.analyze(bridge(ratios, [18, 1, 1, 1, 1, 1, 1, 1]))
    expected = math.exp(sum(math.log(x) for x in ratios) / len(ratios))
    assert result["ratio"] == pytest.approx(expected, rel=1e-10)
    assert result["donor_count"] == 8
    assert len(result["pairs"]) == 25


def test_replicating_technical_wells_does_not_create_donors(client):
    data = bridge()
    first = client.analyze(data)
    for row in deepcopy(data["records"]):
        if row["donor"] == "D00":
            row["id"] += "-extra"
            data["records"].append(row)
    second = client.analyze(data)
    assert second["ratio"] == pytest.approx(first["ratio"])
    assert second["interval"] == pytest.approx(first["interval"])
    assert second["donor_count"] == 8


def test_sample_id_scoped_to_donor_and_units_normalized(client):
    result = client.analyze(bridge([1.1] * 8))
    assert len(result["pairs"]) == 8
    assert result["ratio"] == pytest.approx(1.1)
    assert result["interval"] == pytest.approx([1.1, 1.1])
    assert result["status"] == "within_equivalence_bounds"


def test_missing_counterpart_is_excluded_not_zero(client):
    data = bridge()
    data["records"] = [r for r in data["records"] if not (r["donor"] == "D00" and r["method"] == "candidate")]
    result = client.analyze(data)
    assert result["donor_count"] == 7
    assert result["ratio"] == pytest.approx(1.04)
    assert result["excluded"] == [{"donor": "D00", "sample": "S0", "reason": "unpaired"}]


def test_minimum_counts_independent_donors(client):
    result = client.analyze(bridge([1.04] * 3, [20, 20, 20]))
    assert result["status"] == "insufficient_donors"
    assert result["ratio"] is None


def test_bootstrap_repeatable_and_order_invariant(client):
    data = bridge([.7, .8, .9, 1, 1.1, 1.2, 1.3, 1.4])
    first = client.analyze(data)
    random.Random(8).shuffle(data["records"])
    equivalent(client.analyze(data), first)
    assert first["interval"][0] < first["ratio"] < first["interval"][1]


def test_incompatible_units_rejected(client):
    data = bridge()
    data["records"][0]["unit"] = "ng/mL"
    client.analyze(data, ok=False)


def test_duplicate_samples_cannot_narrow_donor_interval(client):
    ratios = [.76, .9, .95, 1, 1.03, 1.08, 1.2, 1.5]
    balanced = client.analyze(bridge(ratios))
    repeated = client.analyze(bridge(ratios, [14, 1, 1, 1, 1, 1, 1, 1]))
    assert repeated["ratio"] == pytest.approx(balanced["ratio"], rel=1e-12)
    assert repeated["interval"] == pytest.approx(balanced["interval"], rel=1e-12)
    assert repeated["leave_one_donor_out_range"] == pytest.approx(balanced["leave_one_donor_out_range"])


def test_point_estimate_inside_bounds_is_not_enough(client):
    ratios = [.35, .6, .8, 1, 1, 1.25, 1/.6, 1/.35]
    result = client.analyze(bridge(ratios))
    assert result["ratio"] == pytest.approx(1)
    assert result["status"] == "equivalence_not_demonstrated"

