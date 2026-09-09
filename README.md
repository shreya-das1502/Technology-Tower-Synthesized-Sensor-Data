# Technology-Tower-Synthesized-Sensor-Data

Generated for the September 14–20, 2026 week (Mon–Sun), 07:30 to 01:30 the next day,
at 5-minute sampling resolution.

## Files

1. **rooms.csv** — 46 rooms from the floor plan, classified into:
   `CLASSROOM` (6), `UG_LAB` (11, slot-based teaching labs), `RESEARCH_LAB` (9, flexible-hours
   grad/research spaces), `STAFF_ROOM` (13), `CORRIDOR` (1, VOC Gallery II), `TOILET` (4),
   `ELECTRICAL_ROOM` (1), `STORE_ROOM` (1). Capacity: 70 for classrooms/large UG labs, 35 for
   smaller UG labs (area < 800 sqft), 10 for research labs, sized-down for support spaces.
   `sensors_present` lists which of the 6 sensor types apply to that room type.

2. **timetable.csv** — Built from the VIT slot-time grid you pasted:
   - Theory periods: 5 morning (08:00–12:50) + 5 afternoon (14:00–18:50), one section (70
     students) per classroom per period, capped at 3 sessions per half-day.
   - **Wednesday**: only the first 3 morning periods run (theory ends by 11:00), per your note.
   - Lab periods: 6 morning + 6 afternoon columns/day × 5 days = 60 weekly "lab slots" (matches
     the L1–L60 numbering in your grid). Each of the 11 UG labs is assigned 18 of these 60 slots
     at random, expected_occupancy = room capacity (already accounts for 2 combined sections).
   - Research labs get a flexible daily block (09:00–18:00 weekdays, lower weekend block)
     instead of fixed periods, since they aren't run off the UG slot grid.

3. **break_schedule.csv** — Lunch (12:50–14:00), Wednesday short-day, evening wind-down
   (18:50–21:15), **night-slip self-study** (21:15–01:30, classrooms/corridor only — this is why
   data collection runs to 1:30 AM), building-closed window (01:30–07:30, outside your collection
   window), plus baseline operating patterns for staff rooms, toilets, research labs, and
   service rooms (electrical/store).

4. **weather_baseline.json** — Vellore, daily condition assigned across the week to cover all
   4 requested conditions (sunny, moderate, humid, rainy), with min/max temp & humidity per day
   and an hourly diurnal fraction curve used to interpolate outdoor conditions hour-by-hour.

5. **sensor_rules.json** — Occupancy-driven rules for all 6 sensor types (Occupancy, Temperature,
   Humidity, AirQuality [CO2 proxy], Energy, Light), including entry/exit ramp timing (10 min
   before start → full 15 min after, matching your entry-window rule), AC-controlled occupied
   temperature band, CO2 accumulation/decay, per-room-type energy draw, and lux levels.

6. **sensor_readings_week.csv** — The actual simulated continuous data: **69,874 rows** = 46 rooms
   × 1,519 timestamps (7 days × ~217 timestamps/day at 5-min resolution, 07:30–01:30). Columns:
   `room_id, timestamp, day, condition, Occupancy, Temperature_C, Humidity_pct, AirQuality_ppm,
   Energy_kW, Light_lux` (only the sensor columns that apply to that room's type are populated).

## Key assumptions (flag these to your team / adjust if wrong)

- **Sampling interval: 5 minutes.** Not specified in your brief — this is a common IoT telemetry
  rate; easy to change (one constant in the generator) if you want 1-min or 15-min instead.
- **Room→course assignment is randomized**, not your real course allocation (you didn't provide
  actual section-to-room mappings, only the generic slot-time grid + constraints). The generator
  respects all stated constraints (18 lab slots/room/week, 3 theory sessions/half-day/classroom,
  1 section/theory slot, 2 sections/lab slot) but the *specific* day/room pairings are synthetic.
- **Weekend (Sat/Sun)**: no formal classes assumed; only research labs get light activity.
  Change this if your department runs Saturday classes.
- **Chemistry/postgrad labs** (210, 211, 213, 214, 215-216, 217, 221-222, 224, 235) are treated
  as flexible-hours research spaces rather than slot-timetabled UG labs — this seemed more
  realistic than forcing them onto the 50-minute UG slot grid, but merge them into UG_LAB logic
  if your architecture treats all labs identically.
