"""Reconstruct well contents by replaying corrected physical transfers."""
import math
from decimal import Decimal
from .codec import require, text, number, digest
from .errors import WorkbenchError
from .units import convert

VOLUME = {'nL': .001, 'uL': 1., 'µL': 1., 'μL': 1., 'mL': 1000.}


def identifier(value, label):
    value_text = text(value, label)
    if value_text != value:
        raise WorkbenchError(label + ' must be trimmed')
    return value_text


def ordinal(value, label, minimum=1):
    # Sequence and revision identities must not pass through a float conversion.
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 9223372036854775807:
        raise WorkbenchError(label + ' must be a bounded JSON integer')
    return value


def volume(value, unit):
    if not isinstance(unit, str) or unit not in VOLUME:
        raise WorkbenchError('Unsupported volume unit')
    number(value, 'volume', 0)
    converted = float(Decimal(str(value)) * Decimal(str(VOLUME[unit])))
    return number(converted, 'converted volume', 0)


def concentration(value, unit):
    if not isinstance(unit, str):
        raise WorkbenchError('Concentration unit must be text')
    return number(convert(value, unit, 'concentration'), 'converted concentration', 0)


def view(state):
    return {'volume_ul': state['volume'], 'amounts_pmol': dict(sorted(state['amounts'].items())) if state['known'] else None,
            'known': state['known'],
            'lineage': [{'id': key, 'revision': rev} for key, rev in sorted(state['lineage'].items())]}


