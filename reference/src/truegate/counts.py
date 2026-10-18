"""Background-corrected rare-event rates with simultaneous binomial bounds."""
from collections import defaultdict
import numpy as np
from scipy.stats import beta
from .errors import WorkbenchError


def interval(events, total, alpha):
    lower = 0.0 if events == 0 else float(beta.ppf(alpha / 2, events, total - events + 1))
    upper = 1.0 if events == total else float(beta.ppf(1 - alpha / 2, events + 1, total - events))
    return lower, upper


def analyze(data, policy):
    blanks, positive = defaultdict(list), []
    nominal = {}
    all_levels = {}
    for row in data["records"]:
        level, fraction = row["level"], row["expected_fraction"]
        if level in all_levels and all_levels[level] != fraction:
            raise WorkbenchError("A level must have the same expected fraction across records")
        all_levels[level] = fraction
        if fraction == 0:
            blanks[row["batch"]].append(row)
        else:
            if row["level"] in nominal and nominal[row["level"]] != row["expected_fraction"]:
                raise WorkbenchError("A level must have the same expected fraction across records")
            nominal[row["level"]] = row["expected_fraction"]
            positive.append(row)
    if not positive:
        raise WorkbenchError("At least one nonblank level is required")
    batches = {r["batch"] for r in positive}
    if batches - blanks.keys():
        raise WorkbenchError("Every sample batch requires a matched blank")
    # Allocate the family error budget to every unique interval used in the report.
    alpha = (1 - policy["confidence"]) / (len(positive) + len(batches))
    background = {}
    for batch in sorted(batches):
        count = sum(r["events"] for r in blanks[batch])
        total = sum(r["total"] for r in blanks[batch])
        background[batch] = {"events": count, "total": total, "rate": count / total,
                             "interval": list(interval(count, total, alpha))}
    samples, groups = [], defaultdict(list)
    for row in sorted(positive, key=lambda r: r["id"]):
        blank = background[row["batch"]]
        lo, hi = interval(row["events"], row["total"], alpha)
        net = max(0.0, row["events"] / row["total"] - blank["rate"])
        bounds = [max(0, lo - blank["interval"][1]), max(0, hi - blank["interval"][0])]
        expected = row["expected_fraction"]
        error = policy["max_relative_error"]
        accuracy = bounds[0] >= expected * (1 - error) and bounds[1] <= expected * (1 + error)
        item = {"id": row["id"], "batch": row["batch"], "level": row["level"],
                "net_fraction": net, "interval": bounds, "within_accuracy_bounds": bool(accuracy)}
        samples.append(item); groups[(row["batch"], row["level"])].append(item)
    summaries = []
    for (batch, level), items in sorted(groups.items()):
        values = np.array([r["net_fraction"] for r in items])
        cv = float(values.std(ddof=1) / values.mean()) if len(values) > 1 and values.mean() > 0 else None
        ok = len(items) >= policy["min_replicates"] and cv is not None and cv <= policy["max_cv"] and all(r["within_accuracy_bounds"] for r in items)
        summaries.append({"batch": batch, "level": level, "expected_fraction": nominal[level],
                          "n": len(items), "cv": cv, "qualified": bool(ok)})
    levels = []
    for level, fraction in sorted(nominal.items(), key=lambda item: (item[1], item[0])):
        relevant = [s for s in summaries if s["level"] == level]
        ok = {s["batch"] for s in relevant} == batches and all(s["qualified"] for s in relevant)
        levels.append({"level": level, "expected_fraction": fraction, "qualified": bool(ok)})
    loq = None
    for i, level in enumerate(levels):
        if all(v["qualified"] for v in levels[i:]):
            loq = level["expected_fraction"]
            break
    return {"background": background, "samples": samples, "batch_levels": summaries, "levels": levels,
            "candidate_loq_fraction": loq, "interval_alpha": alpha,
            "status": "candidate_identified" if loq is not None else "not_demonstrated",
            "interpretation": "Independent binomial events assumed; interval accuracy and repeatability are both required."}

