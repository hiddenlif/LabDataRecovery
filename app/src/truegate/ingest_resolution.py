"""Resolve complete deliveries from original bytes, independently of arrival order."""
import hashlib
from .codec import digest, loads
from .instrument_files import parse
from .schema import validate
from .calibration import reconcile
from .errors import WorkbenchError, Conflict


def assemble(manifest, sources):
    by_id = {s['source_id']:s for s in sources}
    pending = [s['id'] for s in manifest['sources'] if by_id[s['id']]['state'] != 'accepted']
    if pending:
        raise Conflict('Sources not accepted: ' + ', '.join(sorted(pending)))
    wells, transfers, original, history = {}, {}, [], None
    for spec in sorted(manifest['sources'], key=lambda s:s['id']):
        saved = by_id[spec['id']]
        raw = bytes(saved['raw'])
        if hashlib.sha256(raw).hexdigest() != spec['sha256']:
            raise Conflict('Stored source fingerprint mismatch: ' + spec['id'])
        parsed, errors = parse(raw, spec['kind'])
        if errors:
            raise Conflict('Stored source no longer parses: ' + spec['id'])
        original.append({'id':spec['id'], 'kind':spec['kind'], 'sha256':spec['sha256'],
                         'text':raw.decode('utf-8')})
        if spec['kind'] == 'transfer_history':
            history = parsed[0]['record']
            continue
        for item in parsed:
            row = item['record']
            key = (row['plate'], row['well'], row['revision'])
            table = wells if spec['kind'] == 'readings' else transfers
            if key in table and digest(table[key]['record']) != digest(row):
                raise Conflict(f'Conflicting {spec["kind"]} for {key}')
            entry = table.setdefault(key, {'record':row, 'sources':[]})
            entry['sources'].append({'source':spec['id'], 'line':item['line']})
    chosen = {}
    for (plate, well, revision), item in sorted(wells.items()):
        if (plate, well) not in chosen or revision > chosen[(plate,well)]['record']['revision']:
            chosen[(plate,well)] = item
    records, lineage = [], []
    for key, item in sorted(chosen.items()):
        row = dict(item['record']); revision = row.pop('revision')
        records.append(row)
        lineage.append({'record':row['id'], 'plate':row['plate'], 'well':row['well'],
                        'reading_revision':revision, 'sources':item['sources']})
    telemetry = [item['record'] for _, item in sorted(transfers.items())]
    data = {'kind':'screening', 'records':records, 'telemetry':telemetry,
            'ingestion':{'manifest':manifest, 'sources':original, 'record_lineage':lineage}}
    if history is not None:
        data['transfer_history'] = history
    validate(data)
    from .dispensing import resolve
    resolve(data)
    for plate in {r['plate'] for r in records}:
        if len({r['assay'] for r in records if r['plate'] == plate}) != 1:
            raise WorkbenchError('Plate has inconsistent assay labels: ' + plate)
    return data
