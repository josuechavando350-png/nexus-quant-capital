"""M39's fixed-window admission limiter; persistent and transaction-safe."""

def admit(db, subject, now, limit, window):
    row = db.execute("SELECT start,count,last FROM buckets WHERE subject=?", (subject,)).fetchone()
    if row and now < row[2]:
        return False
    if row is None or now >= row[0] + window:
        start, count = now, 0
    else:
        start, count = row[0], row[1]
    allowed = count < limit
    db.execute("INSERT INTO buckets VALUES(?,?,?,?) ON CONFLICT(subject) DO UPDATE SET "
               "start=excluded.start,count=excluded.count,last=excluded.last",
               (subject, start, count + int(allowed), now))
    return allowed
