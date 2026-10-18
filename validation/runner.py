"""Trusted test process. Candidate modules are imported only by a different UID."""
import json
import os
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET
import pytest

CASES = {"01": "test_01_screening.py", "02": "test_02_bridge.py", "03": "test_03_stability.py",
         "04": "test_04_rare_events.py", "05": "test_05_lineage.py",
         "06": "test_07_recovery.py", "07": "test_08_identity.py", "08": "test_11_ingestion.py", "10": "test_12_uncertainty.py", "11": "test_13_transfers.py", "11r2": "test_14_corrections.py", "11r3": "test_15_recovery_migration.py", "11r4": "test_16_recovery_evolution.py"}


def main():
    selection = sys.argv[1] if len(sys.argv) > 1 else "all"
    if selection not in {*CASES, "all", "08-full", "10-full", "11-full", "11r2-full", "11r3-full", "11r4-full"}:
        raise SystemExit("Unknown check selection")
    receipt = Path("/receipt")
    receipt.mkdir(exist_ok=True)
    receipt.chmod(0o700)
    os.umask(0o077)
    started = time.monotonic()
    if selection in {'all','11r4-full'}:
        selected = ['/checks']
    elif selection == '11r3-full':
        selected = [str(p) for p in sorted(Path('/checks').glob('test_*.py')) if p.name != 'test_16_recovery_evolution.py']
    elif selection == '11r2-full':
        selected = [str(p) for p in sorted(Path('/checks').glob('test_*.py')) if p.name != 'test_15_recovery_migration.py']
    elif selection == '11-full':
        selected = [str(p) for p in sorted(Path('/checks').glob('test_*.py')) if p.name not in {'test_14_corrections.py','test_15_recovery_migration.py'}]
    elif selection == '10-full':
        selected = [str(p) for p in sorted(Path('/checks').glob('test_*.py')) if p.name not in {'test_13_transfers.py','test_14_corrections.py','test_15_recovery_migration.py'}]
    elif selection == '08-full':
        selected = [str(p) for p in sorted(Path('/checks').glob('test_*.py')) if p.name not in {'test_12_uncertainty.py','test_13_transfers.py','test_14_corrections.py','test_15_recovery_migration.py'}]
    else:
        selected = ['/checks/' + CASES[selection]]
    class Inventory:
        collected = 0
        def pytest_collection_finish(self, session):
            self.collected = len(session.items)
    inventory=Inventory()
    status = int(pytest.main([*selected, "-q", "-p", "no:cacheprovider", "--junitxml=/receipt/junit.xml"],plugins=[inventory]))
    suites = ET.parse(receipt / "junit.xml").getroot()
    counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites.iter("testsuite"))
              for key in ("tests", "failures", "errors", "skipped")}
    result = {"selection": selection, "exit_code": status, **counts,
              "passed": counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"],
              "seconds": round(time.monotonic() - started, 3),
              "collected": inventory.collected,
              "accepted": status == 0 and counts["tests"] == inventory.collected and counts["tests"] > 0 and counts["skipped"] == 0 and counts['errors']==0 and counts['failures']==0}
    (receipt / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
