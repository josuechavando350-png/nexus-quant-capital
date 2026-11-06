"""M57: server-held one-use capabilities, hashed at rest and asset-bound."""

import hashlib
import secrets

from .codec import Rejected, identifier, integer


def token_hash(token):
    if not isinstance(token, str) or len(token) != 64:
        raise Rejected("invalid_token")
    try:
        bytes.fromhex(token)
    except ValueError as exc:
        raise Rejected("invalid_token") from exc
    # Only the exact encoding issued is accepted.
    if token.lower() != token or any(c not in "0123456789abcdef" for c in token):
        raise Rejected("invalid_token")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue(db, subject, asset, now, ttl):
    identifier(subject)
    identifier(asset)
    integer(now, 0, 2**63 - 3601)
    integer(ttl, 1, 3600)
    token = secrets.token_hex(32)
    db.execute("INSERT INTO tokens(digest,subject,asset,issued,expires) VALUES(?,?,?,?,?)",
               (token_hash(token), subject, asset, now, now + ttl))
    return token


def consume(db, token, asset, now):
    digest = token_hash(token)
    row = db.execute("SELECT subject,asset,issued,expires,consumed FROM tokens WHERE digest=?", (digest,)).fetchone()
    if row is None or row[1] != asset or row[4] or not row[2] <= now < row[3]:
        raise Rejected("invalid_token")
    db.execute("UPDATE tokens SET consumed=1 WHERE digest=?", (digest,))
    return row[0]


def revoke_asset(db, asset):
    db.execute("UPDATE tokens SET consumed=1 WHERE asset=?", (asset,))
