"""
A single, dependency-free HTML dashboard -- no React, no build step, no
auth. Just enough to visually show the system's current state during a
demo. Reads directly from state_manager's in-memory snapshot store.

Every value that ends up in the page is HTML-escaped: device_id comes from
whatever the sensor (or anyone holding the device key) sends, so it must never
be trusted as markup.
"""
from datetime import datetime
from html import escape
from urllib.parse import quote

from agronomy.paddy_profile import (
    FERTILIZER_RULES,
    HARVEST_APPROACHING_WINDOW_DAYS,
    MOISTURE_HIGH_ENTER,
    MOISTURE_LOW_ENTER,
)
from llm import ALERT_CODE_DESCRIPTIONS
from state_manager import ACTIONABLE_CODES, get_all_device_ids, get_snapshot
from weather import RAIN_THRESHOLD_MM

# The ESP32 reports every few minutes; three missed reports means something is wrong.
STALE_AFTER_SECONDS = 15 * 60
REFRESH_SECONDS = 15

# Colour is never the only signal: every severity also has a text label.
_SEVERITY_LABEL = {"bad": "Fault", "warn": "Warning", "info": "Action", "muted": "Note"}
_SEVERITY_ORDER = {"bad": 0, "warn": 1, "info": 2, "muted": 3}
_CODE_SEVERITY = {
    "SENSOR_FAULT_DHT22": "bad",
    "SENSOR_FAULT_SOIL": "bad",
    "LOW_MOISTURE": "warn",
    "EXCESS_MOISTURE": "warn",
    "RAIN_WARNING": "warn",
    "WEATHER_UNAVAILABLE": "muted",
}

