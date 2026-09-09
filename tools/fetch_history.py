#!/usr/bin/env python3
"""Stream LADOT's monthly sensor archives and keep only your block's spaces.

  ./fetch_history.py --ids spaceids.txt --months 2025-09,2025-10,2026-02
  ./fetch_history.py --ids spaceids.txt --last 6
  ./fetch_history.py --list

Each monthly file is 200-300MB. This streams them and writes only matching
rows to disk, so a year of one block costs a few MB, not 3GB.
Source: LADOT Parking Meter Occupancy - Archive (cj8s-ivry).
"""
import argparse, json, re, sys, urllib.parse, urllib.request

VIEW = "cj8s-ivry"
META = f"https://data.lacity.org/api/views/{VIEW}.json"
FILE = f"https://data.lacity.org/api/views/{VIEW}/files/{{asset}}?download=true&filename={{name}}"
HEADER = "SpaceID,EventTime_Local,EventTime_UTC,OccupancyState\n"


def attachments():
    """month 'YYYY-MM' -> (assetId, filename), newest last."""
    with urllib.request.urlopen(META, timeout=60) as r:
        meta = json.load(r)
    out = {}
    for a in meta.get("metadata", {}).get("attachments", []) or []:
        name = a.get("name", "")
        m = re.search(r"(\d{4})_(\d{2})", name)
        if m:
            out[f"{m.group(1)}-{m.group(2)}"] = (a.get("assetId") or a.get("blobId"), name)
    return dict(sorted(out.items()))


def stream_month(month, asset, name, ids, fh):
    url = FILE.format(asset=asset, name=urllib.parse.quote(name))
    kept = seen = 0
    with urllib.request.urlopen(url, timeout=120) as r:
        first = True
        for raw in r:
            if first:                       # skip the CSV header
                first = False
                continue
            seen += 1
            # rows look like: "CB446","6/1/2026 12:00:00 AM","...","VACANT"
            line = raw.decode("utf-8", "replace")
            sid = line[1:line.find('"', 1)] if line.startswith('"') else line.split(",", 1)[0]
            if sid in ids:
                fh.write(line)
                kept += 1
            if seen % 1_000_000 == 0:
                print(f"    {month}: {seen//1_000_000}M rows scanned, {kept} kept", file=sys.stderr)
    return kept, seen


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ids", help="file of SpaceIDs, one per line (from find_spaces.py)")
    p.add_argument("--months", help="comma-separated YYYY-MM")
    p.add_argument("--last", type=int, help="the N most recent months available")
    p.add_argument("--out", default="occupancy_events.csv")
    p.add_argument("--list", action="store_true", help="show which months are published")
    a = p.parse_args()

    avail = attachments()
    if a.list:
        print("Published months:", ", ".join(avail))
        return
    if not a.ids:
        sys.exit("--ids is required (run find_spaces.py first)")

    ids = {ln.strip() for ln in open(a.ids) if ln.strip()}
    if a.last:
        months = list(avail)[-a.last:]
    elif a.months:
        months = [m.strip() for m in a.months.split(",")]
    else:
        sys.exit("Pass --months or --last")

    missing = [m for m in months if m not in avail]
    if missing:
        sys.exit(f"Not published: {', '.join(missing)}\nAvailable: {', '.join(avail)}")

    print(f"{len(ids)} spaces x {len(months)} months -> {a.out}")
    total = 0
    with open(a.out, "w") as fh:
        fh.write(HEADER)
        for m in months:
            asset, name = avail[m]
            print(f"  {m} ...", file=sys.stderr)
            kept, seen = stream_month(m, asset, name, ids, fh)
            total += kept
            print(f"  {m}: {kept:,} events kept of {seen:,}", file=sys.stderr)
    print(f"\n{total:,} events written to {a.out}")


if __name__ == "__main__":
    main()
