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
import threading
from datetime import datetime, timedelta

from config import ALERT_COOLDOWN_MINUTES, TIME_BASED_ALERT_COOLDOWN_MINUTES, TRANSLATE_SMS_TO
import sms_i18n

# The endpoints are plain `def` functions, which FastAPI runs in a thread pool, so
# every read-modify-write on the store below happens under this lock.
_LOCK = threading.RLock()

# The ESP32 keeps its sequence counter in RAM, so after a power cycle it starts
# again from 0. A reading that is "not newer" is normally a retry/duplicate, but a
# sequence of 0 (after readings were already seen) or one far below the last seen
# value means the device restarted -- ignoring it would silence the device until
# its counter caught up with the old value (hours, at a 5-minute interval).
REBOOT_SEQUENCE_DROP = 10

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

# Calendar-driven reminders: they depend only on the crop's age, so they stay true for
# days (HARVEST_CHECK_DUE stays true for good). They repeat on the long
# TIME_BASED_ALERT_COOLDOWN_MINUTES instead of the short ALERT_COOLDOWN_MINUTES that
# suits live sensor conditions -- see config.py.
TIME_BASED_CODES = {
    "FERTILIZER_DUE_BASAL",
    "FERTILIZER_DUE_TILLERING",
    "FERTILIZER_DUE_PANICLE",
    "HARVEST_APPROACHING",
    "HARVEST_CHECK_DUE",
}

# device_id -> {
#     "moisture_state": "low"/"normal"/"high"/None,
#     "active_codes": set(),
#     "last_sent": {code: datetime},
#     "last_sequence": int,
#     "last_snapshot": dict,   # for the dashboard
# }
_STATE_STORE = {}

# Process-wide (not per-device) runtime state, same in-memory lifetime as the store above:
#   sms_language   -- set from the dashboard; None means "use the .env default"
#   last_sms_event -- outcome of the most recent SMS attempt (any device), for the dashboard banner
_RUNTIME = {"sms_language": None, "last_sms_event": None}


def get_sms_language() -> str:
    """Language for every SMS: the dashboard choice if one was made, else TRANSLATE_SMS_TO, else English."""
    with _LOCK:
        return _RUNTIME["sms_language"] or sms_i18n.normalize_language(TRANSLATE_SMS_TO)


def set_sms_language(lang: str):
    with _LOCK:
        _RUNTIME["sms_language"] = sms_i18n.normalize_language(lang)


def record_sms_event(event: dict):
    """Remember the outcome (sent or failed) of the latest SMS attempt so the dashboard can confirm it."""
    with _LOCK:
        _RUNTIME["last_sms_event"] = dict(event)


def get_last_sms_event():
    with _LOCK:
        event = _RUNTIME["last_sms_event"]
        return dict(event) if event else None


def clear_simulation():
    """
    "Back to real values": forget every simulated (DEMO*) device, and the last-SMS notice if it
    was for a simulated problem. Real devices, their alert state and the language are untouched.
    """
    with _LOCK:
        for device_id in [d for d in _STATE_STORE if d.startswith("DEMO")]:
            _STATE_STORE.pop(device_id, None)
        event = _RUNTIME["last_sms_event"]
        if event and event.get("simulated"):
            _RUNTIME["last_sms_event"] = None


def reset_runtime():
    """Forget the dashboard language choice and the last SMS event (used by tests)."""
    with _LOCK:
        _RUNTIME.update(sms_language=None, last_sms_event=None)


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
    A retried/duplicate send has the same (or slightly lower) sequence number as
    one already processed. Reject it so it can't double-trigger an alert.

    A device restart is NOT a duplicate: see REBOOT_SEQUENCE_DROP above.
    """
    with _LOCK:
        last = get_device_state(device_id)["last_sequence"]
        if sequence > last:
            return False
        restarted = (sequence == 0 and last > 0) or (last - sequence > REBOOT_SEQUENCE_DROP)
        return not restarted


def record_sequence(device_id: str, sequence: int):
    with _LOCK:
        get_device_state(device_id)["last_sequence"] = sequence


def accept_sequence(device_id: str, sequence: int) -> bool:
    """Atomic check-and-record. True if the reading is new and should be processed."""
    with _LOCK:
        if is_duplicate_sequence(device_id, sequence):
            return False
        record_sequence(device_id, sequence)
        return True


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
    with _LOCK:
        state = get_device_state(device_id)
        now = datetime.now()
        live_cooldown = timedelta(minutes=ALERT_COOLDOWN_MINUTES)
        calendar_cooldown = timedelta(minutes=TIME_BASED_ALERT_COOLDOWN_MINUTES)

        current_actionable = set(c for c in current_codes if c in ACTIONABLE_CODES)
        new_alerts = []

        for code in current_actionable:
            cooldown = calendar_cooldown if code in TIME_BASED_CODES else live_cooldown
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


def rollback_alerts(device_id: str, codes: list):
    """
    Undo get_new_alerts() for these codes. Called when delivery FAILED on every
    channel: the farmer was never told, so the cooldown must not start -- the
    codes count as brand new again and are retried on the next reading.
    """
    with _LOCK:
        state = get_device_state(device_id)
        for code in codes:
            state["last_sent"].pop(code, None)
            state["active_codes"].discard(code)


def save_snapshot(device_id: str, snapshot: dict):
    """
    Stores the dashboard snapshot, stamped with `updated_at`. The most recent
    delivery result is kept (with `delivery_at`) until a newer one replaces it, so
    the dashboard doesn't forget what was last sent just because the next reading
    had nothing new to say.
    """
    with _LOCK:
        state = get_device_state(device_id)
        previous = state.get("last_snapshot") or {}
        now = datetime.now().isoformat()

        snap = dict(snapshot)
        snap["updated_at"] = now
        if snap.get("delivery"):
            snap["delivery_at"] = now
        elif previous.get("delivery"):
            snap["delivery"] = previous["delivery"]
            snap["delivery_at"] = previous.get("delivery_at")
        state["last_snapshot"] = snap


def get_snapshot(device_id: str):
    """Read-only lookup: unlike get_device_state it never creates state for an unknown id."""
    with _LOCK:
        state = _STATE_STORE.get(device_id)
        return state.get("last_snapshot") if state else None


def get_all_device_ids():
    with _LOCK:
        return list(_STATE_STORE.keys())


def get_dashboard_device_ids():
    """Devices that have actually produced a reading (i.e. have a snapshot to show)."""
    with _LOCK:
        return [d for d, st in _STATE_STORE.items() if st.get("last_snapshot")]


def reset_device(device_id: str):
    """Forget everything about one device (used to make /demo/trigger repeatable)."""
    with _LOCK:
        _STATE_STORE.pop(device_id, None)
