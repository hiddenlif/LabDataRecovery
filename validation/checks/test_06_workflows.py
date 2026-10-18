import json
import pytest
from data import screening, bridge, stability, counts


@pytest.mark.parametrize("factory", [screening, bridge, stability, counts])
def test_analysis_survives_storage_review_and_report(client, factory):
    data = factory()
    direct = client.analyze(data)
    campaign = client.create(data["kind"])
    client.import_data(campaign, data)
    run = client.run(campaign)
    assert run["analysis"]["result"] == direct
    client.review(campaign, run["run"], 1)
    directory = client.directory / "report"
    client.command("export", "--db", client.db, "--campaign", campaign, "--run", run["run"], "--directory", directory)
    report = json.loads((directory / "snapshot.json").read_text())
    assert report["analysis"]["result"] == direct
    assert report["input"] == data
    assert report["review"]["action"] == "accept"
    assert client.command("verify-report", directory)["verified"]
    (directory / "summary.csv").write_text("replacement")
    client.command("verify-report", directory, ok=False)
