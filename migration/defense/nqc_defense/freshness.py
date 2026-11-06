"""X106: bounded decision age and clock-order checks on locally observed evidence."""

from .codec import Rejected, integer


MAX_TIME = 2**63 - 3601


def evaluate(started_at, decided_at, observed_at, maximum_age):
    integer(started_at, 0, MAX_TIME)
    integer(decided_at, 0, MAX_TIME)
    integer(maximum_age, 0, 300)
    if type(observed_at) is not list or not 1 <= len(observed_at) <= 17:
        raise Rejected("evidence_count")
    for stamp in observed_at:
        integer(stamp, 0, MAX_TIME)
    times = [started_at, *observed_at, decided_at]
    if any(right < left for left, right in zip(times, times[1:])):
        return ["clock_regressed"]
    if decided_at - started_at > maximum_age:
        return ["evidence_expired"]
    return []


def clock_floor(db):
    row = db.execute("SELECT value FROM meta WHERE key='clock_floor'").fetchone()
    if row is None:
        return 0
    try:
        value = int(row[0])
    except (TypeError, ValueError) as exc:
        raise Rejected("clock_state_invalid") from exc
    return integer(value, 0, MAX_TIME)


def require_current(db, now):
    integer(now, 0, MAX_TIME)
    if now < clock_floor(db):
        raise Rejected("clock_regressed")


def advance(db, timestamps):
    if not timestamps:
        raise Rejected("clock_samples_required")
    for stamp in timestamps:
        integer(stamp, 0, MAX_TIME)
    high = max(clock_floor(db), *timestamps)
    db.execute("INSERT INTO meta VALUES('clock_floor',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (str(high),))
