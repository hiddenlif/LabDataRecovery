"""Batch-specific weighted trends and a conservative mean-response time bound."""
from collections import defaultdict
import numpy as np
from scipy.stats import t
from scipy.optimize import brentq
from .units import convert


def fit_batch(name, rows, policy):
    rows = sorted(rows, key=lambda r: (convert(r["time"], r["time_unit"], "time"), r["id"]))
    x = np.array([convert(r["time"], r["time_unit"], "time") for r in rows])
    y = np.array([r["value"] for r in rows])
    w = np.array([r["weight"] for r in rows])
    output = {"batch": name, "n": len(rows), "time_count": len(set(x)),
              "supported_time_h": None, "status": "insufficient_timepoints"}
    if len(set(x)) < policy["min_times"] or len(x) <= 2:
        return output
    design = np.column_stack([np.ones(len(x)), x])
    gram = design.T @ (w[:, None] * design)
    if np.linalg.matrix_rank(gram) < 2:
        return dict(output, status="singular_design")
    inverse = np.linalg.inv(gram)
    beta = inverse @ (design.T @ (w * y))
    residual = y - design @ beta
    variance = float(np.sum(w * residual ** 2) / (len(x) - 2))
    covariance = inverse * variance
    quantile = float(t.ppf(policy["confidence"], len(x) - 2))

    def lower_bound(hour):
        v = np.array([1, hour])
        return float(v @ beta - quantile * np.sqrt(max(0, v @ covariance @ v)))

    maximum = min(policy["max_time_h"], float(x.max()) * policy["max_extrapolation"])
    if lower_bound(0) < policy["limit"]:
        supported, reason = 0.0, "baseline_not_supported"
    elif lower_bound(maximum) >= policy["limit"]:
        supported, reason = maximum, "limited_by_observation_policy"
    else:
        supported = float(brentq(lambda hour: lower_bound(hour) - policy["limit"], 0, maximum, xtol=1e-9))
        reason = "confidence_bound_crossing"
    grid = np.linspace(0, maximum, 25)
    output.update(status="estimated", intercept=float(beta[0]), slope_per_h=float(beta[1]),
                  residual_variance=variance, covariance=covariance.tolist(), degrees_of_freedom=len(x) - 2,
                  observed_max_h=float(x.max()), evaluation_cap_h=maximum, supported_time_h=supported,
                  limiting_reason=reason,
                  curve=[{"time_h": float(hour), "mean": float(beta[0] + beta[1] * hour),
                          "lower_mean_bound": lower_bound(hour)} for hour in grid])
    return output


def analyze(data, policy):
    groups = defaultdict(list)
    for row in data["records"]:
        groups[row["batch"]].append(row)
    batches = [fit_batch(name, rows, policy) for name, rows in sorted(groups.items())]
    missing = [b["batch"] for b in batches if b["status"] != "estimated"]
    supported = None if missing else min(b["supported_time_h"] for b in batches)
    limiting = [] if missing else [b["batch"] for b in batches if abs(b["supported_time_h"] - supported) < 1e-7]
    return {"batches": batches, "supported_time_h": supported, "limiting_batches": limiting,
            "status": "incomplete" if missing else "estimated", "incomplete_batches": missing,
            "interpretation": "One-sided confidence bounds for batch mean responses; not a product shelf-life approval."}

