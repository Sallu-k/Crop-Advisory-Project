"""
Tests for the /dashboard page (dashboard.py) and the snapshot bookkeeping it
relies on (state_manager.save_snapshot). Everything outbound is mocked.
"""
import os
import sys
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dashboard
import main
import state_manager

KEY = {"X-Device-Key": "test-key"}
FORECAST = [
    {"date": "2026-09-21", "rain_mm": 0.0},
    {"date": "2026-09-22", "rain_mm": 8.0},
    {"date": "2026-09-23", "rain_mm": 1.2},
]


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    state_manager._STATE_STORE.clear()
    monkeypatch.setattr(main, "EXPECTED_DEVICE_KEY", "test-key")
    monkeypatch.setattr(main, "SOWING_DATE", (date.today() - timedelta(days=5)).isoformat())
    monkeypatch.setattr(main, "ENABLE_VOICE_CALL", False)
    monkeypatch.setattr(state_manager, "ALERT_COOLDOWN_MINUTES", 720)
    monkeypatch.setattr(main, "send_sms", lambda m: {"success": True, "status_code": 201})
    monkeypatch.setattr(
        main, "get_weather",
        lambda: {"available": True, "rain_expected": True, "forecast": FORECAST},
    )
    monkeypatch.setattr(main, "get_mandi_price", lambda: {"available": False})
    yield
    state_manager._STATE_STORE.clear()


client = TestClient(main.app)


def post(seq, moisture=50.0, device="FIELD-001", **kw):
    body = {"device_id": device, "sequence": seq, "soil_moisture": moisture,
            "temperature": 28.0, "humidity": 60.0, "raining": False}
    body.update(kw)
    r = client.post("/sensor-data", json=body, headers=KEY)
    assert r.status_code == 200
    return r.json()


def page(path="/dashboard"):
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    return r.text


# ------------------------------------------------------------- empty state

def test_empty_state_explains_what_to_do():
    html = page()
    assert "Waiting for the first sensor reading" in html
    assert "/sensor-data-preview" in html


def test_preview_does_not_populate_the_dashboard():
    client.post("/sensor-data-preview", json={"device_id": "X", "sequence": 1, "soil_moisture": 20})
    assert "Waiting for the first sensor reading" in page()


# --------------------------------------------------------- rendering states

def test_dry_field_shows_attention_and_readable_alert():
    post(1, 20, light_level=61)
    html = page()
    assert "Attention needed" in html
    assert "The soil moisture is low." in html          # human-readable text ...
    assert "<code>LOW_MOISTURE</code>" in html          # ... with the raw code kept for reference
    assert 'class="tag warn"' in html and ">Low<" in html
    assert 'aria-valuenow="20"' in html and "left:20.0%" in html
    assert "Day 5" in html
    assert "FIELD-001" in html
    assert "61" in html


def test_healthy_field_is_all_clear():
    post(1, 50)
    html = page()
    assert "All clear" in html
    assert "No active alerts." in html
    assert ">Normal<" in html


def test_waterlogged_field():
    post(1, 90)
    html = page()
    assert "Attention needed" in html and ">Too wet<" in html
    assert "high moisture" in html


def test_gauge_uses_agronomy_thresholds_and_clamps():
    post(1, 100)
    html = page()
    assert "var(--warn) 0 28.0%" in html and "var(--wet) 75.0% 100%" in html
    assert "left:100.0%" in html


def test_sensor_fault_is_shown_honestly_not_faked():
    post(1, 55, temperature=None, humidity=None)
    html = page()
    assert "Sensor fault" in html
    assert "DHT22 sensor not responding" in html
    assert 'class="na">N/A' in html
    assert "SENSOR_FAULT_DHT22" in html


def test_missing_soil_sensor():
    post(1, None)
    html = page()
    assert "The soil moisture sensor is not reporting." in html
    assert "SENSOR_FAULT_SOIL" in html


def test_faults_sort_before_warnings():
    post(1, 20, temperature=None, humidity=None)
    html = page()
    assert html.index("SENSOR_FAULT_DHT22") < html.index("<code>LOW_MOISTURE</code>")


