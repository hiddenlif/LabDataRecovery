"""Explicit study assumptions. Defaults are demonstration settings, not release specifications."""
from copy import deepcopy
from .codec import number, integer, text
from .errors import WorkbenchError

DEFAULTS = {
    "screening": {"min_zprime": 0.4, "min_doses": 6, "max_ic50_um": 8.0,
                  "nuisance_margin": 4.0, "max_fit_rmse": 12.0, "uncertainty_confidence": 0.95},
    "bridge": {"reference": "reference", "candidate": "candidate", "min_donors": 6,
               "equivalence_low": 0.8, "equivalence_high": 1.25,
               "confidence": 0.90, "bootstrap_samples": 1000, "seed": 1729},
    "stability": {"limit": 70.0, "confidence": 0.95, "max_time_h": 72.0,
                  "max_extrapolation": 1.5, "min_times": 3},
    "rare_events": {"confidence": 0.95, "max_relative_error": 0.35,
                    "max_cv": 0.25, "min_replicates": 3},
}


def resolve(kind, updates=None):
    if updates is not None and not isinstance(updates, dict):
        raise WorkbenchError("policy must be an object")
    p = deepcopy(DEFAULTS[kind])
    unknown = set(updates or {}) - p.keys()
    if unknown:
        raise WorkbenchError(f"Unknown policy fields: {', '.join(sorted(unknown))}")
    p.update(updates or {})
    for k, v in p.items():
        if k in {"reference", "candidate"}:
            text(v, k)
        else:
            number(v, k)
    if "confidence" in p and not 0.5 < p["confidence"] < 1:
        raise WorkbenchError("confidence must lie strictly between 0.5 and 1")
    for k in {"min_doses", "min_donors", "min_times", "min_replicates"} & p.keys():
        integer(p[k], k, 3)
    if kind == "screening":
        if not 0.5 < p["uncertainty_confidence"] < 1:
            raise WorkbenchError("uncertainty_confidence must lie strictly between 0.5 and 1")
        number(p["min_zprime"], "min_zprime", -10, 1)
        for k in ["max_ic50_um", "nuisance_margin", "max_fit_rmse"]:
            number(p[k], k, 1e-10)
    if kind == "bridge":
        integer(p["bootstrap_samples"], "bootstrap_samples", 200)
        if p["bootstrap_samples"] > 20000:
            raise WorkbenchError("bootstrap_samples cannot exceed 20000")
        integer(p["seed"], "seed", 0)
        if not 0 < p["equivalence_low"] < 1 < p["equivalence_high"]:
            raise WorkbenchError("Equivalence bounds must straddle 1")
        if p["reference"] == p["candidate"]:
            raise WorkbenchError("Reference and candidate methods must differ")
    if kind == "stability":
        number(p["max_time_h"], "max_time_h", 0)
        number(p["max_extrapolation"], "max_extrapolation", 1, 3)
    if kind == "rare_events":
        number(p["max_relative_error"], "max_relative_error", 0, 1)
        number(p["max_cv"], "max_cv", 0, 1)
    return p

