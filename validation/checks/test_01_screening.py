from assertions import equivalent, report_text
from copy import deepcopy
import random
import pytest
from data import screening


@pytest.mark.parametrize("seed,scale", [(91, 2.3), (207, .4), (830, 3.7)])
def test_calibrated_dose_and_plate_controls(client, seed, scale):
    result = client.analyze(screening(seed, scale))
    hit = result["compounds"][0]
    assert hit["channels"]["primary"]["ic50_um"] == pytest.approx(.75, rel=.02)
    assert hit["channels"]["orthogonal"]["ic50_um"] == pytest.approx(1, rel=.02)
    assert hit["disposition"] == "supported_for_review"
    assert all(o["dose_source"] == "calibrated" for o in hit["channels"]["primary"]["observations"])


def test_later_failure_removes_well_and_retains_reason(client):
    data = screening()
    entry = next(e for e in data["telemetry"] if e["plate"] == "plate-primary")
    data["telemetry"].insert(0, dict(entry, revision=3, status="failed"))
    data["telemetry"].append(dict(entry, revision=2, actual_dose=entry["actual_dose"] * 4))
    result = client.analyze(data)
    assert len(result["excluded"]) == 1
    assert result["excluded"][0]["reason"] == "failed"
    assert result["compounds"][0]["channels"]["primary"]["n"] == 26


def test_same_well_name_on_other_plate_unchanged(client):
    data = screening()
    event = next(e for e in data["telemetry"] if e["plate"] == "plate-primary")
    data["telemetry"].append(dict(event, revision=2, status="cancelled"))
    result = client.analyze(data)["compounds"][0]["channels"]
    assert result["primary"]["n"] == 26
    assert result["orthogonal"]["n"] == 27


def test_telemetry_conflict_rejected_but_exact_duplicate_allowed(client):
    data = screening()
    data["telemetry"].append(deepcopy(data["telemetry"][0]))
    client.analyze(data)
    data["telemetry"][-1]["status"] = "failed"
    client.analyze(data, ok=False)


def test_input_order_has_no_effect_on_estimates(client):
    data = screening()
    first = client.analyze(data)
    random.Random(31).shuffle(data["records"])
    random.Random(32).shuffle(data["telemetry"])
    second = client.analyze(data)
    equivalent(first, second)


def test_missing_telemetry_and_bad_plate_visible(client):
    data = screening()
    data["telemetry"].pop()
    for row in data["records"]:
        if row["plate"] == "plate-counter" and row["role"] == "positive":
            row["signal"] = 20000
    result = client.analyze(data)
    assert any(x["reason"] == "missing_telemetry" for x in result["excluded"])
    assert any(p["status"] == "invalid_control_order" for p in result["plates"])
    assert "counter_unresolved" in result["compounds"][0]["flags"]


def test_same_assay_on_different_instrument_scales(client):
    data = screening(304, 1.8)
    for row in deepcopy(data["records"]):
        row.update(id=row["id"] + "-second", plate=row["plate"] + "-second",
                   signal=row["signal"] * 2 + 13000)
        data["records"].append(row)
    for event in deepcopy(data["telemetry"]):
        event["plate"] += "-second"
        data["telemetry"].append(event)
    result = client.analyze(data)
    assert len(result["plates"]) == 8
    assert all(p["status"] == "usable" for p in result["plates"])
    primary = result["compounds"][0]["channels"]["primary"]
    assert primary["n"] == 54
    assert primary["ic50_um"] == pytest.approx(.75, rel=.02)


def test_no_telemetry_preserves_documented_nominal_mode(client):
    data = screening(107, 1)
    del data["telemetry"]
    primary = client.analyze(data)["compounds"][0]["channels"]["primary"]
    assert primary["ic50_um"] == pytest.approx(.75, rel=.02)
    assert all(o["dose_source"] == "nominal" for o in primary["observations"])


def test_partial_telemetry_preserves_other_plates_and_marks_modes(client):
    data = screening(107, 1)
    data['telemetry'] = [e for e in data['telemetry'] if e['plate']=='plate-primary']
    data['telemetry'].pop()
    result=client.analyze(data)
    assert len(result['excluded'])==1 and result['excluded'][0]['reason']=='missing_telemetry'
    channels=result['compounds'][0]['channels']
    assert channels['primary']['n']==26
    assert all(channels[a]['n']==27 for a in ['counter','viability','orthogonal'])
    assert all(o['dose_source']=='nominal' for o in channels['orthogonal']['observations'])
    assert {p['plate']:p['dispense_mode'] for p in result['plates']} == {
        'plate-primary':'calibrated','plate-counter':'nominal','plate-viability':'nominal','plate-orthogonal':'nominal'}

