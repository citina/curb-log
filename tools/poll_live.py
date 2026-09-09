#!/usr/bin/env python3
"""Poll LADOT's live meter occupancy for a set of spaces; store new events.

The live feed (e7h6-4a3e) holds the LAST KNOWN state of each space plus the
timestamp of that transition. Storing (spaceid, eventtime, state) and
de-duplicating on the first two rebuilds the same event log the LADOT archive
publishes two months later -- so this fills the gap until yours is published.

  ./poll_live.py --ids sensored_ids.txt --db occupancy.sqlite

Run it on a timer (see install_poller.sh). Safe to run as often as you like;
repeat polls with no transition write nothing.
"""
import argparse, json, sqlite3, sys, time, urllib.parse, urllib.request

LIVE = "https://data.lacity.org/resource/e7h6-4a3e.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  spaceid   TEXT NOT NULL,
  eventtime TEXT NOT NULL,          -- UTC, as LADOT reports it
  state     TEXT NOT NULL,          -- VACANT | OCCUPIED
  PRIMARY KEY (spaceid, eventtime)
);
CREATE TABLE IF NOT EXISTS polls (
  polled_at TEXT NOT NULL,          -- our clock, UTC
  n_spaces  INTEGER NOT NULL,
  n_new     INTEGER NOT NULL,
  ok        INTEGER NOT NULL,
  note      TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_time ON events(eventtime);
"""


def fetch(ids, token=None):
    rows = []
    hdrs = {"X-App-Token": token} if token else {}
    for i in range(0, len(ids), 150):
        chunk = ",".join("'%s'" % s for s in ids[i:i + 150])
        q = urllib.parse.urlencode({"$where": f"spaceid in ({chunk})", "$limit": 5000})
        req = urllib.request.Request(f"{LIVE}?{q}", headers=hdrs)
        with urllib.request.urlopen(req, timeout=60) as r:
            rows += json.load(r)
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ids", default="sensored_ids.txt")
    p.add_argument("--db", default="occupancy.sqlite")
    p.add_argument("--token", help="optional Socrata app token (raises rate limits)")
    a = p.parse_args()

    ids = [l.strip() for l in open(a.ids) if l.strip()]
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    db = sqlite3.connect(a.db)
    db.executescript(SCHEMA)

    try:
        rows = fetch(ids, a.token)
    except Exception as e:                      # network down, laptop asleep, LADOT hiccup
        db.execute("INSERT INTO polls VALUES (?,?,?,?,?)", (now, 0, 0, 0, str(e)[:200]))
        db.commit()
        print(f"{now} poll failed: {e}", file=sys.stderr)
        return 1

    before = db.execute("SELECT count(*) FROM events").fetchone()[0]
    db.executemany(
        "INSERT OR IGNORE INTO events VALUES (?,?,?)",
        [(r["spaceid"], r["eventtime"], r["occupancystate"]) for r in rows])
    after = db.execute("SELECT count(*) FROM events").fetchone()[0]
    new = after - before
    db.execute("INSERT INTO polls VALUES (?,?,?,?,?)", (now, len(rows), new, 1, None))
    db.commit()

    vac = sum(1 for r in rows if r["occupancystate"] == "VACANT")
    print(f"{now}  {len(rows)} spaces  {vac} vacant  (+{new} new events, {after} total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
