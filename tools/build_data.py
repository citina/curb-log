#!/usr/bin/env python3
"""Build the page's data.json: exact time-weighted occupancy, in 30-minute cells.

HOW "SPACES FREE" IS COMPUTED  (docs/METHOD.md says it in plain language)
The LADOT archive is an event log: each row says a space became VACANT or
OCCUPIED at an exact second. Between two events nothing changed, so every
space's state is known at every second. For each cluster we sweep its events in
time order, keeping a running count of known and vacant spaces. Each stretch of
constant state is split at 30-minute cell boundaries and credited to its cell,
day by day, as:

    observed seconds       (duration)
    vacant space-seconds   (vacant count x duration)
    empty seconds          (duration, when no known space is vacant)
    known space-seconds    (known count x duration)

so a cell's share free = vacant space-seconds / known space-seconds, its mean
spaces free = that share x the cluster's size, and "found nothing" = empty
seconds / observed seconds. That is the exact average over the half hour, not an
estimate from samples. Dividing by known space-seconds rather than by time is
what keeps a space we can't see from being counted as occupied.

A space silent for more than --stale-hours (72) drops out of the known count.
Silence normally just means nothing changed — a space can sit vacant all
weekend — but a dead or stuck sensor would otherwise assert its last state for
weeks (C127 and C145 on 3601 Vermont did, in summer). Before its first event a
space is unknown too. A stretch counts only while at least --min-known (80%) of
the cluster's spaces are known.

Holidays and non-teaching days (EXCLUDED below) are left out of every pattern.

Our own polls are not an event log — they are snapshots — so each snapshot is
held forward until the next one, capped at --hold minutes so a dropped run or a
sleeping laptop becomes unobserved time rather than being papered over. A
lowercase state (over 24 hours old) or '?' counts as unknown.

PRECEDENCE: where the archive covers a day, it is used and polls for that day are
ignored — the archive is the complete record; polls are a stand-in until it is
published. PERIODS ARE NEVER BLENDED: summer and term are aggregated separately
(midday vacancy on these spaces ran ~49% in summer, ~6% in term).

  ./build_data.py --out ../docs/data.json
  ./build_data.py --report            # print the grids in the terminal
"""
import argparse, collections, csv, datetime as dt, glob, json, os, re, sys
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")

# USC Fall 2026 classes began Monday 24 August 2026. Sensors on these blocks came
# online 12 May 2026; nothing exists before that.
PERIODS = [
    {"id": "fall-2026",   "label": "Fall 2026 term", "start": "2026-08-24", "end": None},
    {"id": "summer-2026", "label": "Summer 2026",    "start": "2026-05-12", "end": "2026-08-23"},
]
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Left out of every pattern: USC holidays and non-teaching days, which aren't a
# normal day at these curbs. Term dates are from usc.edu/academic-calendar;
# Citina confirmed the whole list, summer holidays included, 2026-09-11.
# Inclusive ranges; only weekdays are kept, since the grid is weekdays.
NOT_NORMAL = [
    ("2026-05-25", "2026-05-25", "Memorial Day"),
    ("2026-06-19", "2026-06-19", "Juneteenth"),
    ("2026-07-03", "2026-07-03", "Independence Day (observed)"),
    ("2026-09-07", "2026-09-07", "Labor Day"),
    ("2026-10-08", "2026-10-09", "Fall recess"),
    ("2026-11-11", "2026-11-11", "Veterans Day"),
    ("2026-11-25", "2026-11-29", "Thanksgiving"),
    ("2026-12-05", "2026-12-08", "Study days"),
    ("2026-12-09", "2026-12-16", "Final exams"),
    ("2026-12-17", "2027-01-10", "Winter recess"),
]


def _weekdays(ranges):
    out = {}
    for first, last, label in ranges:
        d = dt.date.fromisoformat(first)
        while d <= dt.date.fromisoformat(last):
            if d.weekday() < 5:
                out[d.isoformat()] = label
            d += dt.timedelta(days=1)
    return out


EXCLUDED = _weekdays(NOT_NORMAL)


def cluster_of(blockface):
    m = re.match(r"^(\d+)\s+(.*)$", blockface.strip())
    return f"{m.group(2)} {int(m.group(1)) // 100}xx" if m else blockface


def period_of(d):
    iso = d.isoformat()
    for p in PERIODS:
        if iso >= p["start"] and (p["end"] is None or iso <= p["end"]):
            return p["id"]
    return None


def parse_window(s):
    """'8-16:30' -> (480, 990): minutes after local midnight, end exclusive."""
    def mins(x):
        h, _, m = x.partition(":")
        return int(h) * 60 + int(m or 0)
    lo, hi = s.split("-")
    return mins(lo), mins(hi)