# ----------------------------------------------------- weather: two distinct states

def test_forecast_shown_when_it_was_fetched():
    post(1, 20)
    html = page()
    assert "Rain forecast (3 days)" in html
    assert "Rain expected" in html
    assert "8.0 mm" in html and 'class="heavy"' in html   # >= 5 mm is flagged
    assert "Tue 22 Sep" in html


def test_not_checked_is_not_reported_as_unavailable():
    """Regression: a reading with no new alert never fetches weather; that is not an outage."""
    post(1, 20)                     # alert -> weather fetched
    post(2, 19, temperature=30.0)   # same alert, cooldown -> weather NOT fetched
    html = page()
    assert "Not checked" in html
    assert "Unavailable" not in html
    assert "WEATHER_UNAVAILABLE" not in html


def test_real_weather_outage_is_reported_as_unavailable_not_no_rain(monkeypatch):
    monkeypatch.setattr(main, "get_weather", lambda: {"available": False, "rain_expected": None, "forecast": None})
    post(1, 20)
    html = page()
    assert "Unavailable" in html
    assert "does not mean no rain" in html
    assert "No significant rain" not in html
    assert "WEATHER_UNAVAILABLE" in html   # a genuine outage is still listed


def test_mandi_card_when_available(monkeypatch):
    monkeypatch.setattr(main, "get_mandi_price", lambda: {
        "available": True, "market": "Bhatkal", "arrival_date": "21/09/2026",
        "modal_price": 2300.0, "min_price": "2100", "max_price": "2500"})
    post(1, 20)
    html = page()
    assert "Mandi price" in html and "Rs 2,300" in html and "range Rs 2100 to 2500" in html


def test_no_mandi_card_without_a_price():
    post(1, 20)
    assert "Mandi price" not in page()


# --------------------------------------------------------------- delivery

def test_delivery_status_shown_after_an_alert():
    post(1, 20)
    html = page()
    assert "Last advisory sent" in html
    assert 'class="tag ok" style="margin:0">sent<' in html
    assert "disabled (SMS-only mode)" in html


def test_delivery_status_survives_the_next_healthy_reading():
    """Regression: the panel used to vanish as soon as a reading sent nothing."""
    post(1, 20)
    post(2, 50)
    html = page()
    assert 'class="tag ok" style="margin:0">sent<' in html


def test_failed_delivery_is_flagged(monkeypatch):
    monkeypatch.setattr(main, "send_sms", lambda m: {"success": False, "error": "textbee 401: bad key"})
    post(1, 20)
    html = page()
    assert 'class="tag bad" style="margin:0">failed: textbee 401: bad key<' in html


def test_no_delivery_yet_message():
    post(1, 50)
    assert "No advisory has been sent yet" in page()


# ------------------------------------------------------------ multi-device

def test_device_switcher_and_selection():
    post(1, 20, device="FIELD-A")
    post(1, 50, device="FIELD-B")
    both = page()
    assert 'href="?device=FIELD-A"' in both and 'href="?device=FIELD-B"' in both
    assert both.count(' aria-current="page"') == 1      # leading space: not the CSS selector

    b = page("/dashboard?device=FIELD-B")
    assert "All clear" in b
    assert ' aria-current="page"' in b.split('href="?device=FIELD-B"')[1][:40]
    a = page("/dashboard?device=FIELD-A")
    assert "Attention needed" in a


def test_single_device_shows_no_switcher():
    post(1, 50)
    assert 'class="devices"' not in page()


def test_unknown_device_falls_back_and_creates_no_state():
    post(1, 50, device="FIELD-A")
    before = list(state_manager.get_all_device_ids())
    html = page("/dashboard?device=nope")
    assert "No device called" in html and "nope" in html
    assert "FIELD-A" in html
    assert state_manager.get_all_device_ids() == before   # a lookup must not create state


# -------------------------------------------------------------- staleness

