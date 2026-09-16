# Curb Log — USC street parking study

Finding out when street parking is available on the stretch actually walkable
from an office near USC DPS, using LADOT's open sensor data rather than manual
observation.

**Scope (picked on a map, 11 Sep 2026): 76 sensored spaces in two places.**

| Place | Spaces | Where |
|---|---:|---|
| `vermont` | 65 | Vermont Ave, West 36th St down to 37th Dr, both sides |
| `36th-st` | 11 | West 36th St just west of Vermont, by the park |

**`tools/places.json` is the one definition of what is studied.** Collection is
wider: all 248 sensored spaces within 800 m of the office are polled, and the
archive extracts keep all of them too. So a place can grow or shrink without
touching the pollers, and a space added later already has its history. To
change one, pick the spaces on the page's Basis map (tap one, or drag a box
around several) and paste the block it gives you into a chat with Claude.

Places used to be LADOT hundred-blocks. That cut six sensored spaces between
37th St and 37th Pl out of the middle of the Vermont stretch, because their
block face (3700/3701) runs on south of 37th Pl, which was then out of scope.
All 21 spaces of those block faces joined Vermont on 11 Sep. Block-face numbers
are unreadable as geography, which is why places are picked on a map. Beyond
these places the fallback is free (unmetered) street parking, which has no
sensors — so "how often is this stretch empty" matters as much as "how many
spaces are free".

Polling covered only the old 44 Vermont spaces on 10–11 Sep, below the 80% of
a place that must be known for time to count, so Vermont's term grid has no
polls for those two days; the September archive (~early November) fills them
in. 9 Sep afternoon survives because polling was still wide then.

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
./fetch_history.py --ids sensored_ids.txt --months 2026-08 # stream a monthly archive, keep all 248 nearby
./build_data.py --report                                   # the page's data, for places.json; grids in the terminal
./map_spaces.py --bare --out ../docs/basemap.png --overview ../docs/basemap-overview.png --json ../docs/map.json
./poll_live.py --ids sensored_ids.txt --collector laptop   # one snapshot
./install_poller.sh                                        # laptop poller (5 min) + publisher (30 min)
./publish.py                                               # what the publisher runs
```

### How "spaces free" is computed

**[docs/METHOD.md](docs/METHOD.md) is the one full account**, plain language
first. In short: LADOT logs an event only when a space changes state, so every
space's state is known at every second, and each half-hour cell is an exact
average over that record, not a sample. Mean free = the share of *known*
sensor-time that was vacant × the spaces in the stretch, so a space we can't see
is never counted as occupied. A sensor silent for 72 hours drops out, a stretch
of time counts only while 80% of a cluster's sensors are known, and USC holidays
and non-teaching days are left out. Polls stand in, held forward at most 10
minutes, until the archive covers a day.

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

Every sensored space nearby gets a column (`tools/sensored_ids.txt`), in the
order pinned by `tools/data/space_order.txt`. That order only ever grows at the
end: an older, shorter line has no column for a newer space, which the build
reads as unknown, whereas reordering or dropping a space would shift every
column after it, so `poll_live.py` refuses to.

### Collection

Polling runs weekdays **8:00am–4:30pm Los Angeles**, the same window as the grid
(`--only-hours 8-16:30`, `--window 8-16:30`; the end is exclusive, so the last
poll of the day is at 4:25).

**GitHub polls, started from outside.** `.github/workflows/poll.yml` has no
schedule of its own: GitHub's cron fired three times in this repo's first
nineteen hours, and only three times inside the window on the first full day.
Scheduled workflows are best-effort and throttled hard on new repositories;
`workflow_dispatch` runs are not. So cron-job.org calls the dispatch API every
five minutes, and each run appends one line to `tools/data/ci/`:

| cron-job.org setting | value |
|---|---|
| URL | `https://api.github.com/repos/citina/curb-log/actions/workflows/poll.yml/dispatches` |
| Method | `POST` |
| Headers | `Accept: application/vnd.github+json` · `Authorization: Bearer <token>` · `X-GitHub-Api-Version: 2022-11-28` |
| Body | `{"ref":"main"}` |
| Schedule | every 5 minutes, hours 8–16, Monday–Friday, time zone America/Los_Angeles |
| Success | HTTP 204 |

The token is a fine-grained one limited to this repository with Actions: read and
write, and it lives only in cron-job.org. It expires on the date picked when it
was made, and polling stops when it does, so renew it before then. The dispatches
after 4:30 poll nothing (`poll_live.py` applies the exact window), but the 4:30
one still publishes the day's last half hour.

