#!/usr/bin/env python3
"""Build the page's data.json from every source we have, segmented by period.

Two kinds of input, combined into one grid:

  ARCHIVE  (LADOT monthly CSVs) — a complete event log. Occupancy is a step
           function; we sample it every --grid minutes.
  POLLS    (our own snapshots)  — already samples of state, taken every 5 min.

Both end up as "share of samples where the space was vacant", which is why they
are comparable: the 5-minute sampling was validated against the archive at
0.33pp of the true hourly rate.

PERIODS ARE NEVER BLENDED. Summer and term-time are different worlds on a
university block — measured on these exact spaces, midday vacancy ran 49% in
summer and 6% in term. Averaging them produces a confidently wrong number, so
each period is aggregated separately and the page picks one.

  ./build_data.py --out ../docs/data.json
"""
import argparse, collections, csv, datetime as dt, glob, json, os, re, sys
from zoneinfo import ZoneInfo

LA = ZoneInfo("America/Los_Angeles")

# USC Fall 2026 classes began Monday 24 August 2026. The sensors on these blocks
# came online 12 May 2026, so nothing exists before that.
PERIODS = [
    {"id": "fall-2026",   "label": "Fall 2026 term", "start": "2026-08-24", "end": None},
    {"id": "summer-2026", "label": "Summer 2026",    "start": "2026-05-12", "end": "2026-08-23"},
]


def cluster_of(blockface):
    m = re.match(r"^(\d+)\s+(.*)$", blockface.strip())
    return f"{m.group(2)} {int(m.group(1)) // 100}xx" if m else blockface


def period_of(d):
    for p in PERIODS:
        if d.isoformat() >= p["start"] and (p["end"] is None or d.isoformat() <= p["end"]):
            return p["id"]
    return None


class Acc:
    """(period, cluster, dow, hour) -> [samples, sum_free, samples_with_none_free]"""
    def __init__(self):
        self.cells = collections.defaultdict(lambda: [0, 0, 0])
        self.days = collections.defaultdict(set)
        self.n = collections.Counter()
        self.sources = collections.defaultdict(set)

    def add(self, t, cluster, free, known, period, source):
        if not known:
            return
        self.cells[(period, cluster, t.weekday(), t.hour)][0] += 1
        self.cells[(period, cluster, t.weekday(), t.hour)][1] += free
        if free == 0:
            self.cells[(period, cluster, t.weekday(), t.hour)][2] += 1
        self.days[period].add(t.date().isoformat())
        self.n[period] += 1
        self.sources[period].add(source)


def load_archive(paths, keep, cluster_by_space, acc, grid_min, stale_h, window):
    """Reconstruct each space's step function and sample it on a fixed grid."""
    for path in paths:
        ev = collections.defaultdict(list)
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                sid = r["SpaceID"]
                if sid not in keep:
                    continue
                ev[sid].append((dt.datetime.strptime(r["EventTime_Local"], "%m/%d/%Y %I:%M:%S %p"),
                                r["OccupancyState"]))
        if not ev:
            continue
        for v in ev.values():
            v.sort()
        allt = [t for v in ev.values() for t, _ in v]
        t0 = min(allt).replace(hour=0, minute=0, second=0, microsecond=0)
        t1 = max(allt)
        step = dt.timedelta(minutes=grid_min)
        stale = dt.timedelta(hours=stale_h)

        # state[space] walked forward in lockstep with the sample clock
        ptr = {s: 0 for s in ev}
        cur = {s: None for s in ev}
        seen = {s: None for s in ev}
        t = t0
        while t <= t1:
            per = period_of(t.date())
            inwin = window[0] <= t.hour < window[1] and t.weekday() < 5
            for s, e in ev.items():
                i, n = ptr[s], len(e)
                while i < n and e[i][0] <= t:
                    seen[s], cur[s] = e[i]
                    i += 1
                ptr[s] = i
            if per and inwin:
                byc = collections.defaultdict(lambda: [0, 0])
                for s in ev:
                    if cur[s] is None or (t - seen[s]) > stale:
                        continue
                    c = cluster_by_space.get(s)
                    if c is None:
                        continue
                    byc[c][1] += 1
                    if cur[s] == "VACANT":
                        byc[c][0] += 1
                for c, (free, known) in byc.items():
                    acc.add(t, c, free, known, per, "archive")
            t += step
        print(f"  archive {os.path.basename(path)}: {len(ev)} spaces, "
              f"{sum(len(v) for v in ev.values()):,} events", file=sys.stderr)


