"""Documented interchange CSV adapters, retaining row diagnostics and physical identity."""
import csv
import io
from decimal import Decimal, InvalidOperation
from .codec import integer, number, text
from .schema import validate
from .units import convert
from .errors import WorkbenchError

HEADERS = {
    'readings': ['id','plate','well','revision','assay','role','signal','compound','dose','dose_unit'],
    'telemetry': ['plate','well','revision','status','actual_dose','dose_unit'],
}


def numeric(value, label, integral=False):
    if integral:
        try:
            exact = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise WorkbenchError(f'{label} must be an integer') from exc
        if not exact.is_finite() or exact != exact.to_integral_value() or not 1 <= exact <= 9223372036854775807:
            raise WorkbenchError(f'{label} must be an integer from 1 to 9223372036854775807')
        return int(exact)
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise WorkbenchError(f'{label} must be numeric') from exc
    return number(result, label)


def parse(raw, kind, codec=None):
    """Return a complete parsed source or row diagnostics; never partial accepted data."""
    if kind == 'transfer_history':
        from .codec import loads
        from copy import deepcopy
        from .transfer_history import replay
        try:
            model = loads(raw.decode('utf-8-sig'))
            if codec not in (None, 'transfer-history/2', 'transfer-history/1'):
                raise WorkbenchError('Unsupported transfer codec: ' + str(codec))
            if codec == 'transfer-history/1':
                model = deepcopy(model)
                for binding in model['bindings']:
                    binding['sequence'] -= 1
            replay(model)
            return [{'line':0, 'record':model}], []
        except (WorkbenchError, ValueError, UnicodeError, OverflowError) as exc:
            return [], [{'line':0, 'error':str(exc)}]
    if kind not in HEADERS:
        raise WorkbenchError('Source kind must be readings or telemetry')
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeError:
        return [], [{'line': 0, 'error': 'Source is not UTF-8'}]
    reader = csv.DictReader(io.StringIO(content, newline=''), strict=True)
    rows, errors = [], []
    try:
        fields = reader.fieldnames
        if fields is None or len(fields) != len(set(fields)) or set(fields) != set(HEADERS[kind]):
            return [], [{'line': 1, 'error': f'Expected columns: {",".join(HEADERS[kind])}'}]
        for values in reader:
            line = reader.line_num
            try:
                if None in values or any(v is None for v in values.values()):
                    raise WorkbenchError('CSV row has the wrong field count')
                row = {key: value.strip() for key, value in values.items()}
                for key in ['plate','well']:
                    row[key] = text(row[key], key)
                row['revision'] = numeric(row['revision'], 'revision', True)
                if kind == 'readings':
                    row['signal'] = numeric(row['signal'], 'signal')
                    if row['role'] == 'sample':
                        row['dose'] = numeric(row['dose'], 'dose')
                        convert(row['dose'], row['dose_unit'], 'concentration')
                    else:
                        if any(row[k] for k in ['compound','dose','dose_unit']):
                            raise WorkbenchError('Control compound/dose/unit fields must be empty')
                        for key in ['compound','dose','dose_unit']:
                            row.pop(key)
                    validate({'kind':'screening', 'records':[row]})
                else:
                    if row['status'] not in {'ok','failed','cancelled'}:
                        raise WorkbenchError('Unknown transfer status')
                    if row['status'] == 'ok':
                        row['actual_dose'] = numeric(row['actual_dose'], 'actual_dose')
                        convert(row['actual_dose'], row['dose_unit'], 'concentration')
                    else:
                        if row['actual_dose'] or row['dose_unit']:
                            raise WorkbenchError('Unsuccessful transfer dose/unit fields must be empty')
                        row.pop('actual_dose'); row.pop('dose_unit')
                rows.append({'line':line, 'record':row})
            except (WorkbenchError, ValueError, OverflowError) as exc:
                errors.append({'line':line, 'error':str(exc)})
    except csv.Error as exc:
        errors.append({'line':reader.line_num, 'error':f'Invalid CSV: {exc}'})
    if not rows and not errors:
        errors.append({'line':1, 'error':'Source contains no data rows'})
    return ([], errors) if errors else (rows, [])