class Acc:
    """(cluster, date, slot) -> [observed_s, vacant_space_s, empty_s, known_space_s]

    Kept per date, so holidays and periods are applied when cells are summed
    rather than baked in during the sweep. The window is in minutes after local
    midnight; sizes is each cluster's number of spaces."""

    def __init__(self, win_start, win_end, slot_min, sizes, min_known):
        self.ws, self.we, self.slot = win_start, win_end, slot_min
        self.sizes, self.min_known = sizes, min_known
        self.cells = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        self.sources = collections.defaultdict(set)      # date -> {"archive", "poll"}
        self.latest_poll = None

    def add(self, a, b, cluster, vacant, known, source):
        """Credit a stretch [a, b) of constant state to the cells it overlaps."""
        if b <= a or known <= 0 or known < self.min_known * self.sizes[cluster]:
            return
        t = a
        while t < b:
            mins = t.hour * 60 + t.minute
            # jump straight to the window when outside it
            if t.weekday() >= 5 or mins >= self.we:
                t = (t + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                continue
            if mins < self.ws:
                t = t.replace(hour=self.ws // 60, minute=self.ws % 60, second=0, microsecond=0)
                continue
            k = (mins - self.ws) // self.slot
            edge = t.replace(hour=0, minute=0, second=0, microsecond=0) + \
                dt.timedelta(minutes=self.ws + (k + 1) * self.slot)
            q = min(b, edge)
            if period_of(t.date()):
                L = (q - t).total_seconds()
                day = t.date().isoformat()
                c = self.cells[(cluster, day, k)]
                c[0] += L
                c[1] += vacant * L
                if vacant == 0:
                    c[2] += L
                c[3] += known * L
                self.sources[day].add(source)
            t = q


def summarise(cells, sources, excluded):
    """Sum per-date cells into (period, cluster, dow, slot), leaving out excluded days.

    Returns ({key: [observed_s, vacant_space_s, empty_s, known_space_s, {dates}]},
             {period: {dates}}, {period: {sources}})."""
    out = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, set()])
    days, srcs = collections.defaultdict(set), collections.defaultdict(set)
    for (c, day, k), v in cells.items():
        d = dt.date.fromisoformat(day)
        per = period_of(d)
        if day in excluded or not per:
            continue
        x = out[(per, c, d.weekday(), k)]
        for i in range(4):
            x[i] += v[i]
        x[4].add(day)
        days[per].add(day)
        srcs[per] |= sources[day]
    return out, days, srcs


def load_archive(paths, cluster_spaces, acc, stale_h):
    """Exact sweep over each cluster's merged event log. Returns dates covered."""
    covered = set()
    stale = dt.timedelta(hours=stale_h)
    keep = {s for ss in cluster_spaces.values() for s in ss}
    for path in paths:
        ev = collections.defaultdict(list)
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r["SpaceID"] in keep:
                    ev[r["SpaceID"]].append(
                        (dt.datetime.strptime(r["EventTime_Local"], "%m/%d/%Y %I:%M:%S %p"),
                         r["OccupancyState"]))
        if not ev:
            continue
        end = max(t for v in ev.values() for t, _ in v)
        start = min(t for v in ev.values() for t, _ in v)
        d = start.date()
        while d <= end.date():
            covered.add(d.isoformat())
            d += dt.timedelta(days=1)

        for cluster, spaces in cluster_spaces.items():
            stream = []
            for s in spaces:
                e = sorted(ev.get(s, []))
                for i, (t, st) in enumerate(e):
                    stream.append((t, s, "V" if st == "VACANT" else "O" if st == "OCCUPIED" else None))
                    nxt = e[i + 1][0] if i + 1 < len(e) else end
                    if nxt - t > stale:                    # silent too long: stop trusting it
                        stream.append((t + stale, s, None))
            stream.sort(key=lambda x: x[0])
            state = {}
            prev = None
            for t, s, st in stream:
                if prev is not None and t > prev:
                    vals = list(state.values())
                    acc.add(prev, t, cluster, vals.count("V"), len(vals), "archive")
                if st is None:
                    state.pop(s, None)
                else:
                    state[s] = st
                prev = t
            if prev is not None and end > prev:
                vals = list(state.values())
                acc.add(prev, end, cluster, vals.count("V"), len(vals), "archive")
        print(f"  archive {os.path.basename(path)}: {len(ev)} spaces, "
              f"{sum(len(v) for v in ev.values()):,} events, {start:%-d %b}-{end:%-d %b}",
              file=sys.stderr)
    return covered


