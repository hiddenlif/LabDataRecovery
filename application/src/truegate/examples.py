"""Fresh deterministic synthetic measurements for demonstrations and development."""
from pathlib import Path
import numpy as np
from .codec import dumps


def screening(seed=41):
    rng = np.random.default_rng(seed)
    records, telemetry = [], []
    doses = np.geomspace(0.008, 40, 10)
    compounds = {"HG-101": [0.6, 250, 300, .9], "HG-102": [1.4, .8, 300, 150],
                 "HG-103": [.9, 300, 1.1, 1.2], "HG-104": [150, 300, 300, 150],
                 "HG-105": [1.2, .6, 300, 1.0], "HG-106": [2.0, 300, 300, 150]}
    for ai, assay in enumerate(["primary", "counter", "viability", "orthogonal"]):
        plate = f"P-{ai+1}"
        slot = 0
        def well(index):
            return f"{chr(65 + index // 24)}{index % 24 + 1:02d}"
        for role, signal in [("vehicle", 12000), ("positive", 500)]:
            for rep in range(4):
                records.append({"id": f"{plate}-{slot}", "plate": plate, "well": well(slot),
                                "assay": assay, "role": role, "signal": float(signal + rng.normal(0, 12))})
                slot += 1
        for ci, (compound, potencies) in enumerate(compounds.items()):
            for dose in doses:
                for rep in range(3):
                    actual = float(dose * (1.7 if ci == 0 else .85 if ci == 2 else 1.0))
                    inhibition = 100 / (1 + (potencies[ai] / actual) ** 1.15)
                    signal = float(12000 - 11500 * inhibition / 100 + rng.normal(0, 30))
                    row = {"id": f"{plate}-{slot}", "plate": plate, "well": well(slot), "assay": assay,
                           "role": "sample", "compound": compound, "dose": float(dose), "dose_unit": "uM", "signal": signal}
                    records.append(row)
                    telemetry.append({"plate": plate, "well": well(slot), "revision": 1, "status": "ok",
                                      "actual_dose": actual * 1000, "dose_unit": "nM"})
                    slot += 1
    rng.shuffle(records); rng.shuffle(telemetry)
    return {"kind": "screening", "description": "Synthetic reporter assay panel", "records": records, "telemetry": telemetry}


def bridge(seed=42):
    rng = np.random.default_rng(seed)
    records = []
    for donor in range(10):
        for sample in range(9 if donor == 0 else 2):
            baseline = float(rng.uniform(.15, .7))
            ratio = 1.4 if donor == 0 else .97 + donor * .004
            for method, value in [("reference", baseline), ("candidate", baseline * ratio)]:
                for rep in range(3 if method == "reference" else 2):
                    value2 = float(value * (1 + rng.normal(0, .008)))
                    unit, scale = ("%", 100) if method == "candidate" else ("fraction", 1)
                    records.append({"id": f"D{donor}-S{sample}-{method}-{rep}", "donor": f"D{donor:02}",
                                    "sample": f"S{sample}", "method": method, "value": value2 * scale, "unit": unit})
    rng.shuffle(records)
    return {"kind": "bridge", "description": "Synthetic paired donor study", "records": records}


def stability(seed=43):
    rng = np.random.default_rng(seed)
    records = []
    for i, slope in enumerate([-.35, -.7, -.95]):
        for hour in [0, 12, 24, 36]:
            for replicate in range(3):
                sd = 1 + hour / 24
                records.append({"id": f"B{i}-{hour}-{replicate}", "batch": f"B{i+1}", "time": hour * 60,
                                "time_unit": "min", "value": float(96 + slope * hour + rng.normal(0, sd)), "weight": 1 / sd ** 2})
    rng.shuffle(records)
    return {"kind": "stability", "description": "Synthetic batch hold-time study", "records": records}


def rare_events(seed=44):
    rng = np.random.default_rng(seed)
    records = []
    for batch, blank in [("A", .00002), ("B", .00005)]:
        for rep in range(4):
            records.append({"id": f"{batch}-blank-{rep}", "batch": batch, "level": "blank", "events": int(rng.binomial(500000, blank)),
                            "total": 500000, "expected_fraction": 0})
        for level, rate in [("low", .0002), ("medium", .001), ("high", .005)]:
            for rep in range(4):
                records.append({"id": f"{batch}-{level}-{rep}", "batch": batch, "level": level,
                                "events": int(rng.binomial(500000, rate + blank)), "total": 500000, "expected_fraction": rate})
    rng.shuffle(records)
    return {"kind": "rare_events", "description": "Synthetic rare-population qualification", "records": records}


def write(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    result = {}
    for kind, factory in [("screening", screening), ("bridge", bridge), ("stability", stability), ("rare_events", rare_events)]:
        target = root / f"{kind}.json"
        if target.exists():
            raise FileExistsError(f"Preserving existing example: {target}")
        target.write_text(dumps(factory()) + "\n")
        result[kind] = str(target)
    return result

