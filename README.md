# Curb Log — USC street parking study

Finding out when street parking is available on the stretch actually walkable
from an office near USC DPS, using LADOT's open sensor data rather than manual
observation.

**Scope (confirmed on a map, 9 Sep 2026): 55 sensored spaces.**

| Cluster | Spaces | Where |
|---|---:|---|
| `VERMONT AVE 36xx` | 44 | Vermont, West 36th St down to ~37th St, both sides |
| `36TH ST 11xx` | 11 | West 36th St just west of Vermont, by the park |

Vermont 37xx sits south of 37th Place and was rejected as too far to walk, as
were the other ten metered streets in the area. Beyond this stretch the
fallback is free (unmetered) street parking, which has no sensors — so "how
often is this stretch empty" matters as much as "how many spaces are free".
`map_spaces.py` redraws the coverage map; block-face numbers are unreadable as
geography and caused a scoping mistake before the map existed.

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
./find_spaces.py --near 34.0206,-118.2890 --radius 800   # which spaces, and which are sensored
./fetch_history.py --ids sensored_ids.txt --last 2       # stream monthly archives, keep only ours
./poll_live.py --ids sensored_ids.txt --collector laptop # one snapshot
./install_poller.sh                                      # that, every 5 min, via launchd
./patterns.py                                            # weekday x hour, in the terminal
./build_data.py --out ../docs/data.json                  # the page's data, all sources
./map_spaces.py --highlight "VERMONT AVE 36xx,36TH ST 11xx"  # coverage map
./analyze.py --csv usc_may_jun.csv                       # same, for archive CSVs
```

### Why snapshots, not an event log

The feed reports each space's last transition, so storing transitions and
rebuilding a step function looks like the richer choice. Measured against the
June 2026 archive it isn't: a 10-minute poller sees only **59%** of real
transitions, and the ones it misses are short episodes, so any dwell-time
answer would be biased long. Sampling the state instead is provably adequate —
5-minute sampling recovers hourly vacancy to **0.33pp** (mean bias -0.002pp):

| cadence | max hourly error | mean bias |
|---|---|---|
| 5 min | 0.33 pp | -0.002 pp |
| 10 min | 0.72 pp | -0.027 pp |
| 15 min | 0.99 pp | -0.024 pp |
| 30 min | 2.49 pp | -0.122 pp |
| 60 min | 5.09 pp | -0.227 pp |

So the poller appends one line per poll — `polled_at_utc,states`, one character
per space — and the event log was dropped rather than shipped with a known bias.

### Two collectors

`.github/workflows/poll.yml` polls every 5 minutes on GitHub Actions and commits
to `tools/data/ci/`. The launchd job polls the same endpoint into
`tools/data/laptop/`, which is gitignored — it is supplementary coverage for
runs GitHub drops. Separate directories are load-bearing: sharing one file made
every `git pull` conflict with the laptop's in-progress writes.
`patterns.py` reads both.

Both collectors are gated to **weekdays 8am-6pm America/Los_Angeles** — the
window actually parked in. This deliberately gives up the pre-8am fill-up curve
and any weekend baseline.

Laptop polling stops while the Mac sleeps, and that missingness is **not
random** — it tracks the working day, so it thins exactly the busy hours.
That is why CI exists and why polls-per-cell is printed with every result.

### Periods are never blended

`build_data.py` combines two sources into one grid — the LADOT archive (a
complete event log, sampled every 15 min off the reconstructed step function)
and our own 5-minute snapshots — and segments them by period:

| Period | From | Source |
|---|---|---|
| Summer 2026 | 12 May (sensors installed) – 23 Aug | archive |
| Fall 2026 term | 24 Aug (classes began) – now | polls, then archive as it publishes |

They are aggregated separately and never averaged together. On these exact
spaces midday vacancy ran ~49% in summer and ~6% in term; a blended figure is
worse than either. The page shows one period at a time and labels summer as a
contrast, not a forecast.

The archive contribution is cached in `tools/archive_cells.json` (a few KB) so
CI can rebuild the page without holding the 200-300MB monthly extracts. Re-run
`build_data.py` locally with the extracts present whenever a new month is
published, and commit the refreshed cache.

## Caveats found the hard way

- **Summer data does not transfer.** 3601 Vermont read 49% free at midday in
  June; on a September teaching day it read 6%. Only term-time data can answer
  the question.
- **LADOT block faces are not decision units.** Vermont between 36th and 38th is
  six separate block faces (77 metered spaces, 65 sensored) that the parking app
  shows as one location, and that you drive as one stretch. `patterns.py`
  therefore clusters both sides of a hundred-block: Vermont 36xx is the 44
  sensored spaces across 3600/3601/3650/3651.
- `curb-log.html` is a manual tracker, now a fallback: it captures max payable
  duration and the unsensored blocks (Jefferson Blvd, most of Figueroa), neither
  of which appear in the sensor feed.
