#!/usr/bin/env python3
"""
simulator.py (v2) — Person 3's deliverable, rewritten to match the REAL
files Person 1 delivered: rooms.csv, timetable.csv, break_schedule.csv,
sensor_rules.json, weather_baseline.json.

WHAT CHANGED FROM v1
---------------------
v1 used simplified placeholder rules. This version implements the actual
occupancy/sensor model Person 1 specified:
  - Occupancy RAMPS in before a session starts and DECAYS after it ends
    (not an instant on/off).
  - Between scheduled sessions, occupancy comes from break_schedule.csv's
    per-room-type baselines (e.g. corridor foot traffic, night-slip study,
    research lab flexible hours) instead of being flatly 0.
  - Temperature and Humidity drift toward outdoor weather (from
    weather_baseline.json's per-day condition + hour-by-hour diurnal
    curves) when a room is empty, and pull toward an AC-controlled band
    when occupied.
  - CO2 (AirQuality) accumulates while occupied and decays via ventilation
    while empty — it has MEMORY across time steps, it isn't recalculated
    from scratch each reading.
  - Energy draw is standby load + occupancy-driven active load, per room
    type.
  - Light follows building-open/closed hours, security night lighting, and
    occupancy.

See ASSUMPTIONS at the bottom of this file for every judgment call made
where the spec was descriptive rather than a precise formula — read that
section before you present this to your team, so you can defend the
choices or tweak them.

USAGE
------
  python3 simulator.py --mock
  python3 simulator.py --endpoint https://real-api-url/readings
  python3 simulator.py --mock --day Wed --step-minutes 10 --sleep-seconds 0.2
"""

import argparse
import csv
import json
import random
import re
import sys
import time
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    requests = None

DAY_SHORT_TO_FULL = {
    "Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday",
    "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday",
}
WEEKDAYS = {"Mon", "Tue", "Wed", "Thu", "Fri"}
WEEKEND = {"Sat", "Sun"}


# --------------------------------------------------------------------------
# 1. LOADING INPUT FILES
# --------------------------------------------------------------------------

def load_rooms(path):
    """rooms.csv -> {room_id: {name, room_type, capacity, sensors:set}}"""
    rooms = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rooms[row["room_id"]] = {
                "name": row["room_name"],
                "room_type": row["room_type"].strip(),
                "capacity": int(row["capacity"]),
                "sensors": set(s.strip() for s in row["sensors_present"].split("|")),
            }
    return rooms


def load_timetable(path):
    """timetable.csv -> {room_id: [ {day, start, end, occ, type}, ... ]}"""
    schedule = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            schedule.setdefault(row["room_id"], []).append({
                "day": row["day"],
                "start": to_minutes(row["start_time"]),
                "end": to_minutes(row["end_time"]),
                "occ": int(row["expected_occupancy"]),
                "type": row["session_type"],
            })
    return schedule


def load_break_schedule(path):
    """
    break_schedule.csv -> list of usable rows (skips rows whose start/end is
    the literal text 'varies', since those describe a concept rather than a
    fixed time window we can simulate directly).
    """
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["start_time"].strip().lower() == "varies":
                continue
            lo, hi = parse_hint_range(row["baseline_occupancy_hint"])
            if lo is None:
                continue
            rows.append({
                "name": row["period_name"],
                "day_scope": row["day_scope"],
                "start": to_minutes(row["start_time"]),
                "end": to_minutes(row["end_time"]),
                "room_types": row["applies_to_room_type"],
                "lo": lo,
                "hi": hi,
            })
    return rows


def load_rules(path):
    with open(path) as f:
        return json.load(f)


def load_weather(path):
    with open(path) as f:
        return json.load(f)


def to_minutes(hhmm):
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)


def parse_hint_range(hint):
    """'0-3' -> (0,3). '0-2, brief' -> (0,2). 'corridor spike' -> (None,None)."""
    m = re.search(r"(\d+)\s*-\s*(\d+)", hint)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# --------------------------------------------------------------------------
# 2. TIME / SCOPE MATCHING HELPERS
# --------------------------------------------------------------------------

