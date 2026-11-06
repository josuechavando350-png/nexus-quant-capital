"""Transactional local credential lifecycle. Same OS/key custodian remains trusted."""
import hmac
from contextlib import contextmanager
from pathlib import Path
import secrets
import stat
import time

from .audit import GENESIS, mac
from .codec import Rejected, canonical, decode, fields, identifier, integer
from .files import create_local, sha256
from .receipts import hex_digest
from .review_policy import read_credential, reason_text
from .review_clock import CredentialExpired, MAX_TIME, ReviewClock

SCHEMA = "nqc-review-credential-event-v1"
CURRENT_SCHEMA = "nqc-review-credential-event-v2"
MAX_REVISIONS = 4096
MAX_TOTAL_REVISIONS = 100000
ORIGIN = {"revision": 0, "head": GENESIS}


def checkpoint(value):
    fields(value, ("revision", "head"))
    integer(value["revision"], 0, MAX_REVISIONS)
    hex_digest(value["head"])
    if value["revision"] == 0 and value["head"] != GENESIS:
        raise Rejected("credential_checkpoint")
    return dict(value)


def create_credential(path):
    """Prepare secret before activation; an interrupted publication does not change authority."""
    path = Path(path).absolute()
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise Rejected("review_credential_directory_permissions")
    create_local(path.parent, path.name, secrets.token_bytes(32))
    token = read_credential(path)
    return {"created": True, "credential_sha256": sha256(token), "activated": False}


class CredentialSnapshot:
    def __init__(self, states, expiries, history):
        self.states, self.expiries, self.history = states, expiries, history
        self.current = {"revision": len(history), "head": history[-1]["head"] if history else GENESIS}

    def contains(self, reference):
        reference = checkpoint(reference)
        revision = reference["revision"]
        if revision > len(self.history):
            raise Rejected("credential_history_missing")
        head = self.history[revision - 1]["head"] if revision else GENESIS
        if reference["head"] != head:
            raise Rejected("credential_history_binding")
        return revision

    def historical(self, reference, actor, recorded_ns):
        identifier(actor)
        revision = self.contains(reference)
        if self.states[revision].get(actor) is None:
            raise Rejected("credential_history_binding")
        expiry = self.expiries[revision][actor]
        integer(recorded_ns, 0, MAX_TIME)
        if expiry is not None and (recorded_ns >= expiry or recorded_ns < self.history[revision - 1]["event"]["recorded_ns"]):
            raise Rejected("credential_history_expiry")

    def valid_at(self, actor, now):
        integer(now, 0, MAX_TIME)
        expiry = self.expiries[-1].get(actor)
        if expiry is not None and now >= expiry:
            raise CredentialExpired(now)


