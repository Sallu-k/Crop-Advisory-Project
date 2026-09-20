"""
A single, dependency-free HTML dashboard -- no React, no build step, no
auth. Just enough to visually show the system's current state during a
demo. Reads directly from state_manager's in-memory snapshot store.
"""
from state_manager import get_snapshot, get_all_device_ids


def render_dashboard(device_id: str = None) -> str:
    device_ids = get_all_device_ids()

    if not device_id and device_ids:
        device_id = device_ids[0]

    snapshot = get_snapshot(device_id) if device_id else None

    if not snapshot:
        body = "<p>No readings received yet. Waiting for the first sensor POST...</p>"
    else:
        facts = snapshot.get("facts", {})
        alert_codes = snapshot.get("alert_codes", [])
        moisture = facts.get("soil_moisture_index")
        moisture_state = facts.get("moisture_state") or "unknown (sensor fault)"
        temp = facts.get("temperature_c")
        humidity = facts.get("humidity_percent")
        rain_now = facts.get("rain_detected_now")
        weather_available = facts.get("weather_available")
        rain_forecast = facts.get("rain_expected_next_days")
        days = facts.get("days_since_sowing")
        rule_version = facts.get("rule_version")
        last_delivery = snapshot.get("delivery")

        alerts_html = (
            "".join(f"<li>{code}</li>" for code in alert_codes)
            if alert_codes else "<li>None currently active</li>"
        )

        weather_line = (
            ("Rain expected in next 3 days" if rain_forecast else "No significant rain expected")
            if weather_available else "Weather forecast unavailable"
        )

        delivery_html = ""
        if last_delivery:
            delivery_html = f"""
            <div class="row"><span>Last Voice Delivery</span><span>{last_delivery.get('voice_status', '-')}</span></div>
            <div class="row"><span>Last SMS Delivery</span><span>{last_delivery.get('sms_status', '-')}</span></div>
            """

        body = f"""
        <div class="grid">
          <div class="card">
            <div class="label">Soil Moisture Index</div>
            <div class="value">{moisture if moisture is not None else 'N/A'} / 100</div>
            <div class="sub">State: {moisture_state}</div>
          </div>
          <div class="card">
            <div class="label">Temperature</div>
            <div class="value">{f'{temp:.1f} C' if temp is not None else 'N/A (sensor fault)'}</div>
          </div>
          <div class="card">
            <div class="label">Humidity</div>
            <div class="value">{f'{humidity:.0f} %' if humidity is not None else 'N/A (sensor fault)'}</div>
          </div>
          <div class="card">
            <div class="label">Rain (right now)</div>
            <div class="value">{'Yes' if rain_now else 'No' if rain_now is False else 'Unknown'}</div>
          </div>
          <div class="card">
            <div class="label">Weather Forecast</div>
            <div class="value" style="font-size:16px">{weather_line}</div>
          </div>
          <div class="card">
            <div class="label">Crop Age</div>
            <div class="value">{days} days</div>
          </div>
        </div>

        <h3>Active Alert Codes</h3>
        <ul>{alerts_html}</ul>

        {delivery_html}

        <p class="muted">Rule version: {rule_version} &middot; Device: {device_id}</p>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta http-equiv="refresh" content="15">
      <title>Voice Crop Advisory - Dashboard</title>
      <style>
        body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; background:#0f1f1c; color:#eaf5f1; margin:0; padding:24px; }}
        h1 {{ font-size: 20px; color:#7fd6b8; margin-bottom:4px; }}
        .subtitle {{ color:#9fb8b0; margin-top:0; margin-bottom:24px; font-size:13px; }}
        .grid {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap:14px; margin-bottom:24px; }}
        .card {{ background:#16302a; border:1px solid #22463c; border-radius:10px; padding:16px; }}
        .label {{ font-size:12px; color:#9fb8b0; text-transform:uppercase; letter-spacing:0.05em; }}
        .value {{ font-size:26px; font-weight:bold; margin-top:6px; }}
        .sub {{ font-size:12px; color:#9fb8b0; margin-top:4px; }}
        ul {{ line-height:1.8; }}
        .row {{ display:flex; justify-content:space-between; max-width:320px; padding:4px 0; border-bottom:1px solid #22463c; }}
        .muted {{ color:#77948c; font-size:12px; margin-top:24px; }}
      </style>
    </head>
    <body>
      <h1>VOICE-FIRST CROP ADVISORY</h1>
      <p class="subtitle">Bhatkal &middot; Paddy &middot; auto-refreshes every 15s</p>
      {body}
    </body>
    </html>
    """
