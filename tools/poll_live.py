#!/usr/bin/env python3
"""Poll LADOT live meter occupancy and append one snapshot line per poll.

WHY SNAPSHOTS, NOT EVENTS
The live feed reports each space's last transition. Storing transitions and
rebuilding a step function sounds better but is lossy: measured against the
June 2026 archive, a 10-minute poller sees only 59% of real transitions, and
the ones it drops are the short episodes -- so any dwell-time answer would be
biased long. Sampling the state instead is provably fine: against the same
ground truth, 5-minute sampling recovers hourly vacancy to within 0.33
percentage points with a mean bias of -0.002pp.

STORAGE
One line per poll in data/YYYY-MM-DD.csv:

    polled_at_utc,states

where `states` is one character per space, in the order given by the space
order file: V vacant, O occupied, ? not reported this poll. ~270 bytes a poll,
so a month is a couple of MB -- small enough to commit from CI, and trivially
mergeable across collectors (concatenate; each line stands alone).

  ./poll_live.py --ids sensored_ids.txt --collector laptop

Each collector writes its own subdirectory (data/<collector>/YYYY-MM-DD.csv).
The laptop poller and the CI cron would otherwise append to the same tracked
file and conflict on every pull; separate paths merge by construction.
"""
import argparse, datetime as dt, hashlib, json, os, sys, time, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")

LIVE = "https://data.lacity.org/resource/e7h6-4a3e.json"


def fetch(ids, token=None):
    """-> {spaceid: (state, age_hours_since_that_transition)}"""
    out = {}
    now = dt.datetime.now(dt.timezone.utc)
    hdrs = {"X-App-Token": token} if token else {}
    for i in range(0, len(ids), 150):
        chunk = ",".join("'%s'" % s for s in ids[i:i + 150])
        q = urllib.parse.urlencode({"$where": f"spaceid in ({chunk})", "$limit": 5000})
        req = urllib.request.Request(f"{LIVE}?{q}", headers=hdrs)
        with urllib.request.urlopen(req, timeout=45) as r:
            for row in json.load(r):
                t = dt.datetime.fromisoformat(row["eventtime"]).replace(tzinfo=dt.timezone.utc)
                out[row["spaceid"]] = (row["occupancystate"],
                                       (now - t).total_seconds() / 3600.0)
    return out


def parse_window(s):
    """'8-16:30' -> (480, 990): minutes after local midnight, end exclusive."""
    def mins(x):
        h, _, m = x.partition(":")
        return int(h) * 60 + int(m or 0)
    lo, hi = s.split("-")
    return mins(lo), mins(hi)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ids", default="sensored_ids.txt")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--collector", default="laptop", help="who is polling; names the subdirectory")
    p.add_argument("--token", help="optional Socrata app token")
    p.add_argument("--only-hours", help="collect only within this local window, e.g. 8-16:30")
    p.add_argument("--only-weekdays", action="store_true", help="skip Saturday and Sunday")
    p.add_argument("--stale-hours", type=float, default=24.0,
                   help="flag a state older than this in lowercase")
    a = p.parse_args()

    # Gate on LOS ANGELES local time, not UTC, so the window holds across DST.
    now_la = dt.datetime.now(LA)
    if a.only_weekdays and now_la.weekday() >= 5:
        print(f"{now_la:%Y-%m-%d %H:%M %Z}: weekend, not collecting")
        return 0
    if a.only_hours:
        lo, hi = parse_window(a.only_hours)
        if not (lo <= now_la.hour * 60 + now_la.minute < hi):
            print(f"{now_la:%Y-%m-%d %H:%M %Z}: outside {a.only_hours}, not collecting")
            return 0

    ids = [l.strip() for l in open(a.ids) if l.strip()]
    out_dir = os.path.join(a.data_dir, a.collector)
    os.makedirs(out_dir, exist_ok=True)

    # Pin the column order. If the space list ever changes, past files stay
    # readable because each one records the order it was written against.
    order_path = os.path.join(a.data_dir, "space_order.txt")
    digest = hashlib.sha1("\n".join(ids).encode()).hexdigest()[:8]
    if not os.path.exists(order_path):
        with open(order_path, "w") as f:
            f.write("# sha1:%s\n" % digest)
            f.write("\n".join(ids) + "\n")
    else:
        have = open(order_path).readline().strip()
        if have != "# sha1:%s" % digest:
            sys.exit(f"Space list changed ({have} -> # sha1:{digest}). "
                     f"Start a new --data-dir rather than mixing orders.")

    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    day = now[:10]
    try:
        states = fetch(ids, a.token)
    except Exception as e:
        with open(os.path.join(out_dir, "failures.log"), "a") as f:
            f.write(f"{now}\t{str(e)[:200]}\n")
        print(f"{now} poll failed: {e}", file=sys.stderr)
        return 1

    # The feed reports the LAST KNOWN state and never expires it, so a dead
    # sensor keeps asserting whatever it last saw. Anything that has not posted
    # a transition in --stale-hours is written lowercase: still recorded, but
    # flagged so the analysis can weigh or drop it. A genuinely parked car does
    # sit unchanged overnight, so the threshold is a day, not a few hours.
    def ch(s):
        v = states.get(s)
        if v is None:
            return "?"
        state, age = v
        if state == "VACANT":
            return "v" if age > a.stale_hours else "V"
        if state == "OCCUPIED":
            return "o" if age > a.stale_hours else "O"
        return "?"                      # the feed's own UNKNOWN state
    line = "".join(ch(s) for s in ids)

    path = os.path.join(out_dir, f"{day}.csv")
    new = not os.path.exists(path)
    with open(path, "a") as f:
        if new:
            f.write("polled_at_utc,states\n")
        f.write(f"{now},{line}\n")

    vac, occ = line.count("V") + line.count("v"), line.count("O") + line.count("o")
    stale, unk = line.count("v") + line.count("o"), line.count("?")
    print(f"{now}  {vac} vacant / {occ} occupied"
          + (f" / {stale} stale" if stale else "")
          + (f" / {unk} unknown" if unk else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
