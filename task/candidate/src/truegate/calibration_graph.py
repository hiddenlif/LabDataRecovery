"""Resolve dilution ancestry and shared log-scale error sources."""
import math
from collections import deque
from .codec import require, text, number
from .errors import WorkbenchError
from .units import convert


def identifier(value, label):
    result = text(value, label)
    if result != value:
        raise WorkbenchError(label + ' must be trimmed')
    return result


def resolve_model(data):
    model = data['calibration']
    if data['kind'] != 'screening':
        raise WorkbenchError('Calibration is supported only for screening')
    require(model, ['revision','sources','nodes','bindings'], 'calibration')
    identifier(model['revision'], 'calibration revision')
    for field, limit in [('sources',128),('nodes',4096),('bindings',100000)]:
        if not isinstance(model[field], list) or len(model[field]) > limit:
            raise WorkbenchError(f'{field} must be an array with at most {limit} entries')
    sources, nodes, bindings = {}, {}, {}
    for source in model['sources']:
        require(source, ['id','log_sd'], 'uncertainty source')
        key = identifier(source['id'], 'source id')
        if key in sources:
            raise WorkbenchError('Duplicate uncertainty source')
        sources[key] = number(source['log_sd'], 'log_sd', 0)
    children, indegree = {}, {}
    for node in model['nodes']:
        require(node, ['id','loadings'], 'calibration node')
        key = identifier(node['id'], 'node id')
        if key in nodes:
            raise WorkbenchError('Duplicate calibration node')
        if not isinstance(node['loadings'], dict) or set(node['loadings']) - sources.keys():
            raise WorkbenchError('loadings must reference declared sources')
        for value in node['loadings'].values(): number(value, 'source loading')
        if 'parent' in node:
            identifier(node['parent'], 'parent'); require(node, ['ratio'], 'dilution')
            ratio = number(node['ratio'], 'ratio')
            if ratio <= 0 or 'concentration' in node or 'unit' in node:
                raise WorkbenchError('A dilution needs a positive ratio and no root concentration')
            children.setdefault(node['parent'], []).append(key)
            indegree[key] = 1
        else:
            require(node, ['concentration','unit'], 'stock')
            if convert(node['concentration'], node['unit'], 'concentration') <= 0 or 'ratio' in node:
                raise WorkbenchError('A stock needs positive concentration and no dilution ratio')
            indegree[key] = 0
        nodes[key] = node
    if set(children) - nodes.keys():
        raise WorkbenchError('Unknown calibration parent')
    ready = deque(sorted(k for k,v in indegree.items() if not v))
    resolved = {}
    while ready:
        key = ready.popleft(); node = nodes[key]
        if 'parent' in node:
            parent = resolved[node['parent']]
            dose, loadings = parent['dose_um'] * node['ratio'], dict(parent['loadings'])
        else:
            dose, loadings = convert(node['concentration'], node['unit'], 'concentration'), {}
        for source, value in node['loadings'].items():
            loadings[source] = loadings.get(source, 0) + value
        if not math.isfinite(dose) or dose <= 0 or any(not math.isfinite(v) for v in loadings.values()):
            raise WorkbenchError('Nonfinite or nonpositive resolved calibration')
        resolved[key] = {'dose_um':dose, 'loadings':loadings}
        for child in sorted(children.get(key, [])):
            indegree[child] -= 1
            if not indegree[child]: ready.append(child)
    if len(resolved) != len(nodes):
        raise WorkbenchError('Calibration graph contains a cycle')
    samples = {r['id'] for r in data['records'] if r['role'] == 'sample'}
    for binding in model['bindings']:
        require(binding, ['record_id','node'], 'binding')
        key = identifier(binding['record_id'], 'binding record')
        node = identifier(binding['node'], 'binding node')
        if key not in samples or key in bindings or node not in resolved:
            raise WorkbenchError('Binding must identify a unique sample and an existing node')
        bindings[key] = node
    return sources, resolved, bindings


def apply(data, records):
    sources, nodes, bindings = resolve_model(data)
    output, unresolved = [], set()
    for row in records:
        copy = dict(row)
        if row['role'] == 'sample':
            if row['id'] not in bindings:
                unresolved.add((row['compound'], row['assay']))
            else:
                node = nodes[bindings[row['id']]]
                if row['dose_source'] in {'calibrated','transfer_history'} and not math.isclose(row['dose_um'], node['dose_um'], rel_tol=1e-9, abs_tol=0):
                    raise WorkbenchError('Calibration central dose disagrees with dispensing evidence')
                copy.update(dose_um=node['dose_um'], calibration_node=bindings[row['id']],
                            calibration_loadings=node['loadings'])
        output.append(copy)
    return output, unresolved, sources