def load_polls(data_dir, cluster_by_space, acc, window):
    order_path = os.path.join(data_dir, "space_order.txt")
    if not os.path.exists(order_path):
        return
    ids = [l.strip() for l in open(order_path) if l.strip() and not l.startswith("#")]
    paths = glob.glob(os.path.join(data_dir, "*.csv")) + glob.glob(os.path.join(data_dir, "*", "*.csv"))
    idx = collections.defaultdict(list)
    for i, s in enumerate(ids):
        c = cluster_by_space.get(s)
        if c:
            idx[c].append(i)
    n = 0
    for path in sorted(paths):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                t = (dt.datetime.fromisoformat(r["polled_at_utc"])
                     .replace(tzinfo=dt.timezone.utc).astimezone(LA).replace(tzinfo=None))
                per = period_of(t.date())
                if not per or not (window[0] <= t.hour < window[1]) or t.weekday() >= 5:
                    continue
                st = r["states"]
                for c, cols in idx.items():
                    free = sum(1 for i in cols if i < len(st) and st[i] in "Vv")
                    known = sum(1 for i in cols if i < len(st) and st[i] in "VOvo")
                    acc.add(t, c, free, known, per, "poll")
                n += 1
    print(f"  polls: {n:,} snapshots", file=sys.stderr)


def save_archive_cache(acc, path):
    out = {}
    for (per, c, d, h), v in acc.cells.items():
        out.setdefault(per, {"n": 0, "days": 0, "cells": {}})
        out[per]["cells"][f"{c}|{d}|{h}"] = v
    for per in out:
        out[per]["n"] = acc.n[per]
        out[per]["days"] = len(acc.days[per])
    json.dump(out, open(path, "w"), separators=(",", ":"))
    print(f"  cached archive contribution -> {path}", file=sys.stderr)


def load_archive_cache(acc, path):
    if not os.path.exists(path):
        print("  no archive extracts and no cache — polls only", file=sys.stderr)
        return
    for per, blk in json.load(open(path)).items():
        for key, v in blk["cells"].items():
            c, d, h = key.rsplit("|", 2)
            acc.cells[(per, c, int(d), int(h))] = list(v)
        acc.n[per] += blk["n"]
        acc.sources[per].add("archive")
        # day identities are not kept in the cache; carry the count forward
        acc.days[per].update("cached-%d" % i for i in range(blk["days"]))
    print(f"  archive contribution from cache ({path})", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ids", default="sensored_ids.txt")
    p.add_argument("--spaces", default="spaces.json")
    p.add_argument("--archive", default="usc_*.csv", help="glob of LADOT archive extracts")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--grid", type=int, default=15)
    p.add_argument("--stale-hours", type=float, default=24)
    p.add_argument("--hours", default="8-17")
    p.add_argument("--out", default="../docs/data.json")
    p.add_argument("--archive-cache", default="archive_cells.json",
                   help="archive contribution, cached so CI need not hold the 200MB extracts")
    a = p.parse_args()

    window = tuple(int(x) for x in a.hours.split("-"))
    ids = [l.strip() for l in open(a.ids) if l.strip()]
    meta = json.load(open(a.spaces))
    cluster_by_space = {s: cluster_of(meta[s]["blockface"]) for s in ids if s in meta}
    clusters = sorted(set(cluster_by_space.values()))

    acc = Acc()
    print("building:", file=sys.stderr)
    archives = sorted(glob.glob(a.archive))
    if archives:
        load_archive(archives, set(ids), cluster_by_space, acc, a.grid, a.stale_hours, window)
        save_archive_cache(acc, a.archive_cache)
    else:
        # CI has the repo but not the multi-hundred-MB monthly extracts, so the
        # archive half is precomputed locally and committed as a small cache.
        load_archive_cache(acc, a.archive_cache)
    load_polls(a.data_dir, cluster_by_space, acc, window)

    def centroid(c):
        ps = [meta[s]["latlng"] for s, cc in cluster_by_space.items() if cc == c and meta[s].get("latlng")]
        if not ps:
            return None
        return [sum(float(q["latitude"]) for q in ps) / len(ps),
                sum(float(q["longitude"]) for q in ps) / len(ps)]

    periods = []
    for spec in PERIODS:
        pid = spec["id"]
        if not acc.n[pid]:
            continue
        cells = {}
        for (per, c, d, h), v in acc.cells.items():
            if per == pid:
                cells[f"{c}|{d}|{h}"] = v
        periods.append({
            "id": pid, "label": spec["label"],
            "start": spec["start"], "end": spec["end"],
            "sources": sorted(acc.sources[pid]),
            "n_samples": acc.n[pid],
            "days": len(acc.days[pid]),
            "cells": cells,
        })

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "window_start": window[0], "window_end": window[1],
        "term_start": "2026-08-24",
        "sensors_live": "2026-05-12",
        "clusters": {c: {"n_spaces": sum(1 for v in cluster_by_space.values() if v == c),
                         "spaces": [s for s in ids if cluster_by_space.get(s) == c],
                         "centroid": centroid(c),
                         "blockfaces": sorted({meta[s]["blockface"] for s in ids
                                               if cluster_by_space.get(s) == c})}
                     for c in clusters},
        "periods": periods,
        "default_period": periods[0]["id"] if periods else None,
    }
    json.dump(payload, open(a.out, "w"), separators=(",", ":"))
    print(f"\nwrote {a.out} ({os.path.getsize(a.out)//1024} KB)")
    for pr in periods:
        print(f"  {pr['label']:<18} {pr['n_samples']:>8,} samples · {pr['days']:>3} days · "
              f"{len(pr['cells']):>3} cells · {'+'.join(pr['sources'])}")


if __name__ == "__main__":
    main()
