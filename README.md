# Curb Log — USC street parking study

Finding out when and where street parking is available within a 10-minute walk
of the USC Department of Public Safety, using LADOT's open sensor data rather
than manual observation.

## Data sources (data.lacity.org)

| Dataset | What it is |
|---|---|
| `e7h6-4a3e` | **Live** occupancy — last known VACANT/OCCUPIED per space, fresh to the second |
| `cj8s-ivry` | Archive — monthly CSVs of sensor transitions, published ~2 months in arrears |
| `s49e-q6j2` | Inventory — space ID, block face, coordinates, rate, time limit |

`epux-nymu` is only a meter location map despite the name; it is not live.

**The USC gap:** USC's spaces use a bare `C` prefix and are absent from the
archive before mid-May 2026. April has zero USC rows, May has 19 days, June is
complete. So the archive holds only finals week and summer for USC — no
term-time history exists. That is why `poll_live.py` exists.

## Tools

```
./find_spaces.py --near 34.0206,-118.2890 --radius 800    # which spaces, and which are sensored
./fetch_history.py --ids sensored_ids.txt --last 2        # stream monthly archives, keep only ours
./poll_live.py --ids sensored_ids.txt --db occupancy.sqlite    # one poll
./install_poller.sh                                       # run that every 10 min via launchd
./analyze.py --db occupancy.sqlite                        # weekday x hour vacancy
```

`analyze.py` reconstructs each sensor's state as a step function — the feed
reports transitions, not snapshots — and samples it on a fixed grid. Sensors
silent longer than `--stale-hours` are treated as unknown rather than assumed
unchanged. Median gap between events is 6 minutes and only 0.53% exceed 24h, so
the default cutoff barely moves results (Tue 11am: 33% at 24h vs 33% at 30 days).

## Caveats found the hard way

- **Summer data does not transfer.** 3601 Vermont read 49% free at midday in
  June; on a September teaching day it read 6%. Only term-time data can answer
  the question.
- **LADOT block faces are not walkable units.** Vermont between 36th and 38th is
  six separate block faces (77 metered spaces, 65 sensored) that the parking app
  shows as one location. Analyse clusters, not block faces.
- `curb-log.html` is a manual tracker, now a fallback: it captures max payable
  duration and the unsensored blocks (Jefferson Blvd, most of Figueroa), neither
  of which appear in the sensor feed.