_CSS = """
:root{
  --bg:#0c1917;--card:#132a25;--card2:#0f211d;--border:#23463d;--text:#eaf5f1;--muted:#9bb6ae;
  --accent:#7fd6b8;--ok:#5fd3a0;--warn:#f5b942;--bad:#ff7a70;--info:#6cb6ff;--wet:#5aa9e6;
  --track:#1c3a33;--shadow:0 1px 2px rgba(0,0,0,.35);
}
@media (prefers-color-scheme: light){
  :root{
    --bg:#f2f7f5;--card:#ffffff;--card2:#f6faf8;--border:#d3e2db;--text:#13302a;--muted:#587169;
    --accent:#0d7a5a;--ok:#0f7d5a;--warn:#9a5b00;--bad:#c0352b;--info:#1d68ad;--wet:#2a78b5;
    --track:#e3eee9;--shadow:0 1px 2px rgba(20,60,50,.10);
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:20px 16px 40px}
a{color:var(--accent)}
header{display:flex;flex-wrap:wrap;gap:12px 20px;align-items:center;justify-content:space-between;margin-bottom:16px}
h1{font-size:20px;letter-spacing:.04em;margin:0;color:var(--accent)}
.subtitle{margin:2px 0 0;color:var(--muted);font-size:13px}
.updated{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}
.live{width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 0 var(--ok);animation:pulse 2s infinite}
.live.off{background:var(--bad);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(95,211,160,.6)}70%{box-shadow:0 0 0 7px rgba(95,211,160,0)}100%{box-shadow:0 0 0 0 rgba(95,211,160,0)}}
@media (prefers-reduced-motion: reduce){.live{animation:none}}
.devices{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px}
.chip{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border:1px solid var(--border);border-radius:999px;background:var(--card);color:var(--text);text-decoration:none;font-size:13px}
.chip[aria-current="page"]{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.dot{width:9px;height:9px;border-radius:50%;flex:none;background:var(--muted)}
.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.bad{background:var(--bad)}.dot.info{background:var(--info)}
.banner{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;padding:14px 16px;border-radius:12px;border:1px solid var(--border);border-left-width:6px;background:var(--card);margin-bottom:16px;box-shadow:var(--shadow)}
.banner.ok{border-left-color:var(--ok)}.banner.warn{border-left-color:var(--warn)}.banner.bad{border-left-color:var(--bad)}
.banner strong{font-size:17px}
.banner span.msg{color:var(--muted)}
.notice{padding:10px 14px;border-radius:10px;background:var(--card2);border:1px dashed var(--border);color:var(--muted);font-size:13px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:14px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:14px;margin-bottom:14px;align-items:start}
.stack{display:grid;gap:14px;min-width:0}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;box-shadow:var(--shadow);min-width:0;margin-bottom:14px}
.grid .card,.grid2 .card,.stack .card{margin-bottom:0}
.label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.value{font-size:30px;font-weight:700;margin-top:4px;line-height:1.15}
.value small{font-size:14px;font-weight:500;color:var(--muted);margin-left:4px}
.sub{font-size:13px;color:var(--muted);margin-top:6px}
.tag{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid currentColor;vertical-align:middle;margin-left:6px}
.tag.ok{color:var(--ok)}.tag.warn{color:var(--warn)}.tag.bad{color:var(--bad)}.tag.info{color:var(--info)}.tag.muted{color:var(--muted)}
.na{color:var(--bad)}
/* moisture gauge: three zones bounded by the agronomy thresholds */
.gauge{position:relative;height:14px;border-radius:7px;margin:16px 0 4px;overflow:visible}
.gauge .zones{position:absolute;inset:0;border-radius:7px;opacity:.85}
.gauge .marker{position:absolute;top:-5px;width:4px;height:24px;margin-left:-2px;border-radius:2px;background:var(--text);box-shadow:0 0 0 2px var(--card)}
.gauge-scale{position:relative;height:16px;font-size:11px;color:var(--muted)}
.gauge-scale span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.gauge-legend{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:var(--muted);margin-top:2px}
/* crop progress: a progress bar, a schedule strip beneath it, and a "today" marker across both */
.timeline{position:relative;margin:16px 0 10px}
.bar{position:relative;height:12px;border-radius:6px;background:var(--track);overflow:hidden}
.bar .fill{position:absolute;left:0;top:0;bottom:0;background:var(--accent);border-radius:6px}
.sched{position:relative;height:8px;margin-top:5px;border-radius:4px;background:var(--track);overflow:hidden}
.sched .win{position:absolute;top:0;bottom:0;background:var(--info)}
.sched .win.harvest{background:var(--warn)}
.timeline .today{position:absolute;top:-4px;bottom:-4px;width:3px;margin-left:-1.5px;border-radius:2px;background:var(--text);box-shadow:0 0 0 2px var(--card)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
/* forecast */
.fc{display:grid;grid-template-columns:78px 1fr 58px;gap:8px;align-items:center;font-size:13px;margin-top:8px}
.fc .b{height:8px;border-radius:4px;background:var(--track);overflow:hidden}
.fc .b i{display:block;height:100%;background:var(--wet)}
.fc .b i.heavy{background:var(--warn)}
.fc .mm{text-align:right;color:var(--muted)}
/* alerts + delivery */
h2{font-size:14px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:22px 0 10px}
.alerts{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.alerts li{display:flex;gap:12px;align-items:flex-start;padding:12px 14px;background:var(--card);border:1px solid var(--border);border-left-width:5px;border-radius:10px}
.alerts li.bad{border-left-color:var(--bad)}.alerts li.warn{border-left-color:var(--warn)}.alerts li.info{border-left-color:var(--info)}.alerts li.muted{border-left-color:var(--muted)}
.alerts .txt{flex:1;min-width:0}
.alerts code{font-size:11px;color:var(--muted);word-break:break-all}
.none{padding:14px;color:var(--muted);background:var(--card);border:1px solid var(--border);border-radius:10px}
.rows{display:grid;gap:0}
.rows .r{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)}
.rows .r:last-child{border-bottom:0}
.rows .r span:first-child{color:var(--muted)}
footer{margin-top:28px;color:var(--muted);font-size:12px;display:flex;flex-wrap:wrap;gap:4px 18px}
.empty{text-align:center;padding:56px 20px;background:var(--card);border:1px dashed var(--border);border-radius:14px}
.empty h2{margin:0 0 8px;font-size:18px;text-transform:none;letter-spacing:0;color:var(--text)}
.empty p{margin:6px auto;max-width:520px;color:var(--muted)}
.empty code{background:var(--card2);padding:2px 6px;border-radius:5px;border:1px solid var(--border)}
"""