def replay(model, records=None):
    require(model, ['revision', 'vessels', 'events', 'bindings'], 'transfer history')
    identifier(model['revision'], 'history revision')
    for key, limit in [('vessels',4096), ('events',100000), ('bindings',100000)]:
        if not isinstance(model[key], list) or len(model[key]) > limit:
            raise WorkbenchError(key + ' is not a bounded array')
    states, solutes = {}, set()
    for vessel in model['vessels']:
        require(vessel, ['id','volume','volume_unit','concentrations','concentration_unit'], 'vessel')
        key = identifier(vessel['id'], 'vessel id')
        if key in states or not isinstance(vessel['concentrations'], dict):
            raise WorkbenchError('Vessels must be unique with a concentrations object')
        qty = volume(vessel['volume'], vessel['volume_unit'])
        amounts = {}
        concentration(0, vessel['concentration_unit'])
        for compound, value in vessel['concentrations'].items():
            identifier(compound, 'solute'); solutes.add(compound)
            dose = concentration(value, vessel['concentration_unit'])
            if qty == 0 and dose != 0:
                raise WorkbenchError('An empty vessel cannot declare nonzero concentration')
            if dose:
                amounts[compound] = number(qty * dose, 'initial amount', 0)
        states[key] = {'known':True, 'volume':qty, 'amounts':amounts, 'lineage':{}}
    if len(solutes) > 64:
        raise WorkbenchError('History allows at most 64 solutes')
    revisions, identities, sequences = {}, {}, {}
    for event in model['events']:
        require(event, ['id','revision','sequence','source','destination','status'], 'transfer event')
        key = identifier(event['id'], 'transfer id')
        rev = ordinal(event['revision'], 'transfer revision')
        seq = ordinal(event['sequence'], 'transfer sequence')
        src, dst = identifier(event['source'], 'source'), identifier(event['destination'], 'destination')
        if src not in states or dst not in states or src == dst:
            raise WorkbenchError('Transfer endpoints must be distinct declared vessels')
        identity = (seq, src, dst)
        if key in identities and identities[key] != identity:
            raise WorkbenchError('Transfer identity changes across revisions')
        if seq in sequences and sequences[seq] != key:
            raise WorkbenchError('Distinct transfers cannot share a sequence')
        identities[key], sequences[seq] = identity, key
        status = event['status']
        if status not in ('ok','partial','failed','cancelled','unknown'):
            raise WorkbenchError('Unknown physical transfer status')
        if status == 'unknown':
            if 'volume' in event or 'volume_unit' in event:
                raise WorkbenchError('Unknown delivery must not claim a measured volume')
            qty = None
        else:
            require(event, ['volume','volume_unit'], 'measured transfer')
            qty = volume(event['volume'], event['volume_unit'])
            if (status in ('ok','partial') and qty <= 0) or (status in ('failed','cancelled') and qty != 0):
                raise WorkbenchError('Transfer status and actual delivered volume disagree')
        normalized = {'id':key, 'revision':rev, 'sequence':seq, 'source':src,
                      'destination':dst, 'status':status, 'volume_ul':qty}
        versions = revisions.setdefault(key, {})
        if rev in versions and versions[rev] != normalized:
            raise WorkbenchError('Conflicting transfer revision')
        versions[rev] = normalized
    selected = sorted((versions[max(versions)] for versions in revisions.values()), key=lambda e:e['sequence'])
    samples = {r['id']:r for r in records if r['role']=='sample'} if records is not None else None
    bindings, by_sequence = {}, {}
    for binding in model['bindings']:
        require(binding, ['record_id','vessel','sequence'], 'transfer binding')
        key = identifier(binding['record_id'], 'binding record')
        vessel = identifier(binding['vessel'], 'binding vessel')
        seq = ordinal(binding['sequence'], 'binding sequence', 0)
        if key in bindings or vessel not in states or (seq != 0 and seq not in sequences):
            raise WorkbenchError('Invalid or duplicate transfer binding')
        if samples is not None and key not in samples:
            raise WorkbenchError('Transfer binding must name an existing sample')
        bindings[key] = binding
        by_sequence.setdefault(seq, []).append(binding)
    output, steps = [], []

    def capture(seq):
        for binding in sorted(by_sequence.get(seq, []), key=lambda b:b['record_id']):
            state = states[binding['vessel']]
            row = dict(binding, **view(state))
            if samples is not None:
                compound = samples[binding['record_id']]['compound']
                dose = state['amounts'].get(compound, 0) / state['volume'] if state['known'] and state['volume'] else None
                row.update(compound=compound, dose_um=dose,
                           status='unknown' if not state['known'] else 'empty' if not state['volume'] else 'zero_dose' if not dose else 'usable')
            output.append(row)

    capture(0)
    for event in selected:
        src, dst = states[event['source']], states[event['destination']]
        qty, status = event['volume_ul'], event['status']
        affected = dict(src['lineage']); affected.update(dst['lineage']); affected[event['id']] = event['revision']
        if status == 'unknown':
            src_lineage = dict(src['lineage']); src_lineage[event['id']] = event['revision']
            src.update(known=False, volume=None, amounts={}, lineage=src_lineage)
            dst.update(known=False, volume=None, amounts={}, lineage=dict(affected))
        elif status not in ('failed','cancelled'):
            if src['known'] and src['volume'] == 0:
                raise WorkbenchError('Transfer overdraws an empty source')
            if src['known'] and qty > src['volume'] and not math.isclose(qty, src['volume'], rel_tol=1e-12, abs_tol=1e-12):
                raise WorkbenchError('Transfer overdraws its source at execution time')
            if src['known']:
                qty = min(qty, src['volume'])
                moved = {c: value * (qty/src['volume']) for c,value in src['amounts'].items()}
                src['amounts'] = {c: max(0.,value-moved[c]) for c,value in src['amounts'].items()}
                src['volume'] = max(0., src['volume']-qty)
                if dst['known']:
                    dst['volume'] = number(dst['volume']+qty, 'destination volume', 0)
                    for c,value in moved.items():
                        dst['amounts'][c] = number(dst['amounts'].get(c,0)+value, 'destination amount', 0)
                # Removing homogeneous liquid does not introduce destination ancestry into source.
                src['lineage'][event['id']] = event['revision']
                dst['lineage'] = affected
            else:
                dst.update(known=False, volume=None, amounts={}, lineage=dict(affected))
                src['lineage'][event['id']] = event['revision']
        else:
            # A zero-volume failed attempt contributes no liquid and no contents ancestry.
            pass
        steps.append(dict(event, source_state=view(src), destination_state=view(dst)))
        capture(event['sequence'])
    return {'revision':model['revision'], 'history_sha256':digest(model), 'steps':steps,
            'bindings':sorted(output, key=lambda b:b['record_id']),
            'final_vessels':[dict(id=k, **view(v)) for k,v in sorted(states.items())]}


def histories(data):
    if 'transfer_history' not in data:
        return []
    if data['kind'] != 'screening':
        raise WorkbenchError('Transfer history is supported only for screening')
    model = data['transfer_history']
    if isinstance(model, dict) and 'histories' in model:
        entries = model['histories']
    else:
        entries = [{'campaign':None, 'model':model}]
    results = []
    for entry in entries:
        results.append(dict(campaign=entry['campaign'], **replay(entry['model'], data['records'])))
    bound = [b['record_id'] for h in results for b in h['bindings']]
    if len(bound) != len(set(bound)):
        raise WorkbenchError('Sample is bound by multiple transfer histories')
    rows = {r['id']:r for r in data['records']}
    plates = {rows[key]['plate'] for key in bound}
    if any(e['plate'] in plates for e in data.get('telemetry', [])):
        raise WorkbenchError('A plate cannot mix legacy telemetry and physical transfer history')
    return results
