"""Portable reports are created from one transactional snapshot."""
import csv
import hashlib
import html
import io
import os
from pathlib import Path
import shutil
import tempfile
from .codec import dumps, loads
from .errors import WorkbenchError

STYLE = """
body{font:16px/1.6 system-ui,sans-serif;background:#f4f6f8;color:#183145;margin:0}
main{max-width:1180px;margin:36px auto;padding:40px;background:white;border-radius:16px}
h1{font-size:36px;margin:0 0 8px}h2{margin-top:32px;color:#116c70}small,.muted{color:#607584}
.tag{display:inline-block;background:#e1f3f0;padding:5px 12px;border-radius:20px;font-size:13px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:10px;border-bottom:1px solid #dce5e8}
th{background:#eff5f6}code{word-break:break-all}pre{white-space:pre-wrap;font-size:12px}
.notice{border-left:4px solid #df9d2a;padding:12px 18px;background:#fff9ec}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}
svg{max-width:100%;height:auto;background:#fafcfc;border:1px solid #e0e8eb;border-radius:8px}
details{margin:24px 0}a{color:#116c70}@media(max-width:800px){main{margin:12px;padding:20px}.grid{display:block}}
"""


def esc(value):
    return html.escape(str(value))


def table(rows):
    if not rows:
        return '<p class="muted">No records.</p>'
    keys = list(rows[0])
    def cell(value):
        if value is None:
            return "Not estimated"
        if isinstance(value, float):
            return f"{value:.6g}"
        return dumps(value) if isinstance(value, (dict, list)) else str(value)
    return "<table><thead><tr>" + "".join(f"<th>{esc(k.replace('_', ' '))}</th>" for k in keys) + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{esc(cell(row.get(k)))}</td>" for k in keys) + "</tr>" for row in rows) + "</tbody></table>"


def summary_rows(analysis):
    r, kind = analysis["result"], analysis["kind"]
    if kind == "screening":
        return [{"compound": v["compound"], "disposition": v["disposition"],
                 "primary_ic50_um": v["channels"]["primary"]["ic50_um"], "flags": ", ".join(v["flags"])} for v in r["compounds"]]
    if kind == "bridge":
        return [{"status": r["status"], "donors": r["donor_count"], "ratio": r["ratio"], "interval": r["interval"]}]
    if kind == "stability":
        return [{"batch": b["batch"], "status": b["status"], "supported_time_h": b["supported_time_h"],
                 "slope_per_h": b.get("slope_per_h")} for b in r["batches"]]
    return r["levels"]