_JS = """
(function(){
  var els=document.querySelectorAll('[data-ts]');
  if(!els.length)return;
  function fmt(s){
    if(s<5)return 'just now';
    if(s<60)return s+'s ago';
    if(s<3600)return Math.floor(s/60)+' min ago';
    if(s<86400)return Math.floor(s/3600)+' h ago';
    return Math.floor(s/86400)+' d ago';
  }
  function tick(){
    var now=Date.now()/1000;
    els.forEach(function(el){
      var s=Math.max(0,Math.round(now-parseFloat(el.getAttribute('data-ts'))));
      el.textContent=fmt(s);
    });
  }
  tick();setInterval(tick,1000);
})();
"""


# ------------------------------------------------------------------ helpers

def _e(value) -> str:
    return escape(str(value), quote=True)


def _fmt(value, fmt: str = "{:.0f}") -> str:
    if value is None:
        return '<span class="na">N/A</span>'
    try:
        return fmt.format(value)
    except (ValueError, TypeError):
        return _e(value)


def _ago_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def _parse_time(value):
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _time_html(value, now: datetime) -> str:
    """Relative time that ticks live in the browser, with a correct server-side fallback."""
    ts = _parse_time(value)
    if ts is None:
        return "unknown"
    return f'<span data-ts="{ts.timestamp():.0f}">{_ago_text((now - ts).total_seconds())}</span>'


def _severity(code: str) -> str:
    # Anything not listed (fertilizer / harvest reminders) is something for the farmer to do.
    return _CODE_SEVERITY.get(code, "info")


def _overall_status(codes: list, stale: bool):
    """Returns (level, headline, detail) for the banner and the device chip."""
    if stale:
        return "bad", "No recent data", "The device has stopped reporting. Check its power and Wi-Fi."
    if any(c.startswith("SENSOR_FAULT") for c in codes):
        return "bad", "Sensor fault", "A sensor is not responding, so some readings below are unavailable."
    actionable = [c for c in codes if c in ACTIONABLE_CODES]
    if actionable:
        n = len(actionable)
        return "warn", "Attention needed", f"{n} active alert{'s' if n != 1 else ''} for this field."
    return "ok", "All clear", "Readings are within the expected range. No action needed."


def _stage_summary(days: int, maturity: int) -> str:
    """One sentence on where the crop is in its schedule."""
    if days >= maturity:
        return "Estimated maturity reached. Check grain colour and moisture before harvesting."
    for rule in FERTILIZER_RULES:
        lo, hi = rule["window"]
        if lo == hi:
            continue
        name = rule["id"].replace("FERT-", "").title()
        if lo <= days <= hi:
            return f"{name} fertilizer window is open now (until day {hi})."
        if days < lo:
            n = lo - days
            return f"Next: {name.lower()} fertilizer window opens in {n} day{'s' if n != 1 else ''} (day {lo})."
    remaining = maturity - days
    if remaining <= HARVEST_APPROACHING_WINDOW_DAYS:
        return f"Harvest window approaching: about {remaining} day{'s' if remaining != 1 else ''} to go."
    return f"About {remaining} days until the estimated harvest check."


def _card(label: str, value_html: str, sub_html: str = "", cls: str = "") -> str:
    sub = f'<div class="sub">{sub_html}</div>' if sub_html else ""
    return f'<div class="card {cls}"><div class="label">{label}</div><div class="value">{value_html}</div>{sub}</div>'


# ------------------------------------------------------------------ sections

