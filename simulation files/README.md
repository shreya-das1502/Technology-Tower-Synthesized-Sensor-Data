# Person 3 — Simulation Engine

This is a complete, tested Person 3 deliverable: `simulator.py`, adjustable
speed, and Person 1's REAL data files. Everything below is written so you
can run it even if you've never used the command line for a project like
this before.

**v2 update:** this now uses Person 1's actual delivered files (rooms.csv,
timetable.csv, break_schedule.csv, sensor_rules.json, weather_baseline.json)
and implements their real rules — occupancy ramp-up/decay, weather-driven
temperature/humidity drift, and CO2 accumulation with memory — not the
simplified placeholder logic from the first draft.

## What's in this folder

| File | What it is |
|---|---|
| `simulator.py` | The simulator itself. This is the deliverable. Read the `ASSUMPTIONS` section at the bottom of the file — it documents every judgment call made where Person 1's rules were descriptive rather than an exact formula. |
| `rooms.csv` | Person 1's real room list (46 rooms, room type, capacity, sensors present). |
| `timetable.csv` | Person 1's real weekly class/lab/research schedule. |
| `break_schedule.csv` | Person 1's real background-occupancy rules for non-class hours (lunch, night-slip study, research flexible hours, building-closed hours, etc). |
| `sensor_rules.json` | Person 1's real rules for Occupancy, Temperature, Humidity, AirQuality (CO2), Energy, and Light. |
| `weather_baseline.json` | Person 1's real Vellore seasonal weather data, used to drive outdoor-influenced readings. |
| `mock_server.py` | A tiny fake version of Person 2's API, so you can test real network requests before their endpoint exists. |
| `readings_log.csv` | Created automatically when you run in `--mock` mode — this is where readings get saved instead of being sent over the network. |

## Step 1 — Open a terminal in this folder

Mac/Linux: open Terminal, then `cd` into this folder.
Windows: open Command Prompt or PowerShell, then `cd` into this folder.

## Step 2 — Install the one dependency you need

```
pip install requests
```

(You only need `flask` too if you want to try `mock_server.py` — see Step 5.)

## Step 3 — Run your first simulation (no network needed)

```
python3 simulator.py --mock
```

What happens:
- It reads all five real data files and simulates **Monday** by default
  (change with `--day Tue`, `--day Wed`, etc — matches the `day` column in
  timetable.csv, which uses `Mon`/`Tue`/`Wed`/`Thu`/`Fri`/`Sat`/`Sun`).
- It "fast-forwards" through the simulated day from 07:30 to 01:30 (the
  building's open hours per `break_schedule.csv`), in steps of 5 simulated
  minutes, sleeping only 0.5 real seconds between steps.
- For each of the 46 rooms, at each simulated timestamp, it works out
  occupancy (ramping in before class starts, holding steady, decaying after
  class ends, or falling back to break-schedule baselines like night-slip
  study or research-lab flexible hours), then generates a reading for every
  sensor that room actually has (per `sensors_present` in rooms.csv).
- Every reading gets written to `readings_log.csv` instead of being sent
  anywhere, because `--mock` was passed.
- You'll see live progress printed to the screen, e.g.:
  `[sim 09:05] sent 6550 readings so far (0 failed)`

**What to check when you look at the output:** pick one classroom's
`Temperature` and `AirQuality` (CO2) rows during one of its scheduled
sessions — both should climb as the room fills, hold near their peak while
full, and CO2 in particular should NOT reset to baseline the instant class
ends (it decays gradually via ventilation). That gradual, stateful decay is
the main thing that makes this look like a real sensor feed instead of
random numbers.

## Step 4 — Open `readings_log.csv` and check it makes sense

Open it in Excel/Sheets or just `cat` it. Look at one room's `temperature`
or `co2` rows over time — you should see the values climb when
`simulated_occupancy` is high and drop back to a baseline when it's 0. That
correlation is the whole point of the simulator (not random noise).

## Step 5 (optional) — Test the real network path before Person 2 is ready

In one terminal:
```
pip install flask
python3 mock_server.py
```
This starts a fake API on `http://localhost:5000/readings`.

In a second terminal, run the simulator WITHOUT `--mock`, pointing at that
fake API (this is the default endpoint, so you don't even need to specify it):
```
python3 simulator.py
```
You'll see the mock server print how many readings it received. This proves
your simulator can talk over real HTTP — so when Person 2 hands you the real
AWS URL, all you change is one flag.

## Step 6 — Swap in the real endpoint once Person 2 shares it

```
python3 simulator.py --endpoint https://THEIR-REAL-API-URL/readings
```

## Step 7 — Simulating a different day

```
python3 simulator.py --mock --day Wed
```
Wednesday is special per `break_schedule.csv` (`wed_short_day`): no theory
classes after 11am, so you'll see classrooms empty out earlier than other
weekdays. Try `--day Sat` or `--day Sun` too — only research labs run then.

## Adjusting the demo speed

Two knobs control the fast-forward:
- `--step-minutes` — how many SIMULATED minutes pass per loop (default 5)
- `--sleep-seconds` — how many REAL seconds pass per loop (default 0.5)

Examples:
```
# Faster demo (whole day in under a minute)
python3 simulator.py --mock --step-minutes 10 --sleep-seconds 0.2

# Real-time mode, for long soak testing
python3 simulator.py --mock --step-minutes 1 --sleep-seconds 60
```
The tool prints an estimated real runtime up front so you know what you're
about to kick off.

## Other useful flags

```
python3 simulator.py --help
```
shows all options, including `--day` (which day of the timetable to run),
`--start` / `--end` (simulated window, default 07:00 to 02:00 next day), and
`--mock-output` (where mock readings get saved).

## Common issues

- **"No timetable rows found for day='Monday'"** — check the `day` column
  in your timetable.csv actually says "Monday" (case doesn't matter, but
  spelling does).
- **Connection refused when not using `--mock`** — nothing is listening at
  the endpoint yet. Either start `mock_server.py` first, or add `--mock`
  back until Person 2's real API is live.
- **Every reading looks identical** — check `sensor_rules.json` has an
  entry for that room's `room_type`; unrecognized room types fall back to
  the `"default"` rules, which is expected behavior, not a bug.
