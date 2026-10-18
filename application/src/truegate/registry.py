"""Resolve campaign-local names before joining measurements and transfers."""
from collections import defaultdict
from .codec import require, text, digest, dumps
from .errors import WorkbenchError


def identity(entity):
    require(entity, ["local_id", "type", "value", "target"], "entity")
    kind, value = entity["type"], text(entity["value"], "identity value")
    target = text(entity["target"], "target")
    if kind == "sequence":
        value = "".join(value.split()).upper()
        if not value or any(c not in "ACDEFGHIKLMNPQRSTVWYX*" for c in value):
            raise WorkbenchError("Sequence must use single-letter amino acid symbols")
    elif kind == "smiles":
        # Exact-string identity only: no claim of chemical graph canonicalization.
        if any(c.isspace() for c in value):
            raise WorkbenchError("SMILES identity must not contain whitespace")
    else:
        raise WorkbenchError("Identity type must be sequence or smiles")
    return kind, value, target


def scoped(campaign, identifier):
    return digest([campaign, identifier])


def normalize_input(data):
    if isinstance(data, dict) and isinstance(data.get("transfer_history"), dict) and "histories" in data["transfer_history"]:
        raise WorkbenchError("Internal history envelopes cannot be imported directly")
    if not isinstance(data, dict) or "campaigns" not in data:
        return data
    if "transfer_history" in data:
        raise WorkbenchError("Campaign transfer histories belong inside their campaign")
    if data.get("kind") != "screening" or "records" in data or "telemetry" in data:
        raise WorkbenchError("Campaign screening inputs cannot also contain top-level records or telemetry")
    campaigns = data["campaigns"]
    if not isinstance(campaigns, list) or not campaigns:
        raise WorkbenchError("campaigns must be a nonempty array")
    aliases, groups, registry, names = {}, defaultdict(list), {}, set()
    for campaign in campaigns:
        require(campaign, ["id", "entities", "records"], "campaign")
        name = text(campaign["id"], "campaign id")
        if name != campaign["id"] or name in names:
            raise WorkbenchError("Campaign identifiers must be unique and trimmed")
        names.add(name)
        if not isinstance(campaign["entities"], list) or not isinstance(campaign["records"], list):
            raise WorkbenchError("entities and records must be arrays")
        for entity in campaign["entities"]:
            key = identity(entity)
            local = text(entity["local_id"], "local id")
            if local != entity["local_id"] or (name, local) in aliases:
                raise WorkbenchError("Local entity identifiers must be unique and trimmed")
            rid = text(entity["registry_id"], "registry id") if "registry_id" in entity else None
            if rid and rid in registry and registry[rid] != key:
                raise WorkbenchError("Registry identifier refers to conflicting identities")
            if rid:
                registry[rid] = key
            aliases[(name, local)] = key
            groups[key].append({"campaign": name, "local_id": local, "registry_id": rid})
    canonical, catalog = {}, []
    for key, members in sorted(groups.items()):
        ids = {a["registry_id"] for a in members if a["registry_id"]}
        if len(ids) > 1:
            raise WorkbenchError("Identical identity has conflicting registry identifiers")
        cid = "registry:" + digest(next(iter(ids))) if ids else "entity:" + digest(list(key))
        canonical[key] = cid
        catalog.append({"canonical_id": cid, "type": key[0], "value": key[1], "target": key[2],
                        "aliases": sorted(members, key=lambda a: (a["campaign"], a["local_id"]))})
    records, telemetry, provenance, transfer_models = [], [], [], []
    from .schema import validate
    from .calibration import reconcile
    for campaign in sorted(campaigns, key=lambda c: c["id"]):
        name = campaign["id"]
        local_data = {"kind": "screening", "records": campaign["records"]}
        if "transfer_history" in campaign:
            local_data["transfer_history"] = campaign["transfer_history"]
        events = campaign.get("telemetry", [])
        local_data["telemetry"] = events
        validate(local_data)
        reconcile(campaign["records"], events)
        for row in campaign["records"]:
            merged = dict(row, id=scoped(name, row["id"]), plate=scoped(name, row["plate"]))
            if row["role"] == "sample":
                key = aliases.get((name, row["compound"]))
                if key is None:
                    raise WorkbenchError("Sample references an unregistered local entity")
                merged["compound"] = canonical[key]
            records.append(merged)
            provenance.append({"id": merged["id"], "campaign": name, "record": row["id"],
                               "plate": row["plate"], "local_id": row.get("compound")})
        telemetry.extend(dict(e, plate=scoped(name, e["plate"])) for e in events)
        if "transfer_history" in campaign:
            model = campaign["transfer_history"]
            vessels = []
            for vessel in model["vessels"]:
                concentrations = {}
                for compound,value in vessel["concentrations"].items():
                    if (name,compound) not in aliases:
                        raise WorkbenchError("Transfer solute is not registered in its campaign")
                    cid = canonical[aliases[(name,compound)]]
                    concentrations[cid] = concentrations.get(cid,0) + value
                vessels.append(dict(vessel, concentrations=concentrations))
            transfer_models.append({"campaign":name, "model":dict(model, vessels=vessels,
                bindings=[dict(b, record_id=scoped(name,b["record_id"])) for b in model["bindings"]])})
    result = {"kind": "screening", "records": sorted(records, key=lambda r: r["id"]),
            "telemetry": telemetry, "identity_catalog": sorted(catalog, key=lambda e: e["canonical_id"]),
            "source_records": sorted(provenance, key=lambda r: r["id"])}

    if transfer_models:
        result['transfer_history'] = {'histories':transfer_models}
    if 'calibration' in data:
        model = data['calibration']
        require(model, ['bindings'], 'calibration')
        if not isinstance(model['bindings'], list):
            raise WorkbenchError('Calibration bindings must be an array')
        valid = {(r['campaign'],r['record']) for r in provenance}
        bindings = []
        for binding in model['bindings']:
            require(binding, ['campaign','record_id','node'], 'campaign binding')
            pair = (text(binding['campaign'],'binding campaign'), text(binding['record_id'],'binding record'))
            if pair != (binding['campaign'],binding['record_id']):
                raise WorkbenchError('Calibration binding identifiers must be trimmed')
            if pair not in valid:
                raise WorkbenchError('Calibration binding references an unknown campaign record')
            bindings.append({'record_id':scoped(*pair), 'node':binding['node']})
        result['calibration'] = dict(model, bindings=bindings)
    for campaign in campaigns:
        if 'calibration' in campaign:
            raise WorkbenchError('Use one top-level calibration model with scoped bindings')
    return result