def _moisture_card(facts: dict) -> str:
    moisture = facts.get("soil_moisture_index")
    state = facts.get("moisture_state")
    tags = {"low": ("warn", "Low"), "normal": ("ok", "Normal"), "high": ("warn", "Too wet")}
    tag_cls, tag_txt = tags.get(state, ("bad", "Sensor fault"))
    tag = f'<span class="tag {tag_cls}">{tag_txt}</span>'

    if moisture is None:
        return (
            '<div class="card wide"><div class="label">Soil moisture index</div>'
            f'<div class="value"><span class="na">N/A</span>{tag}</div>'
            '<div class="sub">The soil moisture sensor is not reporting.</div></div>'
        )

    pct = max(0.0, min(100.0, float(moisture)))
    lo, hi = MOISTURE_LOW_ENTER, MOISTURE_HIGH_ENTER
    zones = f"linear-gradient(90deg,var(--warn) 0 {lo}%,var(--ok) {lo}% {hi}%,var(--wet) {hi}% 100%)"
    return f"""
    <div class="card wide">
      <div class="label">Soil moisture index</div>
      <div class="value">{pct:.0f}<small>/ 100</small>{tag}</div>
      <div class="gauge" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{pct:.0f}"
           aria-label="Soil moisture index {pct:.0f} out of 100, {tag_txt}">
        <div class="zones" style="background:{zones}"></div>
        <div class="marker" style="left:{pct}%"></div>
      </div>
      <div class="gauge-scale"><span style="left:0%">0</span><span style="left:{lo}%">{lo:.0f}</span>
        <span style="left:{hi}%">{hi:.0f}</span><span style="left:100%">100</span></div>
      <div class="gauge-legend"><span>Dry: irrigate</span><span>Normal</span><span>Waterlogged: drain</span></div>
      <div class="sub">A relative index from the probe, not a volumetric percentage.</div>
    </div>"""


def _weather_card(facts: dict) -> str:
    if not facts.get("weather_checked", True):
        return _card(
            "Rain forecast", '<span style="font-size:18px">Not checked</span>',
            "The forecast is only fetched when an alert needs it.",
        )
    if not facts.get("weather_available"):
        return _card(
            "Rain forecast", '<span style="font-size:18px" class="na">Unavailable</span>',
            "The weather service did not respond. This does not mean no rain.",
        )
    headline = "Rain expected" if facts.get("rain_expected_next_days") else "No significant rain"
    forecast = facts.get("weather_forecast") or []
    scale = max([RAIN_THRESHOLD_MM * 2] + [f.get("rain_mm") or 0 for f in forecast])
    rows = ""
    for f in forecast[:3]:
        mm = f.get("rain_mm") or 0
        try:
            day = datetime.strptime(f.get("date", ""), "%Y-%m-%d").strftime("%a %d %b")
        except ValueError:
            day = f.get("date") or "?"
        heavy = "heavy" if mm >= RAIN_THRESHOLD_MM else ""
        rows += (
            f'<div class="fc"><span>{_e(day)}</span>'
            f'<div class="b"><i class="{heavy}" style="width:{min(100, mm / scale * 100):.0f}%"></i></div>'
            f'<span class="mm">{mm:.1f} mm</span></div>'
        )
    return (
        '<div class="card"><div class="label">Rain forecast (3 days)</div>'
        f'<div class="value" style="font-size:20px">{headline}</div>{rows}</div>'
    )


def _crop_card(facts: dict) -> str:
    days = facts.get("days_since_sowing")
    maturity = int((facts.get("crop_profile") or {}).get("maturity_days") or 0)
    if days is None or maturity <= 0:
        return _card("Crop age", _fmt(None))

    pct = min(100.0, days / maturity * 100)
    wins = ""
    for rule in FERTILIZER_RULES:
        lo, hi = rule["window"]
        if lo == hi:
            continue
        wins += f'<div class="win" style="left:{lo / maturity * 100:.1f}%;width:{(hi - lo + 1) / maturity * 100:.1f}%"></div>'
    h_start = max(0, maturity - HARVEST_APPROACHING_WINDOW_DAYS)
    wins += f'<div class="win harvest" style="left:{h_start / maturity * 100:.1f}%;right:0"></div>'
    return f"""
    <div class="card">
      <div class="label">Crop progress</div>
      <div class="value">Day {days}<small>of about {maturity}</small></div>
      <div class="timeline" role="progressbar" aria-valuemin="0" aria-valuemax="{maturity}" aria-valuenow="{min(days, maturity)}"
           aria-label="Crop age {days} days of {maturity}">
        <div class="bar"><div class="fill" style="width:{pct:.1f}%"></div></div>
        <div class="sched">{wins}</div>
        <div class="today" style="left:{pct:.1f}%"></div>
      </div>
      <div class="legend"><span><i style="background:var(--accent)"></i>Days since sowing</span>
        <span><i style="background:var(--info)"></i>Fertilizer windows</span>
        <span><i style="background:var(--warn)"></i>Harvest window</span></div>
      <div class="sub">{_e(_stage_summary(days, maturity))}</div>
    </div>"""


