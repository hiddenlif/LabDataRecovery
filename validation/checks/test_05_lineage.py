from copy import deepcopy
import json
import sqlite3
import pytest
from data import bridge


def test_data_and_policy_changes_create_distinct_runs(client):
    campaign = client.create()
    client.import_data(campaign, bridge())
    first = client.run(campaign)
    assert client.run(campaign)["run"] == first["run"]
    changed_policy = client.run(campaign, {"equivalence_high": 1.02})
    assert changed_policy["run"] != first["run"]
    assert changed_policy["analysis"]["result"]["status"] == "equivalence_not_demonstrated"
    client.import_data(campaign, bridge([1.5]*8))
    second = client.run(campaign)
    assert second["run"] not in {first["run"], changed_policy["run"]}
    assert second["analysis"]["result"]["ratio"] == pytest.approx(1.5)


def test_reviews_stale_after_import_but_history_remains(client):
    campaign = client.create()
    client.import_data(campaign, bridge())
    run = client.run(campaign)["run"]
    client.review(campaign, run, 1)
    assert client.show(campaign)["current_review"]["run"] == run
    client.import_data(campaign, bridge([1.2]*8))
    shown = client.show(campaign)
    assert shown["current_review"] is None
    assert len(shown["decisions"]) == 1
    client.review(campaign, run, 1, ok=False)


def test_review_optimistic_revision_and_campaign_scope(client):
    first, second = client.create(), client.create()
    for campaign in [first, second]:
        client.import_data(campaign, bridge())
    run = client.run(first)["run"]
    client.review(first, run, 2, ok=False)
    client.review(second, run, 1, ok=False)


def test_historical_export_uses_original_input_and_review(client):
    campaign = client.create()
    old = bridge()
    client.import_data(campaign, old)
    run = client.run(campaign)["run"]
    client.review(campaign, run, 1)
    client.import_data(campaign, bridge([1.4]*8))
    directory = client.directory / "historical"
    client.command("export", "--db", client.db, "--campaign", campaign, "--run", run, "--directory", directory)
    snap = json.loads((directory / "snapshot.json").read_text())
    assert snap["input"] == old
    assert snap["superseded"] is True
    assert snap["dataset_revision"] == 1
    assert snap["review"]["run"] == run
    assert client.command("verify-report", directory)["verified"]


def test_reimport_and_engine_identity(client):
    campaign = client.create()
    data = bridge()
    one = client.import_data(campaign, data)
    assert client.import_data(campaign, data)["dataset"] == one["dataset"]
    run = client.run(campaign)["run"]
    with sqlite3.connect(client.db) as db:
        db.execute("UPDATE runs SET engine='previous-engine' WHERE id=?", (run,))
    assert client.run(campaign)["run"] != run
    client.import_data(campaign, bridge([1.1]*8))
    again = client.import_data(campaign, data)
    assert again["revision"] == 3
    assert again["dataset"] != one["dataset"]


def test_mutated_stored_input_blocks_export(client):
    campaign = client.create()
    client.import_data(campaign, bridge())
    run = client.run(campaign)["run"]
    with sqlite3.connect(client.db) as db:
        db.execute("UPDATE datasets SET content=? WHERE campaign=?", (json.dumps(bridge([1.9]*8)), campaign))
    client.command("export", "--db", client.db, "--campaign", campaign, "--run", run,
                   "--directory", client.directory / "bad", ok=False)