def day_scope_matches(day_scope, day_short):
    if day_scope == "ALL":
        return True
    if day_scope == "WEEKDAY":
        return day_short in WEEKDAYS
    if day_scope == "WEEKEND":
        return day_short in WEEKEND
    if day_scope == "WED_ONLY":
        return day_short == "Wed"
    return False


def room_type_matches(applies_to, room_type):
    if applies_to == "ALL":
        return True
    return room_type in applies_to.split("|")


def in_window(minute_of_day, start, end):
    """Handles windows that cross midnight, e.g. 21:15 -> 01:30."""
    if start <= end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end


# --------------------------------------------------------------------------
# 3. OCCUPANCY MODEL (ramp-up / hold / decay / break-schedule baseline)
# --------------------------------------------------------------------------

def occupancy_rules(rules_doc):
    return rules_doc["sensors"]["Occupancy"]


def compute_occupancy(room_id, room_type, day_short, minute_of_day,
                       timetable, break_rows, occ_rule):
    ramp_before = occ_rule["entry_ramp_minutes_before_start"]
    full_after = occ_rule["full_by_minutes_after_start"]
    decay_after = occ_rule["exit_decay_minutes_after_end"]
    noise_pct = occ_rule["noise_pct"] / 100.0

    for s in timetable.get(room_id, []):
        if s["day"] != day_short:
            continue
        ramp_start = s["start"] - ramp_before
        full_time = s["start"] + full_after
        session_end = s["end"]
        decay_end = session_end + decay_after
        target = s["occ"]

        if ramp_start <= minute_of_day < full_time:
            frac = (minute_of_day - ramp_start) / (full_time - ramp_start)
            base = target * max(0.0, min(1.0, frac))
        elif full_time <= minute_of_day < session_end:
            base = target
        elif session_end <= minute_of_day < decay_end:
            frac = (minute_of_day - session_end) / (decay_end - session_end)
            base = target * (1.0 - max(0.0, min(1.0, frac)))
        else:
            continue  # not in this session's influence window

        jitter = base * noise_pct
        return max(0, round(base + random.uniform(-jitter, jitter)))

    # No active/ramping session -> fall back to break_schedule baseline
    for row in break_rows:
        if not day_scope_matches(row["day_scope"], day_short):
            continue
        if not room_type_matches(row["room_types"], room_type):
            continue
        if in_window(minute_of_day, row["start"], row["end"]):
            return random.randint(row["lo"], row["hi"])

    return 0


# --------------------------------------------------------------------------
# 4. WEATHER LOOKUP (outdoor ambient temp/humidity/condition at a given time)
# --------------------------------------------------------------------------

