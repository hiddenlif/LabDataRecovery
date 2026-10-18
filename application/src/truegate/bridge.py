"""Paired method comparisons with donors as the independent sampling unit."""
from collections import defaultdict
import numpy as np
from .errors import WorkbenchError

UNITS = {"fraction": ("fraction", 1), "%": ("fraction", 0.01),
         "ng/mL": ("mass", 1), "ug/mL": ("mass", 1000), "µg/mL": ("mass", 1000)}


def paired_values(records, reference, candidate):
    groups = defaultdict(lambda: defaultdict(list))
    families = set()
    for row in sorted(records, key=lambda r: r["id"]):
        if row["method"] not in {reference, candidate}:
            raise WorkbenchError(f"Unexpected method: {row['method']}")
        if row["unit"] not in UNITS:
            raise WorkbenchError(f"Unsupported bridge unit: {row['unit']}")
        family, factor = UNITS[row["unit"]]
        families.add(family)
        groups[(row["donor"], row["sample"])][row["method"]].append(row["value"] * factor)
    if len(families) != 1:
        raise WorkbenchError("Cannot compare different measurement families")
    pairs, excluded = [], []
    for (donor, sample), methods in sorted(groups.items()):
        if reference not in methods or candidate not in methods:
            excluded.append({"donor": donor, "sample": sample, "reason": "unpaired"})
            continue
        left, right = float(np.mean(methods[reference])), float(np.mean(methods[candidate]))
        if min(left, right) <= 0:
            excluded.append({"donor": donor, "sample": sample, "reason": "nonpositive_mean"})
            continue
        pairs.append({"donor": donor, "sample": sample, "reference_mean": left,
                      "candidate_mean": right, "log_ratio": float(np.log(right / left)),
                      "replicates": {reference: len(methods[reference]), candidate: len(methods[candidate])}})
    return pairs, excluded


def analyze(data, policy):
    pairs, excluded = paired_values(data["records"], policy["reference"], policy["candidate"])
    grouped = defaultdict(list)
    for pair in pairs:
        grouped[pair["donor"]].append(pair["log_ratio"])
    donors = [{"donor": k, "paired_samples": len(v), "log_ratio": float(np.mean(v))}
              for k, v in sorted(grouped.items())]
    result = {"pairs": pairs, "excluded": excluded, "donors": donors, "donor_count": len(donors),
              "ratio": None, "interval": None, "status": "insufficient_donors"}
    if len(donors) < policy["min_donors"]:
        return result
    values = np.array([d["log_ratio"] for d in donors])
    # The donor, rather than a technical replicate or sample, is the resampling unit.
    rng = np.random.default_rng(policy["seed"])
    estimates = np.empty(policy["bootstrap_samples"])
    for i in range(len(estimates)):
        estimates[i] = np.mean(values[rng.integers(0, len(values), len(values))])
    alpha = 1 - policy["confidence"]
    low, high = np.exp(np.quantile(estimates, [alpha / 2, 1 - alpha / 2], method="linear"))
    ratio = float(np.exp(values.mean()))
    jackknife = [float(np.exp(np.delete(values, i).mean())) for i in range(len(values))]
    equivalent = low >= policy["equivalence_low"] and high <= policy["equivalence_high"]
    result.update(ratio=ratio, interval=[float(low), float(high)],
                  leave_one_donor_out_range=[min(jackknife), max(jackknife)],
                  status="within_equivalence_bounds" if equivalent else "equivalence_not_demonstrated",
                  interpretation="Paired donor-level comparison under the selected study policy.")
    return result

