import json
import pytest
from truegate.codec import loads, digest
from truegate.errors import WorkbenchError, Conflict
from truegate.examples import bridge, stability, rare_events
from truegate.engine import analyze
from truegate.repository import Repository
from truegate.reporting import export, verify


@pytest.mark.parametrize("payload", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'])
def test_strict_json(payload):
    with pytest.raises(WorkbenchError):
        loads(payload)


def test_digest_ignores_object_key_order():
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


@pytest.mark.parametrize("factory", [bridge, stability, rare_events])
def test_example_runs(factory):
    data = factory()
    result = analyze(data)
    assert result["input_sha256"] == digest(data)
    assert result["kind"] == data["kind"]
    json.dumps(result, allow_nan=False)


def test_invalid_policy_rejected():
    with pytest.raises(WorkbenchError):
        analyze(bridge(), {"unknown": 3})


def test_campaign_export(tmp_path):
    repo = Repository(tmp_path / "study.db")
    campaign = repo.create("A <study>", "bridge")["campaign"]
    data = bridge()
    imported = repo.import_data(campaign, data)
    assert repo.import_data(campaign, data)["reused"]
    run = repo.run(campaign)
    assert repo.run(campaign)["run"] == run["run"]
    repo.review(campaign, run["run"], "hold", "Scientist", "More donors needed", imported["revision"])
    path = tmp_path / "report"
    export(repo.snapshot(campaign, run["run"]), path)
    assert verify(path)["verified"]
    assert "A &lt;study&gt;" in (path / "index.html").read_text()
    with pytest.raises(WorkbenchError):
        export(repo.snapshot(campaign, run["run"]), path)
    (path / "summary.csv").write_text("changed")
    with pytest.raises(WorkbenchError):
        verify(path)


def test_campaign_scope(tmp_path):
    repo = Repository(tmp_path / "study.db")
    a = repo.create("A", "bridge")["campaign"]
    b = repo.create("B", "bridge")["campaign"]
    repo.import_data(a, bridge())
    repo.import_data(b, bridge())
    run = repo.run(a)
    with pytest.raises(WorkbenchError):
        repo.snapshot(b, run["run"])

