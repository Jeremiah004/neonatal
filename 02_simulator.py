"""
02_simulator.py
Simulates an ESP32 neonatal warmer sending telemetry to Supabase.
Runs a realistic PID control loop - temperature rises toward setpoint,
pid_effort increases if element is degrading (for predictive maintenance).
"""

import os
import time
import random
import requests
from datetime import datetime, timezone
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

# ── PID constants (match thesis values) ──────────────────────────────────────
KP = 2.5
KI = 0.10
KD = 0.05
SETPOINT    = 36.5   # °C  thermoneutral zone centre
INTERVAL_S  = 6      # seconds between ticks (1 Hz in real firmware; 6s here = fast demo)

# ── Simulated element degradation ────────────────────────────────────────────
# After DEGRADE_AFTER ticks, pid_effort drifts upward ~20% to trigger predictive alert
DEGRADE_AFTER = 50

def pid_tick(temp, setpoint, integral, prev_error, dt=1.0, degrade_factor=1.0):
    error      = setpoint - temp
    integral  += error * dt
    derivative = (error - prev_error) / dt
    output     = KP * error + KI * integral + KD * derivative
    output     = max(0.0, min(100.0, output))          # clamp 0–100 %
    effort     = round(output * degrade_factor, 2)     # degradation inflates effort
    return output, effort, integral, error

def simulate_temperature(temp, pid_output):
    """Simple first-order thermal model."""
    heating    = pid_output * 0.04          # heater contribution
    ambient    = (22.0 - temp) * 0.01       # ambient loss
    noise      = random.gauss(0, 0.05)      # sensor noise
    return round(temp + heating + ambient + noise, 2)

def insert_telemetry(row: dict):
    url = f"{SUPABASE_URL}/rest/v1/telemetry"
    r   = requests.post(url, json=row, headers=HEADERS, timeout=10)
    return r.status_code

def main():
    print("=" * 55)
    print("  Smart Neonatal Warmer — ESP32 Simulator")
    print(f"  Device : {DEVICE_ID}")
    print(f"  Target : {SETPOINT} °C")
    print("=" * 55)
    print("Tick | Temp (°C) | PID Out | PID Effort | Status")
    print("-" * 55)

    temp        = 32.0   # cold start
    integral    = 0.0
    prev_error  = SETPOINT - temp
    tick        = 0
    wifi        = True

    while True:
        tick += 1

        # Simulate occasional Wi-Fi dropout (10 % chance)
        if random.random() < 0.10:
            wifi = not wifi

        # Degradation kicks in after DEGRADE_AFTER ticks
        degrade = 1.0 + (0.25 * min(tick - DEGRADE_AFTER, 30) / 30) if tick > DEGRADE_AFTER else 1.0

        pid_output, pid_effort, integral, prev_error = pid_tick(
            temp, SETPOINT, integral, prev_error, degrade_factor=degrade
        )
        temp = simulate_temperature(temp, pid_output)

        row = {
            "device_id":      DEVICE_ID,
            "recorded_at":    datetime.now(timezone.utc).isoformat(),
            "temperature_c":  temp,
            "setpoint_c":     SETPOINT,
            "pid_output":     round(pid_output, 2),
            "pid_effort":     pid_effort,
            "wifi_connected": wifi,
            "synced_from_sd": False,
        }

        status_code = insert_telemetry(row) if wifi else 0
        status_str  = "OK" if status_code == 201 else ("OFFLINE" if not wifi else f"ERR {status_code}")

        print(f" {tick:3d} | {temp:9.2f} | {pid_output:7.2f} | {pid_effort:10.2f} | {status_str}")

        time.sleep(INTERVAL_S)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