def load_polls(data_dir, cluster_spaces, acc, hold_min, skip_dates):
    order_path = os.path.join(data_dir, "space_order.txt")
    if not os.path.exists(order_path):
        return 0
    ids = [l.strip() for l in open(order_path) if l.strip() and not l.startswith("#")]
    pos = {s: i for i, s in enumerate(ids)}
    cols = {c: [pos[s] for s in ss if s in pos] for c, ss in cluster_spaces.items()}
    snaps = []
    for path in glob.glob(os.path.join(data_dir, "*.csv")) + glob.glob(os.path.join(data_dir, "*", "*.csv")):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                t = (dt.datetime.fromisoformat(r["polled_at_utc"])
                     .replace(tzinfo=dt.timezone.utc).astimezone(LA).replace(tzinfo=None))
                if t.date().isoformat() not in skip_dates:
                    snaps.append((t, r["states"]))
    snaps.sort()
    acc.latest_poll = snaps[-1][0] if snaps else None
    hold = dt.timedelta(minutes=hold_min)
    for i, (t, st) in enumerate(snaps):
        b = min(snaps[i + 1][0], t + hold) if i + 1 < len(snaps) else t + hold
        for c, cc in cols.items():
            # uppercase only: lowercase marks a state >24h old and '?' no state,
            # both unknown, exactly as the archive sweep drops silent sensors
            v = sum(1 for j in cc if j < len(st) and st[j] == "V")
            k = sum(1 for j in cc if j < len(st) and st[j] in "VO")
            acc.add(t, b, c, v, k, "poll")
    print(f"  polls: {len(snaps):,} snapshots used"
          + (f"; archive covers {len(skip_dates)} days, polls on those days ignored" if skip_dates else ""),
          file=sys.stderr)
    return len(snaps)


def slot_label(ws, slot, k):
    m = ws + k * slot
    h, mm = divmod(m, 60)
    return f"{h % 12 or 12}:{mm:02d}{'a' if h < 12 else 'p'}"


