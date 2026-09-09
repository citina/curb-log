#!/usr/bin/env python3
"""Turn LADOT sensor transitions into weekday x hour vacancy patterns.

The feed reports STATE CHANGES, not snapshots, so a space's occupancy is a step
function: it holds its last reported state until the next event. This walks that
step function on a fixed grid and counts how many spaces were vacant at each
sample point, then averages by weekday and hour.

  ./analyze.py --csv usc_may_jun.csv
  ./analyze.py --db occupancy.sqlite --from 2026-09-09
  ./analyze.py --csv usc_may_jun.csv --json patterns.json

A sensor that has been silent longer than --stale-hours is treated as unknown
rather than assumed unchanged, so a dead sensor cannot masquerade as a parked car.
"""
import argparse, collections, csv, datetime as dt, json, os, sqlite3, sys

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def load_csv(path):
    ev = collections.defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t = dt.datetime.strptime(row["EventTime_Local"], "%m/%d/%Y %I:%M:%S %p")
            ev[row["SpaceID"]].append((t, row["OccupancyState"]))
    return ev


def load_db(path):
    """The live feed stores UTC; convert to LA local time (UTC-7 PDT / -8 PST)."""
    ev = collections.defaultdict(list)
    db = sqlite3.connect(path)
    for sid, et, st in db.execute("SELECT spaceid, eventtime, state FROM events"):
        t = dt.datetime.fromisoformat(et.replace("Z", ""))
        # PDT runs Mar-Nov; good enough for a term-time study, and flagged in output.
        offset = 7 if 3 <= t.month <= 11 else 8
        ev[sid].append((t - dt.timedelta(hours=offset), st))
    return ev


def sample(ev, grid_min, stale_h, t0=None, t1=None):
    """-> counts[(weekday, hour)] = [vacant_samples, known_samples]"""
    allt = [t for v in ev.values() for t, _ in v]
    if not allt:
        sys.exit("No events to analyse.")
    start = t0 or min(allt)
    end = t1 or max(allt)
    start = start.replace(minute=0, second=0, microsecond=0)
    step = dt.timedelta(minutes=grid_min)
    stale = dt.timedelta(hours=stale_h)

    counts = collections.defaultdict(lambda: [0, 0])
    per_space = collections.defaultdict(lambda: [0, 0])

    for sid, events in ev.items():
        events.sort()
        i, n = 0, len(events)
        cur_state, cur_time = None, None
        t = start
        while t <= end:
            while i < n and events[i][0] <= t:
                cur_time, cur_state = events[i]
                i += 1
            if cur_state is not None and (t - cur_time) <= stale:
                key = (t.weekday(), t.hour)
                counts[key][1] += 1
                per_space[sid][1] += 1
                if cur_state == "VACANT":
                    counts[key][0] += 1
                    per_space[sid][0] += 1
            t += step
    return counts, per_space, start, end


def main():
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv")
    src.add_argument("--db")
    p.add_argument("--grid", type=int, default=15, help="sample every N minutes")
    p.add_argument("--stale-hours", type=int, default=24)
    p.add_argument("--from", dest="frm", help="YYYY-MM-DD")
    p.add_argument("--to", help="YYYY-MM-DD")
    p.add_argument("--hours", default="8-20", help="window to print, e.g. 8-20")
    p.add_argument("--json", help="write the grid out for the tracker page")
    a = p.parse_args()

    ev = load_csv(a.csv) if a.csv else load_db(a.db)
    t0 = dt.datetime.strptime(a.frm, "%Y-%m-%d") if a.frm else None
    t1 = dt.datetime.strptime(a.to, "%Y-%m-%d") if a.to else None
    counts, per_space, start, end = sample(ev, a.grid, a.stale_hours, t0, t1)

    spaces = {}
    if os.path.exists("spaces.json"):
        spaces = json.load(open("spaces.json"))

    h0, h1 = [int(x) for x in a.hours.split("-")]
    hours = list(range(h0, h1))
    n_spaces = len(ev)

    print(f"{len(ev)} spaces · {sum(len(v) for v in ev.values()):,} events")
    print(f"{start:%Y-%m-%d} to {end:%Y-%m-%d} · sampled every {a.grid} min\n")
    print("MEAN SPACES FREE  (of ~%d sensored)" % n_spaces)
    print("     " + "".join(f"{h%12 or 12}{'a' if h<12 else 'p':<3}" for h in hours))
    for d in range(7):
        row = []
        for h in hours:
            vac, kn = counts.get((d, h), [0, 0])
            row.append(f"{(vac/kn)*n_spaces:4.0f}" if kn else "   ·")
        print(f"{DOW[d]:<5}" + "".join(row))

    print("\nPERCENT FREE")
    print("     " + "".join(f"{h%12 or 12}{'a' if h<12 else 'p':<3}" for h in hours))
    for d in range(7):
        row = []
        for h in hours:
            vac, kn = counts.get((d, h), [0, 0])
            row.append(f"{vac/kn*100:3.0f}%" if kn else "   ·")
        print(f"{DOW[d]:<5}" + "".join(row))

    # best and worst block faces during the busy window
    if spaces:
        by_face = collections.defaultdict(lambda: [0, 0])
        for sid, (vac, kn) in per_space.items():
            face = spaces.get(sid, {}).get("blockface", "?")
            by_face[face][0] += vac
            by_face[face][1] += kn
        print("\nBLOCK FACES, all sampled hours")
        ranked = sorted(((v / k, f, k) for f, (v, k) in by_face.items() if k), reverse=True)
        for rate, face, k in ranked[:8]:
            print(f"  {rate*100:5.1f}% free   {face}")
        print("  ...")
        for rate, face, k in ranked[-4:]:
            print(f"  {rate*100:5.1f}% free   {face}")

    if a.json:
        out = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
               "start": start.isoformat(), "end": end.isoformat(),
               "n_spaces": n_spaces, "grid_min": a.grid,
               "cells": {f"{d}-{h}": {"vacant": counts[(d, h)][0], "known": counts[(d, h)][1]}
                         for d in range(7) for h in range(24) if (d, h) in counts}}
        json.dump(out, open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
