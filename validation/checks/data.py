import math
import random


def screening(seed=91, nominal_scale=1):
    rng = random.Random(seed)
    rows, telemetry = [], []
    for assay, potency in [("primary", .75), ("counter", 200), ("viability", 300), ("orthogonal", 1.0)]:
        plate = "plate-" + assay
        vehicle = 16000 if assay == "primary" else 8000
        bottom = 200
        for role, value in [("vehicle", vehicle), ("positive", bottom)]:
            for rep in range(4):
                rows.append({"id": f"{plate}-{role}-{rep}", "plate": plate, "well": f"{role}{rep}",
                             "assay": assay, "role": role, "signal": value + (-1)**rep * 2})
        for index, dose in enumerate([.005, .02, .08, .3, .9, 2.5, 8, 25, 80]):
            for rep in range(3):
                well = f"W{index}-{rep}"
                effect = 1 / (1 + (potency / dose) ** 1.3)
                rows.append({"id": f"{plate}-{well}", "plate": plate, "well": well, "assay": assay,
                             "role": "sample", "compound": "compound-" + str(seed), "dose": dose * nominal_scale,
                             "dose_unit": "uM", "signal": vehicle - (vehicle-bottom) * effect + rng.uniform(-1, 1)})
                telemetry.append({"plate": plate, "well": well, "revision": 1, "status": "ok",
                                  "actual_dose": dose * 1000, "dose_unit": "nM"})
    rng.shuffle(rows); rng.shuffle(telemetry)
    return {"kind": "screening", "records": rows, "telemetry": telemetry}


def bridge(ratios=None, samples=None):
    ratios = ratios or [1.04] * 8
    samples = samples or [1] * len(ratios)
    rows = []
    for donor, ratio in enumerate(ratios):
        for sample in range(samples[donor]):
            base = .2 + donor * .01 + sample * .001
            for method, value, unit in [("reference", base, "fraction"), ("candidate", base * ratio * 100, "%")]:
                for replicate in range(2):
                    rows.append({"id": f"{donor}-{sample}-{method}-{replicate}", "donor": f"D{donor:02}",
                                 "sample": f"S{sample}", "method": method, "value": value, "unit": unit})
    return {"kind": "bridge", "records": rows}


def stability(noise=False):
    rows = []
    for batch, slope in [("slow", -.2), ("fast", -1.0)]:
        for time in [0, 10, 20, 30]:
            for rep in range(3):
                error = ((rep-1) * (1 + time/10)) if noise else 0
                rows.append({"id": f"{batch}-{time}-{rep}", "batch": batch, "time": time * 60,
                             "time_unit": "min", "value": 100 + slope*time + error,
                             "weight": 1/(1+time/10)**2})
    return {"kind": "stability", "records": rows}


def counts(blank=0, totals=1000000):
    rows = []
    for batch in ["one", "two"]:
        rows.append({"id": batch+"-blank", "batch": batch, "level": "blank",
                     "events": blank, "total": totals, "expected_fraction": 0})
        for level, rate in [("low", .001), ("high", .01)]:
            for rep in range(4):
                rows.append({"id": f"{batch}-{level}-{rep}", "batch": batch, "level": level,
                             "events": round(rate*totals) + blank, "total": totals, "expected_fraction": rate})
    return {"kind": "rare_events", "records": rows}