def report(payload):
    ws, we = round(payload["window_start"] * 60), round(payload["window_end"] * 60)
    sl = payload["slot_min"]
    nslot = (we - ws) // sl
    for pr in payload["periods"]:
        print(f"\n=== {pr['label']} · {pr['days']} weekdays · {'+'.join(pr['sources'])} ===")
        for c, info in payload["clusters"].items():
            n = info["n_spaces"]
            print(f"\n{c} ({n} spaces) — mean spaces free, 30-min cells")
            print("      " + "".join(f"{slot_label(ws, sl, k)[:-1]:>6}" for k in range(nslot)))
            for d in range(5):
                row = []
                for k in range(nslot):
                    v = pr["cells"].get(f"{c}|{d}|{k}")
                    row.append(f"{v[1] / v[4] * n:6.1f}" if v and v[4] else "     ·")
                print(f"{DOW[d]:<6}" + "".join(row))
            print("      days behind each cell:")
            for d in range(5):
                row = []
                for k in range(nslot):
                    v = pr["cells"].get(f"{c}|{d}|{k}")
                    row.append(f"{v[3]:6d}" if v else "     ·")
                print(f"{DOW[d]:<6}" + "".join(row))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ids", default="sensored_ids.txt")
    p.add_argument("--spaces", default="spaces.json")
    p.add_argument("--archive", default="usc_*.csv", help="glob of LADOT archive extracts")
    p.add_argument("--archive-cache", default="archive_cells.json")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--window", default="8-16:30", help="grid window, local time, e.g. 8-16:30")
    p.add_argument("--slot", type=int, default=30, help="minutes per cell")
    p.add_argument("--stale-hours", type=float, default=72,
                   help="hours of silence after which a sensor's last state stops counting")
    p.add_argument("--min-known", type=float, default=0.8,
                   help="share of a cluster's spaces that must be known for a stretch to count")
    p.add_argument("--hold", type=float, default=10, help="max minutes a poll snapshot is held")
    p.add_argument("--out", default="../docs/data.json")
    p.add_argument("--report", action="store_true")
    a = p.parse_args()

    ws, we = parse_window(a.window)
    ids = [l.strip() for l in open(a.ids) if l.strip()]
    meta = json.load(open(a.spaces))
    cluster_spaces = collections.defaultdict(list)
    for s in ids:
        if s in meta:
            cluster_spaces[cluster_of(meta[s]["blockface"])].append(s)
    sizes = {c: len(ss) for c, ss in cluster_spaces.items()}

    acc = Acc(ws, we, a.slot, sizes, a.min_known)
    print("building:", file=sys.stderr)
    # The cache is keyed by extract file, so a run holding only some extracts
    # (CI holds only May-June; a new month arrives alone) recomputes what it has and
    # keeps the rest instead of silently dropping it.
    cache = json.load(open(a.archive_cache)) if os.path.exists(a.archive_cache) else {}
    files = cache.get("files", {})
    # Cached cells are cut to one window and slot ([start_min, end_min, slot_min])
    # and swept under one method (stale cut, minimum known share). Mixing cuts
    # would leave columns silently empty or blend two methods, so a mismatched
    # cache is only usable if every extract in it is here to recompute. (An
    # unstamped cache predates the stamps and was cut to 8-16.)
    grid = [ws, we, a.slot]
    method = {"stale_hours": a.stale_hours, "min_known": a.min_known}
    was = (cache.get("grid", [480, 960, 30]), cache.get("method"))
    if files and was != (grid, method):
        here = {os.path.basename(p) for p in glob.glob(a.archive)}
        gone = sorted(set(files) - here)
        if gone:
            sys.exit(f"{a.archive_cache} is cut to grid {was[0]} with method {was[1]}, not {grid} with "
                     f"{method}, and {', '.join(gone)} isn't here to recompute. "
                     f"Fetch it with fetch_history.py first.")
        files = {}
    for path in sorted(glob.glob(a.archive)):
        one = Acc(ws, we, a.slot, sizes, a.min_known)
        dates = load_archive([path], cluster_spaces, one, a.stale_hours)
        files[os.path.basename(path)] = {
            "dates": sorted(dates),
            "cells": {f"{c}|{k}|{day}": [round(x, 1) for x in v]
                      for (c, day, k), v in sorted(one.cells.items())}}
    covered = set()
    for blk in files.values():
        covered.update(blk["dates"])
        for key, v in blk["cells"].items():
            c, k, day = key.split("|")
            cell = acc.cells[(c, day, int(k))]
            for i in range(4):
                cell[i] += v[i]
            acc.sources[day].add("archive")
    if files:
        json.dump({"grid": grid, "method": method, "files": files}, open(a.archive_cache, "w"),
                  separators=(",", ":"))
        print(f"  archive extracts in cache: {', '.join(sorted(files))}", file=sys.stderr)
    load_polls(a.data_dir, cluster_spaces, acc, a.hold, covered)

    def centroid(c):
        ps = [meta[s]["latlng"] for s in cluster_spaces[c] if meta[s].get("latlng")]
        return [sum(float(q["latitude"]) for q in ps) / len(ps),
                sum(float(q["longitude"]) for q in ps) / len(ps)] if ps else None

    agg, days, srcs = summarise(acc.cells, acc.sources, EXCLUDED)
    periods = []
    for spec in PERIODS:
        pid = spec["id"]
        cells = {f"{c}|{d}|{k}": [round(v[0]), round(v[1]), round(v[2]), len(v[4]), round(v[3])]
                 for (per, c, d, k), v in sorted(agg.items()) if per == pid and v[0] > 0}
        if not cells:
            continue
        periods.append({"id": pid, "label": spec["label"], "start": spec["start"], "end": spec["end"],
                        "sources": sorted(srcs[pid]), "days": len(days[pid]),
                        "cells": cells})

    through = acc.latest_poll or (dt.datetime.fromisoformat(max(covered)) if covered else None)
    payload = {
        # the newest data inside, in LA local time — not the build clock, so a
        # rebuild with no new data is byte-identical and there is nothing to commit
        "data_through": through.isoformat(timespec="minutes") if through else None,
        # hours, fractional when the window ends on a half hour (16.5 = 4:30pm)
        "window_start": ws // 60 if ws % 60 == 0 else ws / 60,
        "window_end": we // 60 if we % 60 == 0 else we / 60,
        "slot_min": a.slot,
        # known_space_seconds comes last so a page cached from before it was
        # added still finds the first four fields where it expects them
        "cell_format": ["observed_seconds", "vacant_space_seconds", "empty_seconds", "days",
                        "known_space_seconds"],
        "stale_hours": a.stale_hours, "min_known": a.min_known,
        "excluded_days": EXCLUDED,
        "term_start": "2026-08-24", "sensors_live": "2026-05-12",
        "clusters": {c: {"n_spaces": len(ss), "spaces": ss, "centroid": centroid(c),
                         "blockfaces": sorted({meta[s]["blockface"] for s in ss})}
                     for c, ss in sorted(cluster_spaces.items())},
        "periods": periods,
        "default_period": periods[0]["id"] if periods else None,
    }
    json.dump(payload, open(a.out, "w"), separators=(",", ":"))
    print(f"\nwrote {a.out} ({os.path.getsize(a.out)//1024} KB)")
    for pr in periods:
        print(f"  {pr['label']:<16} {pr['days']:>3} weekdays · {len(pr['cells']):>3} cells · "
              f"{'+'.join(pr['sources'])}")
    if a.report:
        report(payload)


if __name__ == "__main__":
    main()
