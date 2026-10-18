"""Integrate reconstructed contents with legacy dispensing and plate eligibility."""
from .calibration import reconcile
from .transfer_history import histories


def resolve(data):
    evidence = histories(data)
    if not evidence:
        rows, excluded = reconcile(data['records'], data.get('telemetry', []))
        return rows, excluded, []
    binding = {b['record_id']:(h,b) for h in evidence for b in h['bindings']}
    plates = {r['plate'] for r in data['records'] if r['id'] in binding}
    legacy = [r for r in data['records'] if r['plate'] not in plates]
    resolved, excluded = reconcile(legacy, data.get('telemetry', []))
    for row in data['records']:
        if row['plate'] not in plates:
            continue
        if row['role'] != 'sample':
            resolved.append(dict(row)); continue
        item = binding.get(row['id'])
        if item is None:
            reason = 'missing_transfer_binding'
        else:
            history, sample = item
            reason = {'unknown':'unknown_transfer', 'empty':'empty_vessel', 'zero_dose':'zero_dose'}.get(sample['status'])
        if reason:
            excluded.append({'id':row['id'], 'reason':reason})
        else:
            resolved.append(dict(row, dose_um=sample['dose_um'], dose_source='transfer_history',
                                 calibration_revision=None, transfer_binding=dict(sample, history_revision=history['revision'], campaign=history['campaign'])))
    return sorted(resolved,key=lambda r:(r['plate'],r['well'])), excluded, evidence


def measurement_key(data):
    """Compare numerical projections only, never dataset or result identity."""
    from .codec import digest
    from .registry import normalize_input
    normalized = normalize_input(data)
    if normalized['kind'] != 'screening' or 'transfer_history' not in normalized:
        return digest(data)
    rows, excluded, evidence = resolve(normalized)
    projected = [{k:v for k,v in row.items() if k not in {'transfer_binding','calibration_revision'}} for row in rows]
    return digest({'kind':'screening', 'rows':projected, 'excluded':excluded,
                   'calibration':normalized.get('calibration')})
