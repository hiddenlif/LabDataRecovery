"""Resolve dispensing revisions before fitting and preserve per-well exclusions."""
from collections import defaultdict
from .codec import require, integer, number, digest, text
from .units import convert
from .errors import WorkbenchError


def reconcile(records, telemetry):
    if not isinstance(telemetry, list):
        raise WorkbenchError("telemetry must be an array")
    wells = {}
    for row in records:
        key = (row["plate"], row["well"])
        if key in wells:
            raise WorkbenchError(f"Duplicate physical well: {key}")
        wells[key] = row
    revisions = defaultdict(dict)
    for event in telemetry:
        require(event, ["plate", "well", "revision", "status"], "dispense event")
        key = (event["plate"], event["well"])
        if key not in wells or wells[key]["role"] != "sample":
            raise WorkbenchError(f"Telemetry references unknown sample well: {key}")
        rev = integer(event["revision"], "revision", 1)
        if event["status"] not in {"ok", "failed", "cancelled"}:
            raise WorkbenchError("Unknown transfer status")
        if event["status"] == "ok":
            require(event, ["actual_dose", "dose_unit"], "successful transfer")
            convert(event["actual_dose"], event["dose_unit"], "concentration")
        if rev in revisions[key] and digest(event) != digest(revisions[key][rev]):
            raise WorkbenchError(f"Conflicting telemetry revision: {key} revision {rev}")
        revisions[key][rev] = event
    resolved, exclusions = [], []
    for row in sorted(records, key=lambda r: (r["plate"], r["well"])):
        copy = dict(row)
        if row["role"] != "sample":
            resolved.append(copy)
            continue
        key = (row["plate"], row["well"])
        events = revisions.get(key, {})
        event = events[max(events)] if events else None
        if row["plate"] in {e["plate"] for e in telemetry} and event is None:
            exclusions.append({"id": row["id"], "reason": "missing_telemetry"})
            continue
        if event and event["status"] != "ok":
            exclusions.append({"id": row["id"], "reason": event["status"]})
            continue
        dose = convert(event["actual_dose"], event["dose_unit"], "concentration") if event else convert(row["dose"], row["dose_unit"], "concentration")
        if dose <= 0:
            exclusions.append({"id": row["id"], "reason": "zero_dose"})
            continue
        copy.update(dose_um=dose, calibration_revision=event["revision"] if event else None,
                    dose_source="calibrated" if event else "nominal")
        resolved.append(copy)
    return resolved, exclusions

