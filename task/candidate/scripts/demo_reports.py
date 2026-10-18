"""Produce four inspectable example reports from synthetic studies."""
import argparse
from pathlib import Path
from truegate.examples import screening, bridge, stability, rare_events
from truegate.repository import Repository
from truegate.reporting import export, verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=False)
    repo = Repository(args.destination / "demonstrations.db")
    for factory in (screening, bridge, stability, rare_events):
        data = factory()
        campaign = repo.create("Synthetic " + data["kind"].replace("_", " ") + " study", data["kind"])["campaign"]
        imported = repo.import_data(campaign, data)
        run = repo.run(campaign)
        repo.review(campaign, run["run"], "hold", "Demonstration reviewer", "Synthetic data; scientific review remains required", imported["revision"])
        destination = args.destination / data["kind"]
        export(repo.snapshot(campaign, run["run"]), destination)
        assert verify(destination)["verified"]
        print(destination / "index.html")


if __name__ == "__main__":
    main()