def _mandi_card(facts: dict) -> str:
    mandi = facts.get("mandi") or {}
    if not mandi.get("available"):
        return ""
    rng = ""
    if mandi.get("min_price") and mandi.get("max_price"):
        rng = f" &middot; range Rs {_e(mandi['min_price'])} to {_e(mandi['max_price'])}"
    return _card(
        "Mandi price",
        f"Rs {_fmt(mandi.get('modal_price'), '{:,.0f}')}<small>/ quintal</small>",
        f"{_e(mandi.get('market', 'unknown market'))}, {_e(mandi.get('arrival_date', 'date unknown'))}{rng}",
    )


def _alerts_html(codes: list, weather_checked: bool) -> str:
    # WEATHER_UNAVAILABLE on a reading that never fetched weather is an artefact, not a real alert.
    shown = [c for c in codes if not (c == "WEATHER_UNAVAILABLE" and not weather_checked)]
    if not shown:
        return '<div class="none">No active alerts.</div>'
    shown.sort(key=lambda c: (_SEVERITY_ORDER[_severity(c)], c))
    items = ""
    for code in shown:
        sev = _severity(code)
        text = ALERT_CODE_DESCRIPTIONS.get(code, code)
        items += (
            f'<li class="{sev}"><span class="tag {sev}" style="margin:0">{_SEVERITY_LABEL[sev]}</span>'
            f'<div class="txt">{_e(text)}<br><code>{_e(code)}</code></div></li>'
        )
    return f'<ul class="alerts">{items}</ul>'


def _delivery_html(snapshot: dict, now: datetime) -> str:
    delivery = snapshot.get("delivery")
    if not delivery:
        return '<div class="none">No advisory has been sent yet. One goes out when a new alert appears.</div>'

    def status(text):
        text = str(text or "-")
        cls = "ok" if text == "sent" else "bad" if text.startswith("failed") else "muted"
        return f'<span class="tag {cls}" style="margin:0">{_e(text)}</span>'

    return f"""
    <div class="card"><div class="rows">
      <div class="r"><span>SMS</span>{status(delivery.get('sms_status'))}</div>
      <div class="r"><span>Voice call</span>{status(delivery.get('voice_status'))}</div>
      <div class="r"><span>Sent</span><span>{_time_html(snapshot.get('delivery_at'), now)}</span></div>
    </div></div>"""


def _device_chips(device_ids: list, selected: str, now: datetime) -> str:
    if len(device_ids) < 2:
        return ""
    chips = ""
    for did in device_ids:
        snap = get_snapshot(did)
        ts = _parse_time(snap.get("updated_at"))
        stale = ts is not None and (now - ts).total_seconds() > STALE_AFTER_SECONDS
        level = _overall_status(snap.get("alert_codes", []), stale)[0]
        current = ' aria-current="page"' if did == selected else ""
        chips += (
            f'<a class="chip" href="?device={quote(did, safe="")}"{current}>'
            f'<span class="dot {level}"></span>{_e(did)}</a>'
        )
    return f'<nav class="devices" aria-label="Devices">{chips}</nav>'


def _page(body: str) -> str:
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">'
        f'<title>Crop Advisory Dashboard</title><style>{_CSS}</style></head>'
        f'<body><div class="wrap">{body}</div><script>{_JS}</script></body></html>'
    )


