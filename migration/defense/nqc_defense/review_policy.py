"""Pinned local reviewer capabilities. Credential ownership is not a verified human identity."""
import hmac
from pathlib import Path
import secrets
import stat

from .codec import Rejected, canonical, decode, fields, identifier
from .files import create_local, read_local, sha256
from .receipts import hex_digest

PERMISSIONS = {"read", "start", "note", "assess", "close", "reopen"}


def validate_grants(grants, credentials=False):
    if type(grants) is not list or not 1 <= len(grants) <= 32:
        raise Rejected("review_grants_count")
    names = set()
    for grant in grants:
        keys = ("actor", "tenant", "assets", "permissions") + (("token_sha256",) if credentials else ())
        fields(grant, keys)
        identifier(grant["actor"]); identifier(grant["tenant"])
        if grant["actor"] in names:
            raise Rejected("review_actor_duplicate")
        names.add(grant["actor"])
        if type(grant["assets"]) is not list or not 1 <= len(grant["assets"]) <= 64:
            raise Rejected("review_assets")
        for asset in grant["assets"]:
            identifier(asset)
        if len(set(grant["assets"])) != len(grant["assets"]):
            raise Rejected("review_assets")
        permissions = grant["permissions"]
        if type(permissions) is not list or not permissions or any(not isinstance(p, str) or p not in PERMISSIONS for p in permissions):
            raise Rejected("review_permissions")
        if len(set(permissions)) != len(permissions):
            raise Rejected("review_permissions")
        if credentials:
            hex_digest(grant["token_sha256"])
    encoded_grants = grants if credentials else [{**g, "token_sha256": "0" * 64} for g in grants]
    if len(canonical(encoded_grants)) > 60000:
        raise Rejected("review_policy_size")


class ReviewPolicy:
    def __init__(self, root, digest):
        self.root = Path(root).absolute()
        hex_digest(digest)
        self.digest = digest
        self.value, self.key = self.check()

    @classmethod
    def create(cls, root, grants):
        validate_grants(grants)
        root = Path(root).absolute()
        root.mkdir(mode=0o700, exist_ok=False)
        (root / "credentials").mkdir(mode=0o700)
        key = secrets.token_bytes(32)
        create_local(root, "audit.key", key)
        actors = []
        for grant in grants:
            token = secrets.token_bytes(32)
            create_local(root, "credentials/" + grant["actor"] + ".key", token)
            actors.append({**grant, "token_sha256": sha256(token)})
        value = {"schema": "nqc-local-review-policy-v1", "audit_key_sha256": sha256(key), "grants": actors}
        data = canonical(value)
        create_local(root, "policy.json", data)
        return cls(root, sha256(data))

    def check(self):
        for name in ("", "credentials"):
            info = (self.root / name).lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
                raise Rejected("review_policy_permissions")
        data = read_local(self.root, "policy.json", 65536)
        if sha256(data) != self.digest:
            raise Rejected("review_policy_digest")
        value = decode(data)
        fields(value, ("schema", "audit_key_sha256", "grants"))
        if value["schema"] != "nqc-local-review-policy-v1" or canonical(value) != data:
            raise Rejected("review_policy_schema")
        validate_grants(value["grants"], credentials=True)
        key = read_credential(self.root / "audit.key")
        if sha256(key) != value["audit_key_sha256"]:
            raise Rejected("review_audit_key_digest")
        return value, key

    def permits(self, actor, tenant, asset, action):
        return any(g["actor"] == actor and g["tenant"] == tenant and asset in g["assets"] and action in g["permissions"]
                   for g in self.value["grants"])

    def authorize(self, actor, credential, tenant, asset, action):
        identifier(actor); identifier(tenant); identifier(asset)
        value, key = self.check()
        if value != self.value or not hmac.compare_digest(key, self.key):
            raise Rejected("review_policy_changed")
        candidate = next((g for g in value["grants"] if g["actor"] == actor), None)
        if (not isinstance(credential, bytes) or len(credential) != 32 or candidate is None or
                not hmac.compare_digest(sha256(credential), candidate["token_sha256"]) or
                not self.permits(actor, tenant, asset, action)):
            raise Rejected("review_unauthorized")


def read_credential(path):
    path = Path(path).absolute()
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
        raise Rejected("review_credential_permissions")
    key = read_local(path.parent, path.name, 32)
    if len(key) != 32:
        raise Rejected("review_credential_size")
    return key