**One writer.** `tools/publisher.txt` names the only thing that rebuilds
`docs/data.json`: `laptop` or `ci`. While it says `laptop`, the laptop publisher
builds the page and CI only appends polls. When it says `ci`, the :00 and :30 poll
runs rebuild it and `publish.py` does nothing. `archive.yml` obeys the same file.
`data_through` is stamped from the newest data rather than the clock, so a
rebuild with nothing new produces no commit.

**The laptop, retired 15 September.** `install_poller.sh` installs two launchd
jobs: the poller (every 5 minutes, into `tools/data/laptop/`) and the publisher
(`publish.py`, every 30 minutes), which pulls, rebuilds `docs/data.json`, and
pushes, with pathspec-limited commits so nothing else in the working copy is
swept up. Both run only while the Mac is awake: on 10 September it took 65 of
108 five-minute polls, and on 15 September it took none — the page sat a day
stale on yesterday's data while CI held that morning complete, which is what
`publisher.txt` was flipped to `ci` to end. The criterion it had to meet first
was a full weekday of CI polls at about 12 an hour (`cut -c12-13
tools/data/ci/<day>.csv | sort | uniq -c` counts them per UTC hour; 8am–4:30pm
PDT is 15:00–23:30 UTC), which 14 September met exactly.

Nothing now depends on the Mac. To finish the teardown on it:
`launchctl bootout gui/$(id -u)/com.citina.curblog.poll` and the same for
`com.citina.curblog.publish`, then delete both plists from
`~/Library/LaunchAgents`. Until that runs, the poller keeps writing
`tools/data/laptop/` locally and `publish.py` no longer pushes it, so those
polls stay on the Mac.

**The page deploys from `.github/workflows/pages.yml`**, not GitHub's branch
build, so only a change under `docs/` publishes it; under the branch build every
5-minute poll commit rebuilt the site, past Pages' soft limit of 10 builds an
hour. Pushes made with `GITHUB_TOKEN` don't trigger other workflows, so
`poll.yml` and `archive.yml` start the deploy themselves when they change
`docs/data.json`.

Gaps in polling (a sleeping Mac, a dropped dispatch) are not random — they
track the working day. Every cell therefore carries the number of days behind
it, and unobserved time is shown as unmeasured, never as quiet. None of this is
permanent: LADOT's archive backfills every day exactly, about two months later.

### Periods are never blended

`build_data.py` combines the archive and the polls into one grid of weekday x
half-hour cells from 8am to 4:30pm, segmented by period:

| Period | From | Source |
|---|---|---|
| Summer 2026 | 12 May (sensors installed) – 23 Aug | archive |
| Fall 2026 term | 24 Aug (classes began) – now | polls, then archive as it publishes |

They are aggregated separately and never averaged together. On these exact
spaces midday vacancy ran ~49% in summer and ~6% in term; a blended figure is
worse than either. The page shows one period at a time and labels summer as a
contrast, not a forecast. USC holidays and non-teaching days are left out of
both ([list](docs/METHOD.md#days-left-out)).

The archive contribution is cached per extract file in `tools/archive_cells.json`,
so a run holding only some extracts (a new month arriving alone) recomputes what
it has and keeps the rest. `.github/workflows/archive.yml` checks daily for
newly published months, streams each into `tools/usc_YYYY_MM.csv` with
`fetch_history.py`, and commits the updated cache; the next build folds it in.

The cache is stamped with the window and slot its cells were cut to, the
method they were swept with (`--stale-hours`, `--min-known`) and the places they
were swept over. Changing any of them needs every extract in the cache present
to recompute — `build_data.py` stops with a message rather than leave columns
empty, mix two methods or credit a place with spaces it no longer has. In CI, a
push that changes `tools/places.json` starts `archive.yml`, which re-fetches the
months whose extracts aren't committed (`build_data.py --stale-extracts` names
them); a poll's rebuild that fails meanwhile still commits its snapshot.
Holidays and periods are applied when days are summed, so editing those needs
no recompute.
`usc_may_jun.csv` (12 May – 30 June, every event for all 248 sensored spaces
nearby) is committed; later months' extracts stay out of git, and
`fetch_history.py` re-streams any month.

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
  shows as one location, and that you drive as one stretch. Nor are they
  bounded by cross streets: the 3700 block face starts north of 37th Pl, so
  clustering by hundred-block silently cut six spaces out of the middle of the
  stretch. Places are therefore sets of spaces picked on a map.