def curve_svg(analysis):
    series = []
    if analysis["kind"] == "stability":
        for batch in analysis["result"]["batches"]:
            if batch["status"] == "estimated":
                series.append((batch["batch"], [(r["time_h"], r["lower_mean_bound"]) for r in batch["curve"]]))
        xlabel = "Time (hours); lines show lower mean-response bounds"
    elif analysis["kind"] == "screening":
        import math
        for compound in analysis["result"]["compounds"]:
            points = compound["channels"]["primary"]["observations"]
            series.append((compound["compound"], sorted((math.log10(r["dose_um"]), r["inhibition"]) for r in points)))
        xlabel = "Log10 concentration (micromolar); primary assay inhibition (%)"
    else:
        return ""
    points = [p for _, rows in series for p in rows]
    if not points:
        return ""
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    colors = ["#147d92", "#d57d36", "#664aaa", "#36855c", "#ba4b6b", "#6a6e27"]
    body = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 390" role="img" aria-label="Analysis curves">']
    body.append('<path d="M65 25V315H965" fill="none" stroke="#738a95"/>')
    for frac in [0, .25, .5, .75, 1]:
        y = 315 - frac * 280
        body.append(f'<text x="8" y="{y}" font-size="12">{ymin + frac * (ymax-ymin):.2g}</text>')
        x = 65 + frac * 890
        body.append(f'<text x="{x}" y="335" font-size="12">{xmin + frac * (xmax-xmin):.2g}</text>')
    for i, (name, rows) in enumerate(series):
        coords = [(65 + (x-xmin) / max(xmax-xmin, 1e-9) * 890, 315 - (y-ymin) / max(ymax-ymin, 1e-9) * 280) for x, y in rows]
        color = colors[i % len(colors)]
        if analysis["kind"] == "stability":
            body.append(f'<polyline points="{" ".join(f"{x:.2f},{y:.2f}" for x,y in coords)}" stroke="{color}" fill="none" stroke-width="2"/>')
        else:
            body.extend(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" fill="{color}"/>' for x, y in coords)
        body.append(f'<text x="{70 + i*145}" y="360" fill="{color}" font-size="12">{esc(name)}</text>')
    body.append(f'<text x="65" y="382" font-size="12">{esc(xlabel)}</text></svg>')
    return "".join(body)


def transfer_rows(analysis):
    return [dict(campaign=h['campaign'], history_revision=h['revision'], **b)
            for h in analysis['result'].get('transfer_history') or [] for b in h['bindings']]


def render(snapshot):
    a = snapshot["analysis"]
    title = snapshot["campaign"]["name"]
    review = snapshot.get("review")
    status = review["action"] if review else "Awaiting review"
    notice = "Historical snapshot: a newer input revision is available." if snapshot["superseded"] else "This report records the selected analysis and its review snapshot."
    details = ""
    if a["kind"] == "screening":
        details = "<h2>Plate quality</h2>" + table(a["result"]["plates"]) + "<h2>Excluded observations</h2>" + table(a["result"]["excluded"])
        if a["result"].get("identity_catalog"):
            details += "<h2>Campaign identities</h2>" + table(a["result"]["identity_catalog"])
    elif a["kind"] == "bridge":
        details = "<h2>Independent donors</h2>" + table(a["result"]["donors"]) + "<h2>Unpaired or unusable samples</h2>" + table(a["result"]["excluded"])
    elif a["kind"] == "rare_events":
        details = "<h2>Batch and level qualification</h2>" + table(a["result"]["batch_levels"])
    if a['result'].get('transfer_history'):
        details += '<h2>Dispensing transfer history</h2>' + table(transfer_rows(a))
        details += '<p>Concentrations reconstruct homogeneous liquid transfers from corrected measured volumes. Unknown contents remain unresolved.</p>'
    if a['result'].get('calibration'):
        details += '<h2>Calibration uncertainty</h2><pre>' + esc(dumps(a['result']['calibration'])) + '</pre>'
        details += '<p>Intervals use first-order log-dose propagation with shared error sources; this is a local approximation.</p>'
        details += table([dict(compound=c['compound'], assay=assay, **channel.get('uncertainty', {}))
                          for c in a['result']['compounds'] for assay,channel in c['channels'].items()
                          if 'uncertainty' in channel])
    if "ingestion" in snapshot["input"]:
        evidence = snapshot["input"]["ingestion"]
        details += "<h2>Instrument source lineage</h2>" + table(evidence["record_lineage"])
        details += "<details><summary>Delivery manifest</summary><pre>" + esc(dumps(evidence["manifest"])) + "</pre></details>"
    return f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} | TrueGate</title><style>{STYLE}</style><main><small>TRUEGATE · SCIENTIFIC WORKBENCH</small><h1>{esc(title)}</h1><span class="tag">{esc(a["kind"])}</span> <span class="tag">{esc(status)}</span><p class="notice">{esc(notice)}</p><p>{esc(a["result"].get("interpretation", ""))}</p><h2>Results</h2>{table(summary_rows(a))}<p>{curve_svg(a)}</p>{details}<h2>Traceability</h2>{table([{"input revision":snapshot["dataset_revision"],"run":snapshot["run"],"engine":a["engine_version"]}])}<p>Input fingerprint: <code>{esc(a["input_sha256"])}</code><br>Policy fingerprint: <code>{esc(a["policy_sha256"])}</code></p><details><summary>Analysis settings</summary><pre>{esc(dumps(a["policy"]))}</pre></details><details><summary>Review record</summary><pre>{esc(dumps(review))}</pre></details><p><a href="summary.csv">Download summary</a> · <a href="snapshot.json">Complete analysis and inputs</a> · <a href="manifest.json">File fingerprints</a></p><small>Example studies are synthetic demonstrations. This application does not certify clinical performance or authorize product release.</small></main></html>'


def export(snapshot, destination):
    destination = Path(destination)
    if destination.exists():
        raise WorkbenchError("Report destination already exists; choose a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".report-", dir=destination.parent))
    try:
        (temporary / "snapshot.json").write_text(dumps(snapshot) + "\n")
        (temporary / "index.html").write_text(render(snapshot), encoding="utf-8")
        rows = summary_rows(snapshot["analysis"])
        with (temporary / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
        evidence = transfer_rows(snapshot['analysis'])
        if snapshot['analysis']['result'].get('transfer_history'):
            fields = ['campaign','history_revision','record_id','vessel','sequence','status','dose_um','volume_ul','known','compound','amounts_pmol','lineage']
            with (temporary/'transfer-bindings.csv').open('w',newline='',encoding='utf-8') as stream:
                writer = csv.DictWriter(stream,fieldnames=fields)
                writer.writeheader()
                writer.writerows({k:(dumps(row.get(k)) if isinstance(row.get(k),(dict,list)) else row.get(k)) for k in fields} for row in evidence)
        manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(temporary.iterdir())}
        (temporary / "manifest.json").write_text(dumps(manifest) + "\n")
        os.rename(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {"report": str(destination), "files": manifest}


def verify(destination):
    directory = Path(destination)
    manifest = loads((directory / "manifest.json").read_text())
    if not isinstance(manifest, dict) or set(manifest) not in ({"snapshot.json", "index.html", "summary.csv"}, {"snapshot.json", "index.html", "summary.csv", "transfer-bindings.csv"}):
        raise WorkbenchError("Unexpected report manifest")
    for name, sha in manifest.items():
        p = directory / name
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != sha:
            raise WorkbenchError(f"Report integrity check failed: {name}")
    return {"verified": True, "files": len(manifest)}

