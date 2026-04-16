// supabase/functions/predictive_maintenance/index.ts
//
// Edge Function — Predictive Maintenance Engine
// Deployed to Supabase and triggered every hour via pg_cron.
//
// Logic:
//   1. Fetch all active devices
//   2. For each device, compute 24h mean pid_effort
//   3. Compute 7-day rolling baseline
//   4. If deviation > 20% → INSERT alert into alarm_system
//   5. Update device_status table
//
// Deploy command (run once from your project root):
//   npx supabase functions deploy predictive_maintenance

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL  = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY  = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ALERT_THRESHOLD_PCT = 20.0;

Deno.serve(async (_req) => {
  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

  // ── 1. Get all devices ──────────────────────────────────────────────────
  const { data: devices, error: devErr } = await supabase
    .from("devices")
    .select("id, name");

  if (devErr) {
    return new Response(JSON.stringify({ error: devErr.message }), { status: 500 });
  }

  const results = [];

  for (const device of devices ?? []) {
    const deviceId = device.id;

    // ── 2. 24h mean pid_effort ───────────────────────────────────────────
    const since24h = new Date(Date.now() - 86_400_000).toISOString();
    const { data: recent } = await supabase
      .from("telemetry")
      .select("pid_effort")
      .eq("device_id", deviceId)
      .gte("recorded_at", since24h);

    if (!recent || recent.length === 0) continue;

    const mean24h = recent.reduce((s: number, r: any) => s + r.pid_effort, 0) / recent.length;

    // ── 3. 7-day rolling baseline ────────────────────────────────────────
    const since7d = new Date(Date.now() - 7 * 86_400_000).toISOString();
    const { data: history } = await supabase
      .from("telemetry")
      .select("pid_effort")
      .eq("device_id", deviceId)
      .gte("recorded_at", since7d);

    if (!history || history.length === 0) continue;

    const baseline = history.reduce((s: number, r: any) => s + r.pid_effort, 0) / history.length;

    // ── 4. Compute deviation ─────────────────────────────────────────────
    const delta = baseline > 0 ? ((mean24h - baseline) / baseline) * 100 : 0;

    const status = delta > ALERT_THRESHOLD_PCT ? "DEGRADED" : "NORMAL";

    // ── 5. Update device_status ──────────────────────────────────────────
    await supabase
      .from("device_status")
      .upsert({
        device_id:        deviceId,
        last_checked_at:  new Date().toISOString(),
        pid_effort_mean:  Math.round(mean24h * 100) / 100,
        baseline_mean:    Math.round(baseline * 100) / 100,
        deviation_pct:    Math.round(delta * 100) / 100,
        health_status:    status,
      });

    // ── 6. Insert alarm if degraded ──────────────────────────────────────
    if (delta > ALERT_THRESHOLD_PCT) {
      await supabase
        .from("alarm_system")
        .insert({
          device_id:  deviceId,
          alarm_type: "PREDICTIVE_MAINTENANCE",
          message:    `PID effort ${delta.toFixed(1)}% above 7-day baseline. ` +
                      `Mean: ${mean24h.toFixed(1)}, Baseline: ${baseline.toFixed(1)}. ` +
                      `Heating element fatigue suspected.`,
          resolved:   false,
        });
    }

    results.push({ device_id: deviceId, delta: delta.toFixed(1), status });
  }

  return new Response(
    JSON.stringify({ processed: results.length, results }),
    { headers: { "Content-Type": "application/json" } }
  );
});
