"""M67: hash-addressed policy storage with an out-of-band expected digest."""

import hashlib
import re

from .codec import Rejected, canonical, decode, fields, identifier, integer
from .files import create_local, private_directory, read_local, relative_parts


def validate(policy):
    if type(policy) is not dict:
        raise Rejected("policy_schema")
    version = policy.get("schema")
    names = ("schema", "assets", "rate_limit", "rate_window_seconds", "token_ttl_seconds")
    if version == "nqc-defense-policy-v2":
        names += ("evidence_max_age_seconds", "max_quarantined_assets")
    elif version != "nqc-defense-policy-v1":
        raise Rejected("policy_schema")
    fields(policy, names)
    integer(policy["rate_limit"], 1, 10000)
    integer(policy["rate_window_seconds"], 1, 3600)
    integer(policy["token_ttl_seconds"], 1, 3600)
    if type(policy["assets"]) is not list or not 1 <= len(policy["assets"]) <= 100:
        raise Rejected("assets_count")
    if version == "nqc-defense-policy-v2":
        integer(policy["evidence_max_age_seconds"], 0, 300)
        integer(policy["max_quarantined_assets"], 0, len(policy["assets"]))
    seen, used_paths = set(), set()
    for asset in policy["assets"]:
        fields(asset, ("id", "path", "sha256", "canaries"))
        identifier(asset["id"])
        if asset["id"] in seen:
            raise Rejected("duplicate_asset")
        seen.add(asset["id"])
        if type(asset["canaries"]) is not list or not 1 <= len(asset["canaries"]) <= 16:
            raise Rejected("canary_count")
        for entry in [asset, *asset["canaries"]]:
            if entry is not asset:
                fields(entry, ("path", "sha256"))
            relative_parts(entry["path"])
            if entry["path"] in used_paths:
                raise Rejected("duplicate_path")
            used_paths.add(entry["path"])
            if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
                raise Rejected("digest")
    return policy


def controls(policy):
    """Explicit v1 compatibility; does not mutate bytes covered by the policy digest."""
    validate(policy)
    return {"evidence_max_age_seconds": policy.get("evidence_max_age_seconds", 5),
            "max_quarantined_assets": policy.get("max_quarantined_assets", len(policy["assets"]))}


class ConfigStore:
    def __init__(self, root):
        self.root = private_directory(root)

    def put(self, raw):
        data = canonical(validate(decode(raw)))
        digest = hashlib.sha3_256(data).hexdigest()
        try:
            create_local(self.root, digest + ".json", data)
        except FileExistsError:
            if read_local(self.root, digest + ".json", 65536) != data:
                raise Rejected("config_store_corruption")
        return digest

    def get(self, expected_digest):
        if not isinstance(expected_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_digest):
            raise Rejected("config_digest")
        data = read_local(self.root, expected_digest + ".json", 65536)
        if hashlib.sha3_256(data).hexdigest() != expected_digest:
            raise Rejected("config_integrity")
        return validate(decode(data))
