#!/usr/bin/env python3
"""Weekday x hour parking patterns from the snapshot store.

Reads data/*.csv (one line per poll, one character per space) and reports, for
each walkable cluster, how many spaces are typically free at each weekday and
hour -- plus how often you would find NOTHING, which is the number that decides
whether a trip is worth it.

Clusters combine BOTH SIDES of one hundred-block, because that is the unit you
actually drive: LADOT splits Vermont between 36th and 38th into six block faces
(3600/3601/3650/3651/3700/3701), and the parking app shows the lot as one place.

  ./patterns.py                          # everything collected so far
  ./patterns.py --cluster "VERMONT AVE 36xx"
  ./patterns.py --json patterns.json     # for the tracker page

Coverage is printed with every result. Polls stop while the laptop sleeps, and
that missingness is not random -- it tracks your day -- so a cell with few polls
must be read as "not measured", never as "quiet".
"""
import argparse, collections, csv, datetime as dt, glob, json, os, re, sys
from zoneinfo import ZoneInfo

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LA = ZoneInfo("America/Los_Angeles")


def local(ts):
    """Stored timestamps are UTC; report in LA local time, DST included."""
    return (dt.datetime.fromisoformat(ts)
            .replace(tzinfo=dt.timezone.utc)
            .astimezone(LA)
            .replace(tzinfo=None))


def cluster_of(blockface):
    """'3601 VERMONT AVE' -> 'VERMONT AVE 36xx' (both sides, one block)."""
    m = re.match(r"^(\d+)\s+(.*)$", blockface.strip())
    if not m:
        return blockface
    return f"{m.group(2)} {int(m.group(1))//100}xx"


