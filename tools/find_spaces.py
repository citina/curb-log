#!/usr/bin/env python3
"""Find LADOT metered space IDs for a block, by street name or by map pin.

  ./find_spaces.py --street "WESTWOOD BLVD"
  ./find_spaces.py --street "700 HOPE ST"
  ./find_spaces.py --near 34.0625,-118.4450 --radius 150

Writes the matching SpaceIDs to spaceids.txt for fetch_history.py.
Source: LADOT Metered Parking Inventory & Policies (s49e-q6j2).
"""
import argparse, json, sys, urllib.parse, urllib.request
from collections import defaultdict

INVENTORY = "https://data.lacity.org/resource/s49e-q6j2.json"
OCCUPANCY = "https://data.lacity.org/resource/e7h6-4a3e.json"


def soql(url, params):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{q}", timeout=60) as r:
        return json.load(r)


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--street", help="substring of the block face, e.g. 'WESTWOOD BLVD'")
    g.add_argument("--near", help="lat,lon of a point on your block")
    p.add_argument("--radius", type=int, default=150, help="metres, with --near (default 150)")
    p.add_argument("--out", default="spaceids.txt")
    a = p.parse_args()

    if a.street:
        where = f"upper(blockface) like '%{a.street.upper()}%'"
    else:
        lat, lon = [x.strip() for x in a.near.split(",")]
        where = f"within_circle(latlng, {lat}, {lon}, {a.radius})"

    rows = soql(INVENTORY, {"$where": where, "$limit": 5000})
    if not rows:
        sys.exit("No metered spaces matched. Try a shorter street string, or --near with a bigger --radius.")

    # Which of these actually report occupancy? Only sensored spaces appear in the live feed.
    ids = [r["spaceid"] for r in rows]
    sensored = set()
    for i in range(0, len(ids), 200):
        chunk = ",".join("'%s'" % s for s in ids[i:i + 200])
        for row in soql(OCCUPANCY, {"$where": f"spaceid in ({chunk})", "$limit": 5000}):
            sensored.add(row["spaceid"])

    blocks = defaultdict(list)
    for r in rows:
        blocks[r.get("blockface", "?")].append(r)

    print(f"{len(rows)} metered spaces, {len(sensored)} with occupancy sensors\n")
    for face, rs in sorted(blocks.items()):
        n_sens = sum(1 for r in rs if r["spaceid"] in sensored)
        rate = rs[0].get("raterange", "?")
        limit = rs[0].get("timelimit", "?")
        flag = "" if n_sens else "   <-- NO SENSORS, no history available"
        print(f"{face:<28} {len(rs):>3} spaces  {n_sens:>3} sensored  {rate:>7}  {limit:<5}{flag}")
        print(f"{'':<28} {' '.join(sorted(r['spaceid'] for r in rs))}\n")

    keep = sorted(sensored)
    with open(a.out, "w") as f:
        f.write("\n".join(keep) + "\n")
    print(f"Wrote {len(keep)} sensored SpaceIDs to {a.out}")


if __name__ == "__main__":
    main()
