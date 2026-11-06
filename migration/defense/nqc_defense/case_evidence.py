"""Preserve only a case's triggering auth records, with externally pinned offline verification."""
import base64
import binascii
from pathlib import Path
import stat
import time

from .auth_log import AuthLogMonitor, MAX_FILE, MAX_LINE, parse_auth
from .codec import Rejected, canonical, decode, fields, identifier, integer
from .files import publish_local, read_local, relative_parts, sha256
from .openssh_log import parse_openssh, source_options
from .operations import SCHEMA as EVENT_SCHEMA
from .receipts import hex_digest

SCHEMA = "nqc-case-evidence-v1"
MAX_BUNDLE = 8 * 1024 * 1024
MAX_RAW = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_FILES = 8


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def _case(case, tenant, asset, case_id, case_digest, config_digest):
    fields(case, ("case_id", "tenant", "asset", "source_id", "category", "status", "rule", "config_digest",
                  "evidence_event_ids", "threshold", "window_ns", "principal", "remote_address",
                  "automatic_response", "interpretation"))
    require((case["tenant"], case["asset"], case["case_id"]) == (tenant, asset, case_id), "evidence_case_scope")
    require(sha256(canonical(case)) == case_digest, "evidence_case_digest")
    require(case["category"] == "authentication" and case["rule"] == "auth_failure_burst_v1", "evidence_case_unsupported")
    require(case["config_digest"] == config_digest, "evidence_config_binding")
    identifier(case["source_id"])
    integer(case["threshold"], 2, 100)
    integer(case["window_ns"], 1000000000, 86400 * 1000000000)
    refs = case["evidence_event_ids"]
    require(type(refs) is list and len(refs) == case["threshold"], "evidence_case_membership")
    for reference in refs:
        hex_digest(reference)
    require(len(set(refs)) == len(refs), "evidence_duplicate_reference")
    require(case["automatic_response"] is False and case["status"] == "open", "evidence_case_state")


def _config(config, case, config_digest):
    names = ("schema", "source_id", "tenant", "asset", "root", "name", "threshold", "window_ns")
    if type(config) is dict and "format" in config:
        names += ("format", "expected_host")
    fields(config, names)
    require(sha256(canonical(config)) == config_digest, "evidence_config_digest")
    require(config["schema"] == "nqc-auth-source-v1", "evidence_config_schema")
    for key in ("source_id", "tenant", "asset", "threshold", "window_ns"):
        require(config[key] == case[key], "evidence_config_scope")
    require(isinstance(config["root"], str) and 0 < len(config["root"]) <= 4096 and Path(config["root"]).is_absolute(), "evidence_source_root")
    relative_parts(config["name"])
    source_options(config.get("format", "nqc-jsonl"), config.get("expected_host"))


def _snapshot(store, tenant, asset, case_id):
    identifier(tenant); identifier(asset); hex_digest(case_id)
    with store.transaction() as db:
        row = db.execute("SELECT body,category,status FROM cases WHERE tenant=? AND asset=? AND id=?",
                         (tenant, asset, case_id)).fetchone()
        if row is None:
            raise Rejected("evidence_case_not_found")
        case = decode(row[0])
        # Validate before querying references or following any stored source paths.
        if type(case) is not dict or case.get("category") != "authentication":
            raise Rejected("evidence_case_unsupported")
        require((case.get("category"), case.get("status")) == row[1:], "evidence_case_columns")
        config_digest = case.get("config_digest")
        hex_digest(config_digest)
        case_digest = sha256(canonical(case))
        _case(case, tenant, asset, case_id, case_digest, config_digest)
        source = db.execute("SELECT config FROM streams WHERE id=?", (case["source_id"],)).fetchone()
        require(source is not None, "evidence_source_missing")
        config = decode(source[0])
        _config(config, case, config_digest)
        events = []
        for reference in case["evidence_event_ids"]:
            row = db.execute("SELECT sequence,body,digest,source,kind FROM events WHERE id=? AND tenant=? AND asset=?",
                             (reference, tenant, asset)).fetchone()
            require(row is not None, "evidence_event_missing")
            require(isinstance(row[1], bytes) and len(row[1]) <= 32768, "evidence_event_storage_type")
            require(sha256(row[1]) == row[2], "evidence_event_digest")
            event = decode(row[1])
            require(type(event) is dict and event.get("source_id") == row[3] and event.get("kind") == row[4], "evidence_event_columns")
            _event_structure(event)
            events.append({"sequence": row[0], "event": event, "event_sha256": row[2]})
        return case, config, events


