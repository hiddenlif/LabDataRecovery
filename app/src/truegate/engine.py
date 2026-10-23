"""Analysis dispatch is shared by the CLI, campaign store and exported reports."""
from .schema import validate
from .policy import resolve
from .codec import digest
from . import ENGINE_VERSION


def analyze(data, policy=None):
    input_sha = digest(data)
    from .registry import normalize_input
    data = normalize_input(data)
    validate(data)
    settings = resolve(data["kind"], policy)
    from . import screening, bridge, stability, counts
    module = {"screening": screening, "bridge": bridge, "stability": stability, "rare_events": counts}[data["kind"]]
    result = module.analyze(data, settings)
    return {"kind": data["kind"], "engine_version": ENGINE_VERSION, "input_sha256": input_sha,
            "policy_sha256": digest(settings), "policy": settings, "result": result}

