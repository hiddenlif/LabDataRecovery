"""Dataset validation shared by direct analysis and stored campaigns."""
from .codec import require, text, number, integer
from .errors import WorkbenchError

KINDS = {"screening", "bridge", "stability", "rare_events"}
ASSAYS = {"primary", "counter", "viability", "orthogonal"}


def validate(data):
    require(data, ["kind", "records"], "dataset")
    if data["kind"] not in KINDS:
        raise WorkbenchError("Unknown study kind")
    rows = data["records"]
    if not isinstance(rows, list) or not rows or len(rows) > 100000:
        raise WorkbenchError("records must contain 1 to 100000 rows")
    seen = set()
    for i, row in enumerate(rows):
        require(row, ["id"], f"record {i}")
        key = text(row["id"], "record id")
        if key != row["id"]:
            raise WorkbenchError("Record identifiers cannot contain surrounding whitespace")
        if key in seen:
            raise WorkbenchError(f"Duplicate record id: {key}")
        seen.add(key)
        kind = data["kind"]
        if kind == "screening":
            require(row, ["plate", "well", "assay", "role", "signal"], key)
            text(row["plate"], "plate"); text(row["well"], "well")
            if row["assay"] not in ASSAYS or row["role"] not in {"sample", "vehicle", "positive"}:
                raise WorkbenchError(f"Invalid assay or role: {key}")
            number(row["signal"], "signal")
            if row["role"] == "sample":
                require(row, ["compound", "dose", "dose_unit"], key)
                text(row["compound"], "compound"); number(row["dose"], "dose", 0)
        elif kind == "bridge":
            require(row, ["donor", "sample", "method", "value", "unit"], key)
            for field in ["donor", "sample", "method", "unit"]:
                text(row[field], field)
            number(row["value"], "value", 0)
        elif kind == "stability":
            require(row, ["batch", "time", "time_unit", "value", "weight"], key)
            text(row["batch"], "batch"); number(row["time"], "time", 0)
            number(row["value"], "value"); number(row["weight"], "weight", 1e-12)
        else:
            require(row, ["batch", "level", "events", "total", "expected_fraction"], key)
            text(row["batch"], "batch"); text(row["level"], "level")
            events = integer(row["events"], "events")
            total = integer(row["total"], "total", 1)
            if events > total:
                raise WorkbenchError("events cannot exceed total")
            number(row["expected_fraction"], "expected_fraction", 0, 1)
    if "transfer_history" in data:
        from .transfer_history import histories
        histories(data)
    if "calibration" in data:
        from .calibration_graph import resolve_model
        resolve_model(data)
    return data

