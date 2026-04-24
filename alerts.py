import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from google import genai
import store

_store: list[dict] = [
    {
        "id": "mock-1",
        "zone_key": "restroom_a",
        "zone_name": "Restroom Block A",
        "zone_id": "WC-N",
        "section": "North Stand",
        "severity": "CRITICAL",
        "trigger": "94% occupancy",
        "staff_alert": "Critical crowd surge at Restroom Block A. Deploy flow control team to divert fans to Level 2 facilities immediately.",
        "pa_message": "Fans near North Stand: Restroom Block A is currently busy. Please use level 2 facilities for faster service.",
        "action": "deploy_staff",
        "occupancy_percent": 94,
        "wait_time_min": 11,
        "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "acknowledged": False,
    },
    {
        "id": "mock-2",
        "zone_key": "concession_hall",
        "zone_name": "Main Concession Hall",
        "zone_id": "FC-1",
        "section": "Level 1 Concourse",
        "severity": "WARNING",
        "trigger": "25 min wait time",
        "staff_alert": "Wait times at Main Concession Hall exceeded 20m. Open auxiliary counters 4 and 5 to reduce congestion.",
        "pa_message": "Enjoy the match! Auxiliary food counters are now open in the South Stand for your convenience.",
        "action": "open_overflow",
        "occupancy_percent": 89,
        "wait_time_min": 25,
        "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=12)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "acknowledged": False,
    },
    {
        "id": "mock-3",
        "zone_key": "vip_lounge",
        "zone_name": "VIP Premier Lounge",
        "zone_id": "VIP-1",
        "section": "Corporate Box Level",
        "severity": "WARNING",
        "trigger": "low sentiment (0.38)",
        "staff_alert": "Sentiment dip detected in VIP Lounge. Frustration due to catering delays. Sending guest relations supervisor.",
        "pa_message": "",
        "action": "monitor",
        "occupancy_percent": 65,
        "wait_time_min": 5,
        "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "acknowledged": False,
    }
]
_MAX = 20


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _recently_alerted(zone_key: str, minutes: int = 15) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    for a in _store:
        if a["zone_key"] == zone_key:
            try:
                ts = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                if ts > cutoff:
                    return True
            except Exception:
                pass
    return False


def check_and_generate() -> list[dict]:
    zones = store.get_all_zones()
    mc = store.get_match_context()
    new_alerts: list[dict] = []

    for zone_key, zone in zones.items():
        occ  = zone["occupancy_percent"]
        wait = zone["wait_time_min"]
        sent = zone["emotion"]["avg_sentiment_score"]

        if occ >= 85:
            severity, trigger = "HIGH", f"{occ}% occupancy"
        elif wait >= 15:
            severity, trigger = "MEDIUM", f"{wait} min wait time"
        elif sent <= 0.45:
            severity, trigger = "MEDIUM", f"low sentiment ({sent:.2f})"
        else:
            continue

        if _recently_alerted(zone_key):
            continue

        alert = _build_alert(zone_key, zone, mc, severity, trigger)
        _store.insert(0, alert)
        if len(_store) > _MAX:
            _store.pop()
        new_alerts.append(alert)

    return new_alerts


def _build_alert(zone_key: str, zone: dict, mc: dict, severity: str, trigger: str) -> dict:
    try:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        break_in = mc.get("innings_break_minute", 90) - mc.get("current_minute", 0)
        prompt = f"""You are a smart stadium operations AI at Narendra Modi Stadium during IPL 2026.
Generate a SHORT operational alert for this crowd situation.

Zone: {zone["name"]} ({zone["zone_id"]}) — {zone["section"]}
Issue: {trigger}
Status: {zone["occupancy_percent"]}% full ({zone["count"]}/{zone["capacity"]} people), {zone["wait_time_min"]} min wait
Crowd mood: {zone["emotion"]["avg_sentiment_score"]:.2f} sentiment, {zone["emotion"]["frustrated"]}% frustrated
Match: {mc.get("score","?")} in {mc.get("overs","?")} overs, innings break in {break_in} min

Return JSON only, no markdown fences:
{{"staff_alert":"1 concise sentence for ops team with specific action","pa_message":"1 friendly sentence PA announcement redirecting fans","action":"deploy_staff|open_overflow|redirect_fans|monitor"}}"""

        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        text = resp.text.strip()
        # strip markdown fences if present
        for fence in ["```json", "```"]:
            if text.startswith(fence):
                text = text[len(fence):]
                break
        text = text.rstrip("`").strip()
        data = json.loads(text)
    except Exception:
        data = {
            "staff_alert": f"Immediate attention needed at {zone['name']} — {trigger}. Deploy staff now.",
            "pa_message": f"Fans near {zone['name']}: alternative facilities are available with shorter wait times.",
            "action": "monitor",
        }

    return {
        "id": str(uuid.uuid4()),
        "zone_key": zone_key,
        "zone_name": zone["name"],
        "zone_id": zone["zone_id"],
        "section": zone["section"],
        "severity": severity,
        "trigger": trigger,
        "staff_alert": data.get("staff_alert", ""),
        "pa_message": data.get("pa_message", ""),
        "action": data.get("action", "monitor"),
        "occupancy_percent": zone["occupancy_percent"],
        "wait_time_min": zone["wait_time_min"],
        "timestamp": _now(),
        "acknowledged": False,
    }


def get_all() -> list[dict]:
    return _store


def acknowledge(alert_id: str) -> bool:
    for a in _store:
        if a["id"] == alert_id:
            a["acknowledged"] = True
            return True
    return False


def clear() -> None:
    _store.clear()
