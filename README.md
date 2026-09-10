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
./find_spaces.py --near 34.0206,-118.2890 --radius 800     # which spaces, and which are sensored
./fetch_history.py --ids sensored_ids.txt --months 2026-08 # stream a monthly archive, keep only ours
./build_data.py --report                                   # the page's data; grids in the terminal
./map_spaces.py --highlight "VERMONT AVE 36xx,36TH ST 11xx" # coverage map
./poll_live.py --ids sensored_ids.txt --collector laptop   # one snapshot
./install_poller.sh                                        # laptop poller (5 min) + publisher (30 min)
./publish.py                                               # what the publisher runs
```

### How "spaces free" is computed

The archive is an event log: each row says a space became VACANT or OCCUPIED at
an exact second, and between events its state is known and constant. For each
cluster, `build_data.py` sweeps the merged events in time order keeping a running
count of vacant spaces, splits every stretch of constant state at 30-minute cell
boundaries, and credits each cell with vacant space-seconds, observed seconds,
and seconds with none free. So a cell's

- **mean spaces free** = vacant space-seconds / observed seconds — the exact
  average across that half hour, not an estimate from samples;
- **none free** = seconds with zero free / observed seconds — the chance that
  arriving at a random moment in that half hour finds nothing.

Against the earlier 15-minute sampling the exact figures differ by 0.28 spaces
on average (80 summer hour-cells) — close, but sampling gives a half-hour cell
only two readings a day, which is why the exact method matters at this
resolution. A sensor silent over 24 hours drops out of the count.

Polls are snapshots, not events, so each is held forward until the next one,
capped at 10 minutes: a gap becomes unobserved time rather than being papered
over. Wherever the archive covers a day, it is used and polls for that day are
ignored.

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

### Collection

**The laptop is the real collector.** `install_poller.sh` installs two launchd
jobs: the poller (every 5 minutes, weekdays 8am-5pm Los Angeles, into
`tools/data/laptop/`) and the publisher (`publish.py`, every 30 minutes), which
pulls, rebuilds `docs/data.json`, and pushes. It is the only thing that rewrites
the page's data; commits are pathspec-limited so nothing else in the working
copy is swept up, and `data_through` is stamped from the newest data rather than
the clock, so a rebuild with nothing new produces no commit.

`.github/workflows/poll.yml` also polls on a 5-minute cron into `tools/data/ci/`,
but treat it as a bonus: **GitHub fired that schedule three times in the first
nineteen hours.** Scheduled workflows are documented as best-effort and are
throttled hard on new repositories. Manual (`workflow_dispatch`) runs are
reliable; schedules are not a clock.

Polling stops while the Mac sleeps, and that missingness is not random — it
tracks the working day. Every cell therefore carries the number of days behind
it, and unobserved time is shown as unmeasured, never as quiet. None of this is
permanent: LADOT's archive backfills every day exactly, about two months later.

### Periods are never blended

`build_data.py` combines the archive and the polls into one grid of weekday x
half-hour cells from 8am to 4pm, segmented by period:

| Period | From | Source |
|---|---|---|
| Summer 2026 | 12 May (sensors installed) – 23 Aug | archive |
| Fall 2026 term | 24 Aug (classes began) – now | polls, then archive as it publishes |

They are aggregated separately and never averaged together. On these exact
spaces midday vacancy ran ~49% in summer and ~6% in term; a blended figure is
worse than either. The page shows one period at a time and labels summer as a
contrast, not a forecast.

The archive contribution is cached per extract file in `tools/archive_cells.json`,
so a run holding only some extracts (a new month arriving alone) recomputes what
it has and keeps the rest. When a month publishes: `fetch_history.py` it into
`tools/usc_YYYY_MM.csv`, and the next publisher run folds it in.

Validation of polling against the archive needs *overlapping* days. Polling began
9 September, so the first overlap arrives with the September file (~early
November); August's file cannot validate anything.

## Caveats found the hard way

- **A launchd job that exits 78 with an empty log couldn't open its log file.**
  The publisher failed this way twice, and the cause was self-inflicted: its log
  had been created from a sandboxed shell, which tags files
  `com.apple.provenance`, and launchd could not open it for the job. Logs launchd
  creates itself carry `com.apple.macl` and work; deleting the file fixed it at
  once. An earlier diagnosis blamed `/bin/bash` lacking Desktop access and ported
  the publisher to Python — that was wrong, though the port is harmless. Never
  pre-create or truncate a job's log by hand.
- **A cron is not a clock on GitHub.** The 5-minute schedule fired three times in
  nineteen hours; the laptop, dismissed as redundant, had been doing the work.
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
