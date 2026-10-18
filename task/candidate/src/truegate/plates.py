"""Normalize each plate using its own assay controls."""
from collections import defaultdict
import numpy as np
from .errors import WorkbenchError


def normalize(records, min_zprime, *, plate_assays=None):
    plates = defaultdict(list)
    for plate in plate_assays or {}:
        plates[plate] = []
    for row in records:
        plates[row["plate"]].append(row)
    observations, diagnostics, exclusions = [], [], []
    for plate, rows in sorted(plates.items()):
        if len({r["assay"] for r in rows}) > 1:
            raise WorkbenchError(f"Plate has inconsistent assay labels: {plate}")
        assay = rows[0]["assay"] if rows else plate_assays[plate]
        negative = [r["signal"] for r in rows if r["role"] == "vehicle"]
        positive = [r["signal"] for r in rows if r["role"] == "positive"]
        reason, zprime, hi, lo = None, None, None, None
        if min(len(negative), len(positive)) < 3:
            reason = "insufficient_controls"
        else:
            hi, lo = float(np.mean(negative)), float(np.mean(positive))
            if hi <= lo:
                reason = "invalid_control_order"
            else:
                zprime = float(1 - 3 * (np.std(negative, ddof=1) + np.std(positive, ddof=1)) / (hi - lo))
                if zprime < min_zprime:
                    reason = "poor_control_separation"
        diagnostics.append({"plate": plate, "assay": assay, "zprime": zprime,
                            "vehicle_mean": hi, "positive_mean": lo, "status": reason or "usable"})
        for row in rows:
            if row["role"] != "sample":
                continue
            if reason:
                exclusions.append({"id": row["id"], "reason": reason})
            else:
                observations.append(dict(row, inhibition=100 * (hi - row["signal"]) / (hi - lo)))
    return observations, diagnostics, exclusions