def outdoor_conditions(day_short, minute_of_day, weather_doc):
    day_full = DAY_SHORT_TO_FULL[day_short]
    day_entry = next((d for d in weather_doc["daily"] if d["day"] == day_full), None)
    if day_entry is None:
        day_entry = weather_doc["daily"][0]  # fallback

    hour = str((minute_of_day // 60) % 24)
    t_frac = weather_doc["diurnal_temp_fraction_by_hour"].get(hour, 0.5)
    h_frac = weather_doc["diurnal_humidity_fraction_by_hour"].get(hour, 0.5)

    temp = day_entry["temp_min_c"] + t_frac * (day_entry["temp_max_c"] - day_entry["temp_min_c"])
    humidity = day_entry["humidity_min_pct"] + h_frac * (day_entry["humidity_max_pct"] - day_entry["humidity_min_pct"])
    return temp, humidity, day_entry["condition"]


# --------------------------------------------------------------------------
# 5. SENSOR VALUE GENERATION (Temperature, Humidity, AirQuality, Energy, Light)
# --------------------------------------------------------------------------

def gen_temperature(room_id, room_type, occ, outdoor_temp, condition, rules, state, step_minutes):
    r = rules["Temperature"]
    prev = state["temp"].get(room_id, outdoor_temp)

    if occ > 0:
        heat_gain = min(occ * r["occupancy_heat_gain_c_per_person"], r["max_occupancy_heat_gain_c"])
        value = 25.0 + heat_gain  # AC target band midpoint (24-26C) + occupancy heat load
    else:
        damp = 0.3  # thermal-mass lag toward outdoor ambient
        value = prev + damp * (outdoor_temp - prev)
        value += r["condition_offset_c"].get(condition, 0.0)

    value += random.uniform(-r["noise_c"], r["noise_c"])
    state["temp"][room_id] = value
    return round(value, 2)


def gen_humidity(room_type, occ, outdoor_humidity, condition, rules):
    r = rules["Humidity"]
    base = outdoor_humidity - 5.0
    occ_effect = min(occ * r["occupancy_effect_pct_per_person"], r["max_occupancy_effect_pct"])
    value = base + occ_effect + r["condition_offset_pct"].get(condition, 0.0)
    value += random.uniform(-r["noise_pct"], r["noise_pct"])
    return round(max(0.0, min(100.0, value)), 2)


def gen_air_quality(room_id, occ, rules, state, step_minutes):
    r = rules["AirQuality"]
    prev = state["co2"].get(room_id, r["empty_room_baseline_ppm"])

    if occ > 0:
        gain = r["accumulation_ppm_per_person_per_10min"] * occ * (step_minutes / 10.0)
        value = min(prev + gain, r["max_ppm"])
    else:
        decay_frac = (r["ventilation_decay_pct_per_5min_when_unoccupied"] / 100.0) * (step_minutes / 5.0)
        value = prev - prev * decay_frac
        value = max(value, r["outdoor_baseline_ppm"])

    state["co2"][room_id] = value
    reading = value + random.uniform(-r["noise_ppm"], r["noise_ppm"])
    return round(max(r["outdoor_baseline_ppm"], reading), 1)


def gen_energy(room_type, occ, rules):
    r = rules["Energy"]
    standby = r["standby_load_kw"].get(room_type, 0.1)
    active = r["active_load_kw_per_capacity_unit"].get(room_type, 0.0) * occ
    value = standby + active
    value += value * random.uniform(-r["noise_pct"] / 100.0, r["noise_pct"] / 100.0)
    return round(value, 3)


def gen_light(room_type, occ, minute_of_day, break_rows, day_short, rules):
    r = rules["Light"]

    building_closed = any(
        row["name"] == "building_closed" and in_window(minute_of_day, row["start"], row["end"])
        for row in break_rows
    )
    if building_closed:
        return round(r["closed_hours_lux"] + random.uniform(-1, 1), 1)

    if occ > 0:
        base = r["occupied_lux"].get(room_type, 0)
    else:
        night_slip = any(
            row["name"] == "night_slip_study" and in_window(minute_of_day, row["start"], row["end"])
            for row in break_rows
        )
        if night_slip:
            base = r["security_night_lux"].get(room_type, r["security_night_lux"].get("default", 0))
        else:
            base = r["unoccupied_daytime_lux"].get(room_type, r["unoccupied_daytime_lux"].get("default", 0))

    noise = base * (r["noise_pct"] / 100.0) if base else 1.0
    value = base + random.uniform(-noise, noise)
    return round(max(0.0, value), 1)


# --------------------------------------------------------------------------
# 6. SENDING READINGS
# --------------------------------------------------------------------------

def send_reading(reading, endpoint, mock_writer, session):
    if mock_writer is not None:
        mock_writer.writerow(reading)
        return True
    try:
        resp = session.post(endpoint, json=reading, timeout=5)
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[warn] POST failed for {reading['sensor_id']}: {e}")
        return False


# --------------------------------------------------------------------------
# 7. MAIN SIMULATION LOOP
# --------------------------------------------------------------------------

def run_simulation(args):
    rooms = load_rooms(args.rooms)
    timetable = load_timetable(args.timetable)
    break_rows = load_break_schedule(args.breaks)
    rules_doc = load_rules(args.rules)
    weather_doc = load_weather(args.weather)
    occ_rule = occupancy_rules(rules_doc)

    sim_minutes = to_minutes(args.start)
    end_minutes = to_minutes(args.end)
    if end_minutes <= sim_minutes:
        end_minutes += 1440

    total_steps = (end_minutes - sim_minutes) // args.step_minutes
    est_real_seconds = total_steps * args.sleep_seconds

    print("== Simulation plan ==")
    print(f"  Day: {args.day} ({DAY_SHORT_TO_FULL.get(args.day, args.day)})")
    print(f"  Simulated window: {args.start} -> {args.end}  ({end_minutes - sim_minutes} sim minutes)")
    print(f"  Step size: {args.step_minutes} sim minutes/loop, sleeping {args.sleep_seconds}s real time/loop")
    print(f"  Total steps: {total_steps}  |  Estimated real runtime: ~{est_real_seconds:.0f}s "
          f"({est_real_seconds/60:.1f} min)")
    print(f"  Rooms: {len(rooms)}  |  Mode: "
          f"{'MOCK (local CSV)' if args.mock else 'LIVE (' + args.endpoint + ')'}")
    print("======================\n")

    mock_writer = None
    mock_file = None
    session = None
    if args.mock:
        mock_file = open(args.mock_output, "w", newline="")
        mock_writer = csv.DictWriter(
            mock_file,
            fieldnames=["sensor_id", "room_id", "sensor_type", "timestamp",
                        "value", "unit", "simulated_occupancy"],
        )
        mock_writer.writeheader()
    else:
        session = requests.Session()

    state = {"temp": {}, "co2": {}}
    base_date = datetime(2026, 1, 1)
    sent_count = 0
    fail_count = 0
    m = sim_minutes

    while m < end_minutes:
        sim_time = base_date + timedelta(minutes=m)
        timestamp_iso = sim_time.strftime("%Y-%m-%dT%H:%M:%S")
        minute_of_day = m % 1440
        outdoor_temp, outdoor_humidity, condition = outdoor_conditions(args.day, minute_of_day, weather_doc)

        for room_id, info in rooms.items():
            room_type = info["room_type"]
            occ = compute_occupancy(room_id, room_type, args.day, minute_of_day,
                                     timetable, break_rows, occ_rule)

            sensors = info["sensors"]
            values = {}
            if "Occupancy" in sensors:
                values["Occupancy"] = (occ, "person_count")
            if "Temperature" in sensors:
                values["Temperature"] = (
                    gen_temperature(room_id, room_type, occ, outdoor_temp, condition,
                                     rules_doc["sensors"], state, args.step_minutes),
                    "celsius")
            if "Humidity" in sensors:
                values["Humidity"] = (
                    gen_humidity(room_type, occ, outdoor_humidity, condition, rules_doc["sensors"]),
                    "percent_RH")
            if "AirQuality" in sensors:
                values["AirQuality"] = (
                    gen_air_quality(room_id, occ, rules_doc["sensors"], state, args.step_minutes),
                    "ppm")
            if "Energy" in sensors:
                values["Energy"] = (gen_energy(room_type, occ, rules_doc["sensors"]), "kW")
            if "Light" in sensors:
                values["Light"] = (
                    gen_light(room_type, occ, minute_of_day, break_rows, args.day, rules_doc["sensors"]),
                    "lux")

            for sensor_type, (value, unit) in values.items():
                # DynamoDB workaround: their ingest.py does json.loads() with no
                # parse_float=Decimal, so plain JSON numbers with decimals become
                # Python floats and boto3's put_item rejects those outright (500
                # error). Sending the value as a JSON STRING instead sidesteps
                # this completely on our end, no change needed on their side.
                # Pass --raw-numeric-values once their Lambda is patched to send
                # real numbers again (better for range queries downstream).
                out_value = value if args.raw_numeric_values else str(value)
                out_occ = occ if args.raw_numeric_values else str(occ)
                reading = {
                    "sensor_id": f"{room_id}_{sensor_type}",
                    "room_id": room_id,
                    "sensor_type": sensor_type,
                    "timestamp": timestamp_iso,
                    "value": out_value,
                    "unit": unit,
                    "simulated_occupancy": out_occ,
                }
                ok = send_reading(reading, args.endpoint, mock_writer, session)
                sent_count += 1 if ok else 0
                fail_count += 0 if ok else 1

        if m % (args.step_minutes * 6) < args.step_minutes:  # print roughly every ~30 sim min
            print(f"[sim {sim_time.strftime('%H:%M')}] sent {sent_count} readings so far "
                  f"({fail_count} failed)", end="\r")

        m += args.step_minutes
        time.sleep(args.sleep_seconds)

    if mock_file:
        mock_file.close()

    print(f"\n\nDone. Total readings sent: {sent_count}, failed: {fail_count}.")
    if args.mock:
        print(f"Output written to {args.mock_output}")


# --------------------------------------------------------------------------
# 8. CLI
# --------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Fast-forward IoT occupancy/sensor simulator.")
    p.add_argument("--rooms", default="rooms.csv")
    p.add_argument("--timetable", default="timetable.csv")
    p.add_argument("--breaks", default="break_schedule.csv")
    p.add_argument("--rules", default="sensor_rules.json")
    p.add_argument("--weather", default="weather_baseline.json")
    p.add_argument("--day", default="Mon", choices=list(DAY_SHORT_TO_FULL.keys()),
                    help="Which day (Mon..Sun) to simulate")
    p.add_argument("--start", default="07:30", help="Simulated window start, HH:MM")
    p.add_argument("--end", default="01:30", help="Simulated window end, HH:MM (next day if <= start)")
    p.add_argument("--step-minutes", type=int, default=5)
    p.add_argument("--sleep-seconds", type=float, default=0.5)
    p.add_argument("--endpoint", default="http://localhost:5000/readings")
    p.add_argument("--mock", action="store_true")
    p.add_argument("--mock-output", default="readings_log.csv")
    p.add_argument("--raw-numeric-values", action="store_true",
                    help="Send 'value' as a real JSON number instead of a string. "
                         "Only use this once Person 2's ingest.py is patched to handle "
                         "Decimal conversion (json.loads(..., parse_float=Decimal)) — "
                         "otherwise decimal readings will fail with a 500 error.")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not args.mock and requests is None:
        print("[error] 'requests' not installed. Run: pip install requests")
        sys.exit(1)
    try:
        run_simulation(args)
    except KeyboardInterrupt:
        print("\nStopped by user.")


# --------------------------------------------------------------------------
# ASSUMPTIONS -- read this before presenting to your team
# --------------------------------------------------------------------------
# The sensor_rules.json descriptions were written in prose, not exact
# formulas. Where a judgment call was needed, this is what was chosen:
#
# 1. Occupancy ramp/decay/hold uses the exact minutes given (10 min ramp,
#    full by +15 min, 5 min decay). Between sessions, occupancy comes from
#    break_schedule.csv rows whose day_scope/room_type/time window match;
#    if none match, occupancy is 0. Rows with start_time="varies"
#    (passing_time_theory, passing_time_lab) are skipped because they don't
#    define a fixed window -- corridor movement spikes from those aren't
#    separately modeled. Add them back in if your team wants that detail.
#
# 2. Temperature: while occupied, the reading is modeled as 25C (midpoint
#    of the stated 24-26C AC band) plus occupancy heat gain, since "AC
#    active, target 24-26C" and "+0.02C/person heat gain" together read as
#    the AC holding close to band center under typical load. While empty,
#    the room's temperature drifts 30% of the way toward outdoor ambient
#    every step (a simple thermal-lag model) plus the weather condition
#    offset. This is the most interpretive part of the whole rule set --
#    if Person 1 has a more precise intended formula, swap out
#    gen_temperature().
#
# 3. Humidity has no stated lag/memory, so it's recalculated fresh each
#    reading from outdoor humidity, unlike temperature and CO2 which carry
#    state across time steps.
#
# 4. Light: "building_closed" (from break_schedule) forces 0 lux regardless
#    of occupancy sensor (shouldn't happen, but is a safety fallback).
#    "night_slip_study" hours with no occupant use the security night lux
#    table; all other empty-room daytime hours use unoccupied_daytime_lux.
#
# 5. Energy noise and Light noise both use noise_pct as a PERCENTAGE of the
#    computed value, not a flat unit, since both energy and lux span a wide
#    range across room types (a flat noise number wouldn't make sense for a
#    0.02 kW electrical room vs a 70-person classroom).
