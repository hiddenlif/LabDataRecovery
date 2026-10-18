"""Strict, stable interchange. Hashes bind content, not file formatting."""
import hashlib
import json
import math
from pathlib import Path
from .errors import WorkbenchError


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WorkbenchError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def loads(text):
    def invalid(value):
        raise WorkbenchError(f"Non-finite JSON constant: {value}")
    try:
        return json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise WorkbenchError(f"Invalid JSON: {exc}") from exc


def load(path):
    p = Path(path)
    if p.stat().st_size > 20 * 1024 * 1024:
        raise WorkbenchError("Input exceeds 20 MiB")
    return loads(p.read_text(encoding="utf-8-sig"))


def dumps(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkbenchError(f"{label} must be numeric")
    if not math.isfinite(value):
        raise WorkbenchError(f"{label} must be finite")
    if minimum is not None and value < minimum:
        raise WorkbenchError(f"{label} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise WorkbenchError(f"{label} must be <= {maximum}")
    return float(value)


def integer(value, label, minimum=0):
    number(value, label, minimum)
    if int(value) != value:
        raise WorkbenchError(f"{label} must be an integer")
    return int(value)


def text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise WorkbenchError(f"{label} must be nonempty text of at most 200 characters")
    return value.strip()


def require(obj, keys, label):
    if not isinstance(obj, dict):
        raise WorkbenchError(f"{label} must be an object")
    missing = set(keys) - obj.keys()
    if missing:
        raise WorkbenchError(f"{label} missing {', '.join(sorted(missing))}")

