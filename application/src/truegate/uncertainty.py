"""First-order propagation of shared log-concentration errors through a 4PL fit."""
import math
from statistics import NormalDist
import numpy as np
from scipy.special import expit


def propagate(curve, rows, sources, confidence):
    if curve['status'] != 'fit':
        return curve
    rows = sorted(rows, key=lambda r:(r['dose_um'], r['id']))
    names = sorted(sources)
    x = np.log([r['dose_um'] for r in rows])
    distance = x - math.log(curve['ic50_um'])
    sigmoid = expit(curve['slope'] * distance)
    factor = (curve['top'] - curve['bottom']) * sigmoid * (1-sigmoid)
    jacobian = np.column_stack([1-sigmoid, sigmoid, -factor*curve['slope'], factor*distance])
    loadings = np.array([[r['calibration_loadings'].get(s,0) for s in names] for r in rows]).reshape(len(rows),len(names))
    if np.linalg.matrix_rank(jacobian) < 4 or np.linalg.cond(jacobian)**2 > 1e12:
        return dict(curve, status='poor_identifiability', interval_um=None)
    # Solve the Gauss-Newton normal equations without explicitly inverting them.
    sensitivity = np.linalg.lstsq(jacobian, -factor[:,None]*curve['slope']*loadings, rcond=None)[0][2]
    calibration_sd = math.hypot(*(float(v)*sources[s] for s,v in zip(names,sensitivity)))
    calibration_variance = calibration_sd * calibration_sd
    fit_variance = curve['log_ic50_variance']
    se = math.hypot(math.sqrt(fit_variance), calibration_sd)
    z = -NormalDist().inv_cdf((1-confidence)/2)
    bounds = [math.log(curve['ic50_um']) - z*se, math.log(curve['ic50_um']) + z*se]
    details = {'method':'first_order_log_dose', 'confidence':confidence,
               'fit_log_variance':fit_variance, 'calibration_log_variance':calibration_variance if math.isfinite(calibration_variance) else None,
               'source_sensitivity':{s:float(v) if math.isfinite(v) else None for s,v in zip(names,sensitivity)}}
    if not all(math.isfinite(b) and -700 < b < 700 for b in bounds):
        return dict(curve, status='uncertainty_unbounded', interval_um=None, uncertainty=details)
    return dict(curve, interval_um=[math.exp(b) for b in bounds], uncertainty=details)