def load(data_dir):
    order_path = os.path.join(data_dir, "space_order.txt")
    if not os.path.exists(order_path):
        sys.exit(f"No {order_path}. Run poll_live.py first.")
    ids = [l.strip() for l in open(order_path) if l.strip() and not l.startswith("#")]

    rows = []
    # every collector's subdirectory, plus any files left at the top level
    paths = glob.glob(os.path.join(data_dir, "*.csv")) + \
            glob.glob(os.path.join(data_dir, "*", "*.csv"))
    for path in sorted(paths):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows.append((local(r["polled_at_utc"]), r["states"]))
    return ids, sorted(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default="data")
    p.add_argument("--spaces", default="spaces.json")
    p.add_argument("--cluster", help="show one cluster's full weekday x hour grid")
    p.add_argument("--hours", default="7-21")
    p.add_argument("--min-polls", type=int, default=3, help="hide cells thinner than this")
    p.add_argument("--json")
    p.add_argument("--exclude-stale", action="store_true",
                   help="drop states the feed had not refreshed in a day")
    a = p.parse_args()

    ids, rows = load(a.data_dir)
    if not rows:
        sys.exit("No polls collected yet.")
    meta = json.load(open(a.spaces)) if os.path.exists(a.spaces) else {}

    # column index -> cluster
    col_cluster = [cluster_of(meta.get(s, {}).get("blockface", "?")) for s in ids]
    clusters = sorted(set(col_cluster))
    idx = collections.defaultdict(list)
    for i, c in enumerate(col_cluster):
        idx[c].append(i)

    # (cluster, dow, hour) -> [n_polls, sum_free, n_polls_with_zero_free]
    # Lowercase v/o mark a state the feed had not refreshed in a day: recorded,
    # but possibly a dead sensor asserting a stale reading.
    agg = collections.defaultdict(lambda: [0, 0, 0])
    stale_obs = total_obs = 0
    for t, states in rows:
        for c, cols in idx.items():
            if a.exclude_stale:
                free = sum(1 for i in cols if states[i] == "V")
                known = sum(1 for i in cols if states[i] in "VO")
            else:
                free = sum(1 for i in cols if states[i] in "Vv")
                known = sum(1 for i in cols if states[i] in "VOvo")
            stale_obs += sum(1 for i in cols if states[i] in "vo")
            total_obs += len(cols)
            if not known:
                continue
            k = (c, t.weekday(), t.hour)
            agg[k][0] += 1
            agg[k][1] += free
            if free == 0:
                agg[k][2] += 1

    h0, h1 = (int(x) for x in a.hours.split("-"))
    hours = list(range(h0, h1))
    span = f"{rows[0][0]:%a %d %b %H:%M} to {rows[-1][0]:%a %d %b %H:%M}"
    print(f"{len(rows):,} polls · {len(ids)} spaces · {len(clusters)} clusters")
    print(f"{span} (local)")
    if total_obs:
        print(f"{stale_obs/total_obs*100:.1f}% of observations were stale "
              f"(no sensor transition for over a day)"
              + (" — excluded" if a.exclude_stale else " — included; use --exclude-stale to drop"))
    print()

    if a.cluster:
        c = a.cluster
        if c not in clusters:
            sys.exit(f"Unknown cluster. Available:\n  " + "\n  ".join(clusters))
        n_spaces = len(idx[c])
        print(f"{c} — {n_spaces} sensored spaces")
        print("MEAN FREE   (· = fewer than %d polls)" % a.min_polls)
        print("     " + "".join(f"{h%12 or 12}{'a' if h<12 else 'p':<3}" for h in hours))
        for d in range(7):
            cells = []
            for h in hours:
                n, s, z = agg.get((c, d, h), [0, 0, 0])
                cells.append(f"{s/n:4.1f}" if n >= a.min_polls else "   ·")
            print(f"{DOW[d]:<5}" + "".join(cells))
        print("\nPOLLS PER CELL")
        print("     " + "".join(f"{h%12 or 12}{'a' if h<12 else 'p':<3}" for h in hours))
        for d in range(7):
            cells = []
            for h in hours:
                n, _, _ = agg.get((c, d, h), [0, 0, 0])
                cells.append(f"{n:4d}" if n else "   ·")
            print(f"{DOW[d]:<5}" + "".join(cells))
    else:
        # Weekday daytime ranking: where should you drive first?
        print("WEEKDAYS, 8am-5pm — ranked by how many spaces are typically free")
        print(f"{'CLUSTER':<22}{'SPACES':>7}{'MEAN FREE':>11}{'% FREE':>8}{'EMPTY':>7}{'POLLS':>7}")
        print("-" * 62)
        out = []
        for c in clusters:
            n = s = z = 0
            for d in range(5):
                for h in range(8, 17):
                    cn, cs, cz = agg.get((c, d, h), [0, 0, 0])
                    n += cn; s += cs; z += cz
            if n:
                out.append((s/n, c, len(idx[c]), s/n/max(1, len(idx[c]))*100, z/n*100, n))
        for mean, c, ns, pct, zero, n in sorted(out, reverse=True):
            print(f"{c:<22}{ns:>7}{mean:>11.1f}{pct:>7.0f}%{zero:>6.0f}%{n:>7}")
        print("\n'EMPTY' = share of polls with not one space free on that cluster.")
        if max((o[5] for o in out), default=0) < 20:
            print("\nToo few polls to mean anything yet — this is a plumbing check, not a finding.")

    if a.json:
        def centroid(c):
            ps = [meta[ids[i]]["latlng"] for i in idx[c] if meta.get(ids[i], {}).get("latlng")]
            if not ps:
                return None
            return [sum(float(q["latitude"]) for q in ps) / len(ps),
                    sum(float(q["longitude"]) for q in ps) / len(ps)]
        payload = {
            "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "span": [rows[0][0].isoformat(), rows[-1][0].isoformat()],
            "n_polls": len(rows),
            "stale_share": round(stale_obs / total_obs, 4) if total_obs else 0,
            "days_covered": len({r[0].date().isoformat() for r in rows}),
            "window_start": h0,
            "window_end": h1,
            "clusters": {c: {"n_spaces": len(idx[c]),
                             "spaces": [ids[i] for i in idx[c]],
                             "centroid": centroid(c),
                             "blockfaces": sorted({meta.get(ids[i], {}).get("blockface", "?")
                                                   for i in idx[c]})}
                         for c in clusters},
            "cells": {f"{c}|{d}|{h}": [v[0], v[1], v[2]]
                      for (c, d, h), v in agg.items()},
        }
        json.dump(payload, open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
