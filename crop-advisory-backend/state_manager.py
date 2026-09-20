"""
Tracks per-device state so the system only notifies on STATE CHANGE, not on
every single sensor reading. This is the single most important fix in this
codebase: without it, a dry field produces a phone call every 5 minutes for
as long as it stays dry.

LIMITATION (stated honestly, not hidden): this is in-memory, per-process
state. On a free-tier Render deployment the process can restart (e.g. after
inactivity), which resets this state. For a one-week student prototype this
is an acceptable, disclosed limitation -- a real deployment would use a
small persistent store (SQLite/Redis) instead. The architecture already
separates this into its own module specifically so swapping it out later is
a one-file change.

ACTIONABLE_CODES are the ones gated by state-change + cooldown (they cause a
call/SMS only when they're new or the cooldown has expired). Everything else
(e.g. mandi price) is informational and just gets included in the SMS body
whenever an actionable alert is already being sent -- it never triggers a
notification by itself.
"""
from datetime import datetime, timedelta

from config import ALERT_COOLDOWN_MINUTES

ACTIONABLE_CODES = {
    "LOW_MOISTURE",
    "EXCESS_MOISTURE",
    "FERTILIZER_DUE_BASAL",
    "FERTILIZER_DUE_TILLERING",
    "FERTILIZER_DUE_PANICLE",
    "HARVEST_CHECK_DUE",
    "HARVEST_APPROACHING",
    "RAIN_WARNING",
    "SENSOR_FAULT_DHT22",
    "SENSOR_FAULT_SOIL",
}

# device_id -> {
#     "moisture_state": "low"/"normal"/"high"/None,
#     "active_codes": set(),
#     "last_sent": {code: datetime},
#     "last_sequence": int,
#     "last_snapshot": dict,   # for the dashboard
# }
_STATE_STORE = {}


def get_device_state(device_id: str) -> dict:
    if device_id not in _STATE_STORE:
        _STATE_STORE[device_id] = {
            "moisture_state": None,
            "active_codes": set(),
            "last_sent": {},
            "last_sequence": -1,
            "last_snapshot": None,
        }
    return _STATE_STORE[device_id]


def is_duplicate_sequence(device_id: str, sequence: int) -> bool:
    """
    A retried/duplicate ESP32 send has the same (or lower) sequence number
    as one already processed. Reject it so it can't double-trigger an alert.
    Note: a device reboot resets its own sequence counter to 0, which would
    look like a big drop -- for a one-week single-device demo this is an
    accepted simplification; a real deployment would pair sequence with a
    boot ID.
    """
    state = get_device_state(device_id)
    return sequence <= state["last_sequence"]


def record_sequence(device_id: str, sequence: int):
    get_device_state(device_id)["last_sequence"] = sequence


def get_previous_moisture_state(device_id: str):
    return get_device_state(device_id)["moisture_state"]


def update_moisture_state(device_id: str, new_state):
    get_device_state(device_id)["moisture_state"] = new_state


def get_new_alerts(device_id: str, current_codes: list) -> list:
    """
    Compares current_codes against what's already active + cooldown timers.
    Returns only the codes that should ACTUALLY trigger a new notification
    right now, and updates the stored state to reflect this call.
    """
    state = get_device_state(device_id)
    now = datetime.now()
    cooldown = timedelta(minutes=ALERT_COOLDOWN_MINUTES)

    current_actionable = set(c for c in current_codes if c in ACTIONABLE_CODES)
    new_alerts = []

    for code in current_actionable:
        was_active = code in state["active_codes"]
        last_sent_time = state["last_sent"].get(code)
        cooldown_expired = (last_sent_time is None) or (now - last_sent_time >= cooldown)

        if (not was_active) or cooldown_expired:
            new_alerts.append(code)
            state["last_sent"][code] = now

    # A code that WAS active but no longer is just gets dropped silently
    # (e.g. moisture went from low back to normal -- no "all clear" call,
    # to avoid doubling the number of notifications for no real benefit).
    state["active_codes"] = current_actionable

    return sorted(new_alerts)


def save_snapshot(device_id: str, snapshot: dict):
    get_device_state(device_id)["last_snapshot"] = snapshot


def get_snapshot(device_id: str):
    return get_device_state(device_id).get("last_snapshot")


def get_all_device_ids():
    return list(_STATE_STORE.keys())