class ReviewCredentials:
    def __init__(self, store, policy):
        self.store, self.policy = store, policy
        self.clock = ReviewClock(policy)
        with store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS review_credentials (policy TEXT NOT NULL, revision INTEGER NOT NULL, "
                       "payload TEXT NOT NULL, previous TEXT NOT NULL, mac TEXT NOT NULL, PRIMARY KEY(policy,revision))")
            db.execute("CREATE TABLE IF NOT EXISTS review_clock (policy TEXT PRIMARY KEY, payload TEXT NOT NULL, mac TEXT NOT NULL)")

    @contextmanager
    def transaction(self):
        """Keep a confirmed time observation even when the guarded operation is rejected."""
        failure = None
        with self.store.transaction() as db:
            snapshot = self.load(db)
            self.clock.observe(db, snapshot)
            db.execute("SAVEPOINT review_operation")
            try:
                yield db
            except Rejected as exc:
                db.execute("ROLLBACK TO review_operation")
                if isinstance(exc, CredentialExpired):
                    self.clock.remember(db, snapshot, exc.observed_ns)
                failure = exc
            finally:
                db.execute("RELEASE review_operation")
        if failure is not None:
            raise failure

    def check_policy(self):
        value, key = self.policy.check()
        if value != self.policy.value or not hmac.compare_digest(key, self.policy.key):
            raise Rejected("review_policy_changed")

    def administrator(self, key):
        self.check_policy()
        if not isinstance(key, bytes) or not hmac.compare_digest(key, self.policy.key):
            raise Rejected("credential_administrator_required")

    @staticmethod
    def transition(state, expiry_state, used, event):
        actor, action, token = event["actor"], event["action"], event["token_sha256"]
        identifier(actor)
        reason_text(event["reason"])
        if actor not in state:
            raise Rejected("credential_unknown_actor")
        expiry = event.get("expires_at_ns")
        if expiry is not None:
            integer(expiry, 1, MAX_TIME)
        deadlines = dict(expiry_state)
        if action == "revoke":
            if state[actor] is None or token is not None or expiry is not None:
                raise Rejected("credential_revoke_state")
        elif action == "set_expiry":
            if state[actor] is None or token is not None or expiry is None:
                raise Rejected("credential_expiry_state")
            if deadlines[actor] is not None and expiry >= deadlines[actor]:
                raise Rejected("credential_expiry_must_shorten")
            deadlines[actor] = expiry
        elif action in ("rotate", "renew"):
            hex_digest(token)
            if (action == "rotate") != (state[actor] is not None):
                raise Rejected("credential_rotation_state")
            if token in used:
                raise Rejected("credential_reuse")
            if expiry is not None:
                deadlines[actor] = expiry
            if deadlines[actor] is not None and deadlines[actor] <= event["recorded_ns"]:
                raise Rejected("credential_expiry_not_future")
        else:
            raise Rejected("credential_action")
        result = dict(state)
        if action != "set_expiry":
            result[actor] = token
        if token is not None:
            used.add(token)
        return result, deadlines

    def load(self, db):
        self.check_policy()
        rows = db.execute("SELECT revision,payload,previous,mac FROM review_credentials WHERE policy=? ORDER BY revision LIMIT ?",
                          (self.policy.digest, MAX_REVISIONS + 1)).fetchall()
        return verify_credential_rows(self.policy, rows)

    def check_time(self, db, snapshot, actor, now=None):
        if now is None:
            now = self.clock.observe(db, snapshot)
        else:
            self.clock.remember(db, snapshot, now)
        snapshot.valid_at(actor, now)
        return now

    def authorize(self, db, actor, token, tenant, asset, action, expected=None):
        identifier(actor); identifier(tenant); identifier(asset)
        snapshot = self.load(db)
        digest = snapshot.states[-1].get(actor)
        if (digest is None or not isinstance(token, bytes) or len(token) != 32 or
                not hmac.compare_digest(sha256(token), digest) or not self.policy.permits(actor, tenant, asset, action)):
            raise Rejected("review_unauthorized")
        # Legacy callers remain compatible only while no credential changes exist.
        if expected is None and snapshot.current != ORIGIN:
            raise Rejected("credential_checkpoint_required")
        expected = ORIGIN if expected is None else checkpoint(expected)
        if snapshot.current != expected:
            raise Rejected("credential_checkpoint_mismatch")
        self.check_time(db, snapshot, actor)
        return snapshot

    def status(self, admin_key, *, expected=None, after=0, limit=100):
        self.administrator(admin_key)
        integer(after, 0, MAX_REVISIONS); integer(limit, 1, 200)
        if expected is not None:
            checkpoint(expected)
        with self.transaction() as db:
            self.administrator(admin_key)
            snapshot = self.load(db)
            if expected is not None and snapshot.current != expected:
                raise Rejected("credential_checkpoint_mismatch")
            now = self.clock.observe(db, snapshot)
            clock_state = self.clock.read(db, snapshot)
        actors = {a: {"active": token is not None and (snapshot.expiries[-1][a] is None or now < snapshot.expiries[-1][a]),
                      "revoked": token is None, "expires_at_ns": snapshot.expiries[-1][a],
                      "expired": token is not None and snapshot.expiries[-1][a] is not None and now >= snapshot.expiries[-1][a]}
                  for a, token in snapshot.states[-1].items()}
        return {"checkpoint": snapshot.current, "actors": actors, "clock": clock_state,
                "history": snapshot.history[after:after + limit], "independent_anchor": False, "scope": "this_operations_store"}

    def change(self, admin_key, actor, action, reason, request_id, expected, *, credential=None, expires_at_ns=None):
        self.administrator(admin_key)
        identifier(actor); identifier(request_id); reason_text(reason); checkpoint(expected)
        if expires_at_ns is not None:
            integer(expires_at_ns, 1, MAX_TIME)
        if action not in ("rotate", "revoke", "renew", "set_expiry"):
            raise Rejected("credential_action")
        if action in ("revoke", "set_expiry"):
            if credential is not None:
                raise Rejected("credential_unexpected_token")
            digest = None
        else:
            if not isinstance(credential, bytes) or len(credential) != 32:
                raise Rejected("review_credential_size")
            digest = sha256(credential)
        command = {"schema": CURRENT_SCHEMA, "policy_digest": self.policy.digest, "actor": actor, "action": action,
                   "token_sha256": digest, "request_id": request_id, "reason": reason, "expires_at_ns": expires_at_ns}
        with self.transaction() as db:
            self.administrator(admin_key)
            snapshot = self.load(db)
            for entry in snapshot.history:
                if entry["event"]["request_id"] == request_id:
                    old = dict(entry["event"]); old.pop("recorded_ns"); old.pop("schema")
                    old.setdefault("expires_at_ns", None)
                    requested = dict(command); requested.pop("schema")
                    before = {"revision": entry["revision"] - 1, "head": entry["previous"]}
                    if old != requested or before != expected:
                        raise Rejected("credential_request_conflict")
                    return {"applied": False, "idempotent_retry": True, "checkpoint": snapshot.current,
                            "operation_checkpoint": {"revision": entry["revision"], "head": entry["head"]}}
            if snapshot.current != expected:
                raise Rejected("credential_checkpoint_mismatch")
            if len(snapshot.history) >= MAX_REVISIONS or db.execute("SELECT count(*) FROM review_credentials").fetchone()[0] >= MAX_TOTAL_REVISIONS:
                raise Rejected("credential_capacity")
            now = integer(time.time_ns(), 0, 2**63 - 1)
            if snapshot.history and now < snapshot.history[-1]["event"]["recorded_ns"]:
                raise Rejected("credential_clock_regressed")
            event = {**command, "recorded_ns": now}
            used = {v for state in snapshot.states for v in state.values() if v is not None}
            used.add(sha256(self.policy.key))
            self.transition(snapshot.states[-1], snapshot.expiries[-1], used, event)
            revision, previous = snapshot.current["revision"] + 1, snapshot.current["head"]
            payload = canonical(event).decode()
            head = mac(self.policy.key, revision, previous, payload)
            db.execute("INSERT INTO review_credentials VALUES(?,?,?,?,?)", (self.policy.digest, revision, payload, previous, head))
            updated = self.load(db)
            self.clock.remember(db, updated, now, initialize=not any(v is not None for v in snapshot.expiries[-1].values()))
        return {"applied": True, "idempotent_retry": False, "checkpoint": {"revision": revision, "head": head},
                "scope": "this_operations_store"}