def _event_structure(event):
    fields(event, ("schema", "event_id", "tenant", "asset", "source_id", "kind", "observed_ns", "occurred_ns", "evidence", "attributes"))
    evidence = event["evidence"]
    fields(evidence, ("config_digest", "generation", "device", "inode", "start", "end", "raw_sha256"))
    integer(evidence["generation"], 0, 2**63 - 1)
    integer(evidence["device"], 0, 2**64 - 1)
    integer(evidence["inode"], 0, 2**64 - 1)
    integer(evidence["start"], 0, MAX_FILE)
    integer(evidence["end"], evidence["start"] + 1, MAX_FILE)
    hex_digest(evidence["raw_sha256"])


def describe_case(store, tenant, asset, case_id):
    case, config, events = _snapshot(store, tenant, asset, case_id)
    return {"case_id": case_id, "case_digest": sha256(canonical(case)), "config_digest": sha256(canonical(config)),
            "source_id": case["source_id"], "records": len(events),
            "generations": sorted({item["event"]["evidence"]["generation"] for item in events}),
            "source_pin_must_match_operator_registration": True}


def verify_bundle(data, digest, tenant, asset, case_id, case_digest, config_digest):
    """Never opens paths carried inside the bundle. Caller supplies all expected identities."""
    for value in (digest, case_id, case_digest, config_digest):
        hex_digest(value)
    identifier(tenant); identifier(asset)
    require(isinstance(data, bytes) and len(data) <= MAX_BUNDLE, "evidence_bundle_size")
    require(sha256(data) == digest, "evidence_bundle_digest")
    value = decode(data, max_bytes=MAX_BUNDLE, max_nodes=65536)
    fields(value, ("schema", "captured_ns", "case", "case_sha256", "source_config", "config_sha256", "files", "records"))
    require(canonical(value) == data and value["schema"] == SCHEMA, "evidence_bundle_format")
    integer(value["captured_ns"], 0, 2**63 - 1)
    require(value["case_sha256"] == case_digest and value["config_sha256"] == config_digest, "evidence_external_pins")
    case, config = value["case"], value["source_config"]
    _case(case, tenant, asset, case_id, case_digest, config_digest)
    _config(config, case, config_digest)
    require(type(value["files"]) is list and 1 <= len(value["files"]) <= MAX_FILES, "evidence_file_count")
    files, source_bytes = {}, 0
    for item in value["files"]:
        fields(item, ("generation", "name", "device", "inode", "size", "mtime_ns", "ctime_ns"))
        generation = integer(item["generation"], 0, 2**63 - 1)
        require(generation not in files, "evidence_duplicate_generation")
        relative_parts(item["name"])
        integer(item["device"], 0, 2**64 - 1); integer(item["inode"], 0, 2**64 - 1)
        source_bytes += integer(item["size"], 0, MAX_FILE)
        integer(item["mtime_ns"], -(2**63), 2**63 - 1); integer(item["ctime_ns"], -(2**63), 2**63 - 1)
        files[generation] = item
    require(source_bytes <= MAX_SOURCE_BYTES, "evidence_source_budget")
    records = value["records"]
    require(type(records) is list and len(records) == case["threshold"], "evidence_record_count")
    used, native_ids, failures = set(), set(), []
    raw_size, last_sequence = 0, 0
    for index, item in enumerate(records):
        fields(item, ("sequence", "event", "event_sha256", "raw_base64"))
        sequence = integer(item["sequence"], 1, 2**63 - 1)
        require(sequence > last_sequence, "evidence_event_order")
        last_sequence = sequence
        event = item["event"]
        _event_structure(event)
        require(sha256(canonical(event)) == item["event_sha256"], "evidence_event_digest")
        require((event["schema"], event["kind"], event["tenant"], event["asset"], event["source_id"]) ==
                (EVENT_SCHEMA, "auth.observation", tenant, asset, case["source_id"]), "evidence_event_scope")
        require(event["event_id"] == case["evidence_event_ids"][index], "evidence_event_membership")
        integer(event["observed_ns"], 0, 2**63 - 1)
        evidence = event["evidence"]
        fields(evidence, ("config_digest", "generation", "device", "inode", "start", "end", "raw_sha256"))
        require(evidence["config_digest"] == config_digest, "evidence_record_binding")
        generation = integer(evidence["generation"], 0, 2**63 - 1)
        require(generation in files, "evidence_generation_missing")
        file = files[generation]; used.add(generation)
        require((evidence["device"], evidence["inode"]) == (file["device"], file["inode"]), "evidence_file_identity")
        start = integer(evidence["start"], 0, MAX_FILE)
        end = integer(evidence["end"], start + 1, file["size"])
        require(end - start <= MAX_LINE, "evidence_record_size")
        expected_id = sha256(canonical([tenant, asset, case["source_id"], evidence]))
        require(expected_id == event["event_id"], "evidence_event_identity")
        encoded = item["raw_base64"]
        require(isinstance(encoded, str) and len(encoded) <= 4 * ((MAX_LINE + 2) // 3), "evidence_encoding_size")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise Rejected("evidence_record_encoding") from exc
        require(base64.b64encode(raw).decode("ascii") == encoded, "evidence_record_encoding")
        require(len(raw) == end - start and sha256(raw) == evidence["raw_sha256"], "evidence_raw_digest")
        require(raw.endswith(b"\n") and b"\n" not in raw[:-1], "evidence_record_framing")
        raw_size += len(raw)
        require(raw_size <= MAX_RAW, "evidence_raw_budget")
        auth = parse_auth(raw) if config.get("format", "nqc-jsonl") == "nqc-jsonl" else parse_openssh(raw, config)
        attributes = {"outcome": auth["outcome"], "principal": auth["principal"], "remote_address": auth["remote_address"],
                      "rule_evaluated": True, "rule_exclusion": None}
        if "origin" in auth:
            attributes.update(origin=auth["origin"], method=auth["method"], invalid_user=auth["invalid_user"], remote_port=auth["remote_port"])
        require(event["attributes"] == attributes and event["occurred_ns"] == auth["time_ns"], "evidence_normalization")
        require(auth["outcome"] == "failure" and auth["principal"] == case["principal"] and auth["remote_address"] == case["remote_address"], "evidence_trigger_subject")
        native = auth.get("native_record_id")
        if native:
            require(native not in native_ids, "evidence_duplicate_native_record")
            native_ids.add(native)
        failures.append([auth["time_ns"], event["event_id"]])
    require(set(files) == used, "evidence_unused_file")
    require(all(a[0] <= b[0] for a, b in zip(failures, failures[1:])) and failures[-1][0] - failures[0][0] <= case["window_ns"], "evidence_trigger_window")
    require(sha256(canonical([case["rule"], config_digest, failures])) == case_id, "evidence_case_identity")
    return {"verified": True, "bundle_digest": digest, "case_id": case_id, "case_digest": case_digest,
            "config_digest": config_digest, "tenant": tenant, "asset": asset, "records": len(records),
            "raw_bytes": raw_size, "trigger_conditions_verified": True, "full_episode_history_included": False,
            "origin_authenticated": False, "independent_anchor": False}


def capture_case(store, tenant, asset, case_id, case_digest, config_digest, source_map, output):
    for digest in (case_digest, config_digest):
        hex_digest(digest)
    case, config, events = _snapshot(store, tenant, asset, case_id)
    _case(case, tenant, asset, case_id, case_digest, config_digest)
    _config(config, case, config_digest)
    require(type(source_map) is list and 1 <= len(source_map) <= MAX_FILES, "evidence_file_count")
    selected = {}
    for item in source_map:
        fields(item, ("generation", "name"))
        generation = integer(item["generation"], 0, 2**63 - 1)
        relative_parts(item["name"])
        require(generation not in selected, "evidence_duplicate_generation")
        selected[generation] = item["name"]
    required = {item["event"]["evidence"]["generation"] for item in events}
    require(set(selected) == required, "evidence_source_selection")
    files, contents, source_bytes = [], {}, 0
    for generation, name in sorted(selected.items()):
        data, info = AuthLogMonitor._snapshot(config, name)
        source_bytes += len(data)
        require(source_bytes <= MAX_SOURCE_BYTES, "evidence_source_budget")
        files.append({"generation": generation, "name": name, "device": info.st_dev, "inode": info.st_ino,
                      "size": info.st_size, "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns})
        contents[generation] = data
    records = []
    for item in events:
        evidence = item["event"]["evidence"]
        start = integer(evidence["start"], 0, MAX_FILE)
        end = integer(evidence["end"], start + 1, MAX_FILE)
        require(end - start <= MAX_LINE, "evidence_record_size")
        raw = contents[evidence["generation"]][start:end]
        require(start == 0 or contents[evidence["generation"]][start - 1:start] == b"\n", "evidence_source_boundary")
        require(sha256(raw) == evidence["raw_sha256"], "evidence_source_record_changed")
        records.append({**item, "raw_base64": base64.b64encode(raw).decode("ascii")})
    data = canonical({"schema": SCHEMA, "captured_ns": time.time_ns(), "case": case, "case_sha256": case_digest,
                      "source_config": config, "config_sha256": config_digest, "files": files, "records": records})
    digest = sha256(data)
    verify_bundle(data, digest, tenant, asset, case_id, case_digest, config_digest)
    output = Path(output).absolute()
    info = output.parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and not info.st_mode & 0o077, "evidence_output_permissions")
    publish_local(output.parent, output.name, data)
    persisted = read_local(output.parent, output.name, MAX_BUNDLE)
    verified = verify_bundle(persisted, digest, tenant, asset, case_id, case_digest, config_digest)
    return {**verified, "stored_and_reread": True, "bundle_bytes": len(data)}