def _header(subtitle: str, right: str = "") -> str:
    return (
        f'<header><div><h1>VOICE-FIRST CROP ADVISORY</h1><p class="subtitle">{subtitle}</p></div>{right}</header>'
    )


# ---------------------------------------------------------------- entry point

def render_dashboard(device_id: str = None, now: datetime = None) -> str:
    now = now or datetime.now()
    # Only ever look up devices that really exist: get_snapshot() creates state
    # for an unknown id, so an arbitrary ?device= must never reach it.
    device_ids = [d for d in get_all_device_ids() if get_snapshot(d)]

    if not device_ids:
        empty = f"""
        <div class="empty">
          <h2>Waiting for the first sensor reading</h2>
          <p>Nothing has reported yet. Once the ESP32 posts to <code>/sensor-data</code>,
             this page fills in and refreshes by itself every {REFRESH_SECONDS} seconds.</p>
          <p>To try the logic without sending any SMS, use <code>/sensor-data-preview</code> in the
             <a href="/docs">API docs</a>.</p>
        </div>"""
        return _page(_header("Paddy advisory") + empty)

    notice = ""
    if device_id and device_id not in device_ids:
        notice = (
            f'<div class="notice">No device called <b>{_e(device_id)}</b> has reported. '
            f"Showing {_e(device_ids[0])} instead.</div>"
        )
    selected = device_id if device_id in device_ids else device_ids[0]

    snapshot = get_snapshot(selected)
    facts = snapshot.get("facts", {})
    codes = snapshot.get("alert_codes", [])
    profile = facts.get("crop_profile") or {}

    updated = _parse_time(snapshot.get("updated_at"))
    stale = updated is not None and (now - updated).total_seconds() > STALE_AFTER_SECONDS
    level, headline, detail = _overall_status(codes, stale)

    place = profile.get("location") or "Bhatkal"
    crop = (profile.get("crop") or "paddy").title()
    right = (
        f'<div class="updated"><span class="live{" off" if stale else ""}"></span>'
        f"Updated {_time_html(snapshot.get('updated_at'), now)}</div>"
    )

    temp, hum = facts.get("temperature_c"), facts.get("humidity_percent")
    rain_now, light = facts.get("rain_detected_now"), facts.get("light_level")
    dht_note = "DHT22 sensor not responding" if "SENSOR_FAULT_DHT22" in (facts.get("sensor_faults") or []) else ""
    rain_value = "Yes" if rain_now else "No" if rain_now is False else "Unknown"
    rain_sub = "Rain sensor is wet" if rain_now else "Rain sensor is dry" if rain_now is False else "No rain-sensor value sent"

    readings = (
        _card("Temperature", f"{_fmt(temp, '{:.1f}')}<small>&deg;C</small>" if temp is not None else _fmt(None), dht_note)
        + _card("Humidity", f"{_fmt(hum)}<small>%</small>" if hum is not None else _fmt(None), dht_note)
        + _card("Rain right now", rain_value, rain_sub)
        + _card("Ambient light", f"{_fmt(light)}<small>/ 100</small>" if light is not None else _fmt(None), "Informational only")
    )
    cards = (
        _moisture_card(facts)
        + f'<div class="grid">{readings}</div>'
        + f'<div class="grid2">{_crop_card(facts)}<div class="stack">{_weather_card(facts)}{_mandi_card(facts)}</div></div>'
    )

    body = (
        _header(f"{_e(place)} &middot; {_e(crop)} &middot; refreshes every {REFRESH_SECONDS}s", right)
        + _device_chips(device_ids, selected, now)
        + notice
        + f'<div class="banner {level}" role="status"><span class="dot {level}"></span>'
          f'<strong>{_e(headline)}</strong><span class="msg">{_e(detail)}</span></div>'
        + cards
        + "<h2>Active alerts</h2>"
        + _alerts_html(codes, facts.get("weather_checked", True))
        + "<h2>Last advisory sent</h2>"
        + _delivery_html(snapshot, now)
        + f'<footer><span>Device: {_e(selected)}</span>'
          f'<span>Rule version: {_e(facts.get("rule_version", "unknown"))}</span></footer>'
    )
    return _page(body)
