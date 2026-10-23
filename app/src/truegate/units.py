"""Unit conversion at the import boundary; internal concentrations are micromolar."""
from .codec import number
from .errors import WorkbenchError

CONCENTRATION = {"M": 1e6, "mM": 1e3, "uM": 1.0, "µM": 1.0, "μM": 1.0, "nM": 1e-3}
TIME = {"h": 1.0, "hours": 1.0, "min": 1 / 60, "days": 24.0}


def convert(value, unit, family):
    table = CONCENTRATION if family == "concentration" else TIME
    if unit not in table:
        raise WorkbenchError(f"Unsupported {family} unit: {unit}")
    return number(value, family, 0) * table[unit]

