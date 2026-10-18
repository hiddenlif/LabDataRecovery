"""Increasing four-parameter concentration-response fits on normalized inhibition."""
import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit


def response(log_dose, parameters):
    bottom, top, log_mid, slope = parameters
    return bottom + (top - bottom) * expit(slope * (log_dose - log_mid))


def fit_curve(rows, min_doses, max_rmse):
    rows = sorted(rows, key=lambda r: (r["dose_um"], r["id"]))
    x = np.array([r["dose_um"] for r in rows], dtype=float)
    y = np.array([r["inhibition"] for r in rows], dtype=float)
    result = {"n": len(rows), "dose_count": len(set(x)), "ic50_um": None,
              "slope": None, "rmse": None, "interval_um": None,
              "dose_range_um": [float(x.min()), float(x.max())] if len(x) else None,
              "max_observed_inhibition": float(y.max()) if len(y) else None,
              "observations": [{"id": r["id"], "dose_um": r["dose_um"],
                                "inhibition": r["inhibition"], "dose_source": r["dose_source"],
                                **({"calibration_revision":None, "transfer_binding":r["transfer_binding"]} if "transfer_binding" in r else {})} for r in rows]}
    if len(set(x)) < min_doses or len(x) <= 4:
        return dict(result, status="insufficient_doses")
    if y.min() > 50 or y.max() < 50:
        return dict(result, status="unbracketed", bound="below_range" if y.min() > 50 else "above_range")
    lx = np.log(x)
    bounds = ([-30, 50, lx.min() - 2, 0.15], [50, 130, lx.max() + 2, 6])
    options = []
    for slope in [0.6, 1.2, 2.5]:
        p0 = [max(-20, min(float(y.min()), 40)), min(120, max(float(y.max()), 60)), float(np.median(lx)), slope]
        options.append(least_squares(lambda p: response(lx, p) - y, p0, bounds=bounds,
                                     max_nfev=2000, ftol=1e-10, xtol=1e-10, gtol=1e-10))
    best = min(options, key=lambda f: float(np.sum(f.fun ** 2)))
    rmse = float(np.sqrt(np.mean(best.fun ** 2)))
    mid = float(np.exp(best.x[2]))
    result.update(ic50_um=mid, slope=float(best.x[3]), rmse=rmse,
                  bottom=float(best.x[0]), top=float(best.x[1]))
    if not best.success or rmse > max_rmse:
        return dict(result, status="poor_fit")
    gram = best.jac.T @ best.jac
    if np.linalg.matrix_rank(gram) < 4 or np.linalg.cond(gram) > 1e12:
        return dict(result, status="poor_identifiability")
    variance = float(np.sum(best.fun ** 2) / (len(x) - 4))
    covariance = np.linalg.inv(gram) * variance
    log_se = float(np.sqrt(max(0, covariance[2, 2])))
    if log_se > 2:
        return dict(result, status="poor_identifiability")
    result["log_ic50_variance"] = float(max(0, covariance[2, 2]))
    result["interval_um"] = [float(mid * np.exp(-1.96 * log_se)), float(mid * np.exp(1.96 * log_se))]
    return dict(result, status="fit")