def verify_credential_rows(policy, rows):
    """Replay supplied rows; shared by live storage and the offline dossier verifier."""
    states = [{g["actor"]: g["token_sha256"] for g in policy.value["grants"]}]
    expiries = [{actor: None for actor in states[0]}]
    used = {*states[0].values(), sha256(policy.key)}
    if type(rows) not in (list, tuple):
        raise Rejected("credential_history_rows")
    if len(rows) > MAX_REVISIONS:
        raise Rejected("credential_capacity")
    history, seen, previous, last_time, versioned = [], set(), GENESIS, -1, False
    for number, row in enumerate(rows, 1):
        if type(row) not in (list, tuple) or len(row) != 4:
            raise Rejected("credential_history_row")
        revision, payload, parent, digest = row
        integer(revision, 1, MAX_REVISIONS)
        if revision != number or parent != previous:
            raise Rejected("credential_history_sequence")
        if not isinstance(payload, str) or len(payload.encode()) > 16384:
            raise Rejected("credential_history_size")
        hex_digest(digest)
        if not hmac.compare_digest(digest, mac(policy.key, revision, parent, payload)):
            raise Rejected("credential_history_integrity")
        event = decode(payload.encode())
        current_schema = type(event) is dict and event.get("schema") == CURRENT_SCHEMA
        fields(event, ("schema", "policy_digest", "actor", "action", "token_sha256", "request_id", "reason", "recorded_ns") + (("expires_at_ns",) if current_schema else ()))
        if canonical(event).decode() != payload or event["schema"] not in (SCHEMA, CURRENT_SCHEMA) or event["policy_digest"] != policy.digest:
            raise Rejected("credential_history_binding")
        if not current_schema and versioned:
            raise Rejected("credential_schema_regression")
        versioned = versioned or current_schema
        identifier(event["request_id"])
        if event["request_id"] in seen:
            raise Rejected("credential_request_duplicate")
        seen.add(event["request_id"])
        now = integer(event["recorded_ns"], 0, 2**63 - 1)
        if now < last_time:
            raise Rejected("credential_clock_regressed")
        state, deadlines = ReviewCredentials.transition(states[-1], expiries[-1], used, event)
        states.append(state); expiries.append(deadlines)
        history.append({"revision": revision, "event": event, "previous": parent, "head": digest})
        previous, last_time = digest, now
    return CredentialSnapshot(states, expiries, history)
