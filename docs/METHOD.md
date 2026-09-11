# How free spots are calculated

The method behind every number on [Curb Log](https://citina.github.io/curb-log/).
Plain language first, then the detail.

## Reading the numbers

**"15.4 free"** in a cell (say Vermont, Tuesday, 10:00–10:30, summer) means
that across that half hour, on the Tuesdays measured, 15.4 of the stretch's 44
sensored spaces were vacant on average. It is an average over time, not a count
at one moment: if 20 spaces were free for the first ten minutes and 13 for the
last twenty, the half hour averages 15.3.

**"None free 12% of the time"** means that of all the seconds in that half hour,
on those days, 12% had not one space free. Read it as the chance of arriving at a
random moment in that half hour and finding nothing.

**"7 days"** is how many days sit behind the cell: seven Tuesdays. One day is an
anecdote, two or three are indicative, and the average firms up from there.

The colour is the share of the stretch that was free, so the two stretches
(44 spaces and 11) read on the same scale.

## Where the data comes from

Every metered space on these blocks has a sensor in the pavement, run by LADOT,
which publishes two feeds on data.lacity.org:

- the **live feed**, each space's current state, fresh to the second;
- the **archive**, a monthly log of every change, about two months late
  (September's arrives in early November).

The city logs an event only when a space changes state, vacant to occupied or
back. So between two events nothing changed, and **the status of every space is
known at every minute**, to the second in fact. The grid is an exact average
over that complete record, not a sample of it.

Until a month's archive arrives, the page fills in from our own check of the
live feed every five minutes, weekdays 8:00 am–4:30 pm. When the archive covers
a day, it replaces those checks.

## Summer is not term

The sensors went in on 12 May 2026, so the only history before term is summer.
On these exact spaces midday vacancy ran about 49% in summer and 6% once classes
began on 24 August. Summer and term are therefore never averaged together: the
page shows one at a time, and "usually" in the live panel always means the
current term.

## Days left out

USC holidays and non-teaching days aren't a normal day at these curbs, so they
are left out of every pattern (weekdays only; the grid has no weekends):

| Days | What |
|---|---|
| 25 May | Memorial Day |
| 19 Jun | Juneteenth |
| 3 Jul | Independence Day (observed) |
| 7 Sep | Labor Day |
| 8–9 Oct | Fall recess |
| 11 Nov | Veterans Day |
| 25–27 Nov | Thanksgiving |
| 7–8 Dec | Study days |
| 9–16 Dec | Final exams |
| 17 Dec – 8 Jan | Winter recess (spring classes begin 11 Jan 2027) |

Term dates are from [USC's academic calendar](https://usc.edu/academic-calendar/).
The list lives in `NOT_NORMAL` at the top of `tools/build_data.py`.

---

## The detail

### The sweep

A *stretch* is a group of neighbouring spaces you'd drive as one: the 44 on
Vermont between 36th and 37th Streets, and the 11 on 36th Street west of Vermont.
For each, `tools/build_data.py` merges all its spaces' events in time order and
walks through them, keeping a running count of spaces **known** and spaces
**vacant**. Each stretch of time in which nothing changes is split at the
half-hour boundaries and added to its cell, day by day, as four sums:

| Sum | What is added |
|---|---|
| observed seconds | the duration |
| vacant space-seconds | vacant spaces × duration |
| known space-seconds | known spaces × duration |
| empty seconds | the duration, if no known space is vacant |

Then, for each weekday and half hour:

- **share free** = vacant space-seconds ÷ known space-seconds
- **mean spaces free** = share free × spaces in the stretch
- **none free** = empty seconds ÷ observed seconds

### Known and unknown

A space is unknown before its first event, and after **72 hours** without one.
Otherwise its last reported state stands.

- **Why divide by known space-seconds, not by time.** A space we can't see is
  not a taken one. Dividing by time would silently count every unseen space as
  occupied, which is exactly the flaw fixed on 11 September (below).
- **Why 72 hours.** Silence usually just means nothing changed: a space can sit
  vacant from Friday evening to Monday, and that is real, known state. But a dead
  or stuck sensor also goes silent while its last word stands forever. In summer
  two did, both on the 3601 Vermont block: C127 (15 events in seven weeks, and
  still "occupied" in every September check) and C145 (silent from 30 May to the
  end of June). Seventy-two hours keeps a whole weekend and still drops a stuck
  sensor after three days; 96 hours or a week give nearly the same numbers.
- **At least 80% known.** A stretch of time counts only while at least 80% of the
  stretch's sensors are known: 9 of 11 on 36th Street, 36 of 44 on Vermont. Below
  that, a few sensors would be standing in for the whole block. In the summer
  data this removes only 12 May, installation day, when the sensors came online
  through the morning.
- **One consequence.** With 80–99% of sensors known, "none free" means no *known*
  space was free; one we couldn't see might have been. It can only overstate
  "none free", and only slightly.

### Our own checks

The live feed gives each space's current state, not a log of changes, so our
checks are snapshots. Each is held forward until the next one, for at most 10
minutes, so a missed check becomes unobserved time rather than being papered
over. A state LADOT marks as over 24 hours old, or a missing one, counts as
unknown. (The 72-hour rule can't apply: a snapshot doesn't say how far past 24
hours a state is. About 2% of checked states are affected, and the archive
replaces the checks anyway.) The 80% rule and the days left out apply to checks
too. Why checks are stored as snapshots rather than as a log of changes is in
the README.

### What's stored

Each cell in `docs/data.json` is

```
[observed_seconds, vacant_space_seconds, empty_seconds, days, known_space_seconds]
```

as `cell_format` says. Mean free = `cell[1] / cell[4] × n_spaces`; none free =
`cell[2] / cell[0]`. The known field comes last so a page cached from before it
existed still reads the first four. `stale_hours`, `min_known` and
`excluded_days` record the rules the file was built with.

`tools/archive_cells.json` keeps the archive's sums per extract file and per
day, stamped with the grid (window and cell length) and the method (stale hours,
minimum known share). Holidays and periods are applied when the days are summed,
so changing either needs no recompute. Changing the grid or the method does, and
the build stops with a message rather than mix two.

### What changed on 11 September 2026

Before then, mean free was vacant space-seconds ÷ *time*, a sensor was dropped
after 24 hours of silence, and holidays counted as ordinary days. Dropped
sensors were therefore counted as occupied. On Memorial Day the log knew every
space all day (most had sat vacant since the weekend), but after 24 hours 98% had
dropped out, and Vermont that Monday read about one free. The stuck sensors
pulled Vermont down every day.

Rebuilt on the same data: summer Tuesday 10:00 on Vermont went from 13.7 to
15.4 free; summer Monday mornings no longer show "none free 14% of the time"
(that was all Memorial Day); 36th Street moved by at most 0.4 anywhere; the fall
grid by at most 0.8, with "none free" unchanged.
