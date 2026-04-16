"""
03_seed_history.py
Seeds 7 days of historical telemetry so the predictive maintenance
Edge Function has a baseline to compare against.
Inserts in batches of 500 to stay within Supabase rate limits.
"""

import os
import random
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DEVICE_ID    = os.getenv("DEVICE_ID")

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=minimal",
}

SETPOINT       = 36.5
DAYS           = 7
READINGS_PER_H = 60        # one per minute
BATCH_SIZE     = 500

def generate_history():
    rows   = []
    now    = datetime.now(timezone.utc)
    start  = now - timedelta(days=DAYS)
    temp   = 36.5
    effort = 28.0          # healthy baseline effort

    total_minutes = DAYS * 24 * READINGS_PER_H
    for i in range(total_minutes):
        ts = start + timedelta(minutes=i)

        # Slow drift upward in last 24 h to simulate degradation
        day_fraction = i / total_minutes
        if day_fraction > 0.85:
            effort_drift = effort + (day_fraction - 0.85) / 0.15 * 8.0
        else:
            effort_drift = effort

        noise_temp   = random.gauss(0, 0.08)
        noise_effort = random.gauss(0, 1.2)
        temp_val     = round(36.5 + noise_temp, 2)
        effort_val   = round(max(0, effort_drift + noise_effort), 2)

        rows.append({
            "device_id":      DEVICE_ID,
            "recorded_at":    ts.isoformat(),
            "temperature_c":  temp_val,
            "setpoint_c":     SETPOINT,
            "pid_output":     effort_val,
            "pid_effort":     effort_val,
            "wifi_connected": True,
            "synced_from_sd": False,
        })

    return rows

def insert_batch(batch):
    url = f"{SUPABASE_URL}/rest/v1/telemetry"
    r   = requests.post(url, json=batch, headers=HEADERS, timeout=30)
    return r.status_code

def main():
    print("Generating 7-day history...")
    rows  = generate_history()
    total = len(rows)
    print(f"Total rows to insert: {total}")

    inserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch  = rows[i:i + BATCH_SIZE]
        status = insert_batch(batch)
        inserted += len(batch)
        pct = inserted / total * 100
        print(f"  [{pct:5.1f}%] inserted {inserted}/{total} — HTTP {status}")

    print("\nDone. Historical baseline is ready.")
    print("You can now run the Edge Function or dashboard.")

if __name__ == "__main__":
    main()
