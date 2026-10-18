"""Combine independent assay evidence without claiming a corrected biological potency."""
from collections import defaultdict
from .dispensing import resolve
from .plates import normalize
from .curves import fit_curve


def analyze(data, policy):
    resolved, excluded, transfer_evidence = resolve(data)
    observations, plates, plate_exclusions = normalize(resolved, policy["min_zprime"], plate_assays={r["plate"]:r["assay"] for r in data["records"]})
    unresolved, sources = set(), {}
    if 'calibration' in data:
        from .calibration_graph import apply
        observations, unresolved, sources = apply(data, observations)
    instrumented = {e["plate"] for e in data.get("telemetry", [])}
    by_id = {r["id"]:r for r in data["records"]}
    history_plates = {by_id[b["record_id"]]["plate"] for h in transfer_evidence for b in h["bindings"]}
    for plate in plates:
        plate["dispense_mode"] = "transfer_history" if plate["plate"] in history_plates else "calibrated" if plate["plate"] in instrumented else "nominal"
    grouped = defaultdict(list)
    for row in observations:
        grouped[(row["compound"], row["assay"])].append(row)
    compounds = sorted({r["compound"] for r in data["records"] if r["role"] == "sample"})
    results = []
    for compound in compounds:
        channels = {assay: fit_curve(grouped[(compound, assay)], policy["min_doses"], policy["max_fit_rmse"])
                    for assay in ["primary", "counter", "viability", "orthogonal"]}
        if 'calibration' in data:
            from .uncertainty import propagate
            for assay, curve in list(channels.items()):
                if (compound,assay) in unresolved:
                    channels[assay] = dict(curve, status='calibration_unresolved', interval_um=None)
                else:
                    channels[assay] = propagate(curve, grouped[(compound,assay)], sources, policy['uncertainty_confidence'])
        primary = channels["primary"]
        flags = []
        if primary["status"] == "unbracketed" and primary.get("bound") == "above_range" and primary["dose_range_um"][1] >= policy["max_ic50_um"]:
            disposition = "no_primary_activity_in_range"
        elif primary["status"] != "fit":
            disposition = "insufficient_evidence"
        elif primary["ic50_um"] > policy["max_ic50_um"]:
            disposition = "outside_potency_window"
        else:
            if 'calibration' in data and primary['interval_um'][1] > policy['max_ic50_um']:
                flags.append('primary_potency_uncertain')
            for assay in ["counter", "viability"]:
                channel = channels[assay]
                if channel["status"] == "fit":
                    if channel["interval_um"][0] <= policy["nuisance_margin"] * primary["interval_um"][1]:
                        flags.append(assay + "_activity_near_primary")
                elif not (channel["status"] == "unbracketed" and channel.get("bound") == "above_range"
                          and channel["dose_range_um"][1] >= policy["nuisance_margin"] * primary["interval_um"][1]):
                    flags.append(assay + "_unresolved")
            orth = channels["orthogonal"]
            if orth["status"] != "fit" or orth["ic50_um"] > policy["max_ic50_um"]:
                flags.append("orthogonal_confirmation_missing")
            disposition = "supported_for_review" if not flags else "followup_required"
        results.append({"compound": compound, "disposition": disposition, "flags": flags, "channels": channels})
    return {"transfer_history": transfer_evidence or None, "compounds": results, "plates": plates, "excluded": sorted(excluded + plate_exclusions, key=lambda r: r["id"]),
            "identity_catalog": data.get("identity_catalog", []), "source_records": data.get("source_records", []),
            "calibration": ({"revision":data['calibration']['revision'], "method":"first_order_log_dose",
                             "confidence":policy['uncertainty_confidence']} if 'calibration' in data else None),
            "interpretation": "Assay evidence for scientist review; no target-specificity or clinical claim."}