def test_stale_device_is_flagged():
    post(1, 50)
    later = datetime.now() + timedelta(minutes=20)
    html = dashboard.render_dashboard(now=later)
    assert "No recent data" in html
    assert 'class="live off"' in html
    assert "All clear" not in html


def test_recent_device_is_not_stale():
    post(1, 50)
    html = dashboard.render_dashboard(now=datetime.now() + timedelta(minutes=5))
    assert "No recent data" not in html
    assert "5 min ago" in html


# ---------------------------------------------------- security / robustness

def test_hostile_device_id_is_escaped():
    evil = "<script>alert(1)</script>"
    post(1, 50, device=evil)
    post(1, 50, device="FIELD-B")
    for path in ("/dashboard", "/dashboard?device=%3Cscript%3Ealert%281%29%3C%2Fscript%3E"):
        html = page(path)
        assert "<script>alert(1)" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_hostile_query_param_is_escaped():
    post(1, 50)
    html = page("/dashboard?device=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E")
    assert "<img src=x" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_snapshot_with_missing_fields_does_not_crash():
    """Old / partial snapshots (no facts, no timestamp) must still render."""
    state_manager.get_device_state("LEGACY")["last_snapshot"] = {"facts": {}, "alert_codes": []}
    html = page()
    assert "LEGACY" in html and "All clear" in html


def test_unknown_alert_code_still_renders():
    state_manager.get_device_state("D")["last_snapshot"] = {"facts": {}, "alert_codes": ["BRAND_NEW_CODE"]}
    assert "BRAND_NEW_CODE" in page()


class _Balanced(HTMLParser):
    VOID = {"meta", "br", "img", "input", "link", "hr"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> (open: {self.stack[-3:]})")
        else:
            self.stack.pop()


@pytest.mark.parametrize("scenario", ["empty", "dry", "healthy", "fault", "two_devices"])
def test_html_is_well_formed(scenario):
    if scenario == "dry":
        post(1, 20)
    elif scenario == "healthy":
        post(1, 50)
    elif scenario == "fault":
        post(1, None, temperature=None, humidity=None)
    elif scenario == "two_devices":
        post(1, 20, device="A")
        post(1, 50, device="B")
    parser = _Balanced()
    parser.feed(page())
    assert parser.errors == [] and parser.stack == []


# -------------------------------------------------------------- stage text

@pytest.mark.parametrize("days,expected", [
    (5, "Next: tillering fertilizer window opens in 13 days (day 18)"),
    (20, "Tillering fertilizer window is open now (until day 25)"),
    (30, "Next: panicle fertilizer window opens in 10 days (day 40)"),
    (45, "Panicle fertilizer window is open now (until day 50)"),
    (60, "About 55 days until the estimated harvest check."),
    (108, "Harvest window approaching: about 7 days to go."),
    (114, "Harvest window approaching: about 1 day to go."),
    (115, "Estimated maturity reached."),
    (140, "Estimated maturity reached."),
])
def test_stage_summary(days, expected):
    assert dashboard._stage_summary(days, 115).startswith(expected)


# ------------------------------------------------------- snapshot bookkeeping

def test_snapshot_is_timestamped():
    state_manager.save_snapshot("D", {"facts": {}, "alert_codes": []})
    snap = state_manager.get_snapshot("D")
    assert datetime.fromisoformat(snap["updated_at"]) <= datetime.now()


def test_snapshot_keeps_last_delivery_until_a_new_one_replaces_it():
    d1 = {"sms_status": "sent", "voice_status": "disabled"}
    state_manager.save_snapshot("D", {"facts": {}, "alert_codes": [], "delivery": d1})
    first = state_manager.get_snapshot("D")["delivery_at"]

    state_manager.save_snapshot("D", {"facts": {}, "alert_codes": []})      # nothing sent this time
    snap = state_manager.get_snapshot("D")
    assert snap["delivery"] == d1 and snap["delivery_at"] == first

    d2 = {"sms_status": "failed: x", "voice_status": "disabled"}
    state_manager.save_snapshot("D", {"facts": {}, "alert_codes": [], "delivery": d2})
    assert state_manager.get_snapshot("D")["delivery"] == d2
