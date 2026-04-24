import copy
import random
from datetime import datetime, timezone

_INITIAL_DATA = {
    "zones": {
        "restroom_north": {
            "name": "Restroom Block A — North",
            "zone_id": "WC-N",
            "section": "North Stand",
            "type": "restroom",
            "capacity": 60,
            "occupancy_percent": 68,
            "count": 41,
            "wait_time_min": 7,
            "emotion": {
                "happy": 35,
                "neutral": 40,
                "sad": 15,
                "frustrated": 10,
                "avg_sentiment_score": 0.62,
            },
            "last_updated": "2026-04-25T14:22:00Z",
        },
        "restroom_south": {
            "name": "Restroom Block B — South",
            "zone_id": "WC-S",
            "section": "South Stand",
            "type": "restroom",
            "capacity": 60,
            "occupancy_percent": 38,
            "count": 23,
            "wait_time_min": 2,
            "emotion": {
                "happy": 62,
                "neutral": 28,
                "sad": 6,
                "frustrated": 4,
                "avg_sentiment_score": 0.82,
            },
            "last_updated": "2026-04-25T14:22:00Z",
        },
        "concession_main": {
            "name": "Main Concession Hall",
            "zone_id": "FC-1",
            "section": "Level 1 Concourse",
            "type": "food",
            "capacity": 180,
            "occupancy_percent": 74,
            "count": 133,
            "wait_time_min": 14,
            "emotion": {
                "happy": 48,
                "neutral": 28,
                "sad": 9,
                "frustrated": 15,
                "avg_sentiment_score": 0.61,
            },
            "last_updated": "2026-04-25T14:22:00Z",
        },
        "concession_express": {
            "name": "Express Kiosk — East Wing",
            "zone_id": "EK-E",
            "section": "East Concourse",
            "type": "food",
            "capacity": 80,
            "occupancy_percent": 91,
            "count": 73,
            "wait_time_min": 20,
            "emotion": {
                "happy": 30,
                "neutral": 22,
                "sad": 18,
                "frustrated": 30,
                "avg_sentiment_score": 0.44,
            },
            "last_updated": "2026-04-25T14:22:00Z",
        },
        "premium_pavilion": {
            "name": "Premium Pavilion Lounge",
            "zone_id": "VIP-1",
            "section": "Pavilion End",
            "type": "lounge",
            "capacity": 90,
            "occupancy_percent": 92,
            "count": 83,
            "wait_time_min": 3,
            "emotion": {
                "happy": 78,
                "neutral": 18,
                "sad": 2,
                "frustrated": 2,
                "avg_sentiment_score": 0.91,
            },
            "last_updated": "2026-04-25T14:22:00Z",
        },
    },
    "match_context": {
        "match_id": "IPL-2026-M42",
        "match_title": "IPL 2026 — Match 42",
        "venue": "Narendra Modi Stadium, Ahmedabad",
        "team_a": "RCB",
        "team_b": "GT",
        "batting_team": "RCB",
        "score": "127/3",
        "overs": "14.3",
        "run_rate": 8.7,
        "target": None,
        "innings": 1,
        "current_minute": 52,
        "innings_break_minute": 90,
        "next_break_type": "Innings Break",
        "stadium_capacity": 132000,
        "attendance": 118450,
        "attendance_pct": 89.7,
        "recent_event": "FOUR! Kohli drives through cover point",
        "overall_crowd_sentiment": 0.78,
        "crowd_density": "HIGH",
    },
}

_store: dict = copy.deepcopy(_INITIAL_DATA)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Read ──────────────────────────────────────────────────────────────────────

def get_zone(name: str) -> dict | None:
    return _store["zones"].get(name)


def get_all_zones() -> dict:
    return _store["zones"]


def get_match_context() -> dict:
    return _store["match_context"]


def get_stats() -> dict:
    zones = _store["zones"]
    avg_occ  = sum(z["occupancy_percent"] for z in zones.values()) / len(zones)
    avg_sent = sum(z["emotion"]["avg_sentiment_score"] for z in zones.values()) / len(zones)
    crowded  = [k for k, v in zones.items() if v["occupancy_percent"] > 75]
    clear    = [k for k, v in zones.items() if v["occupancy_percent"] < 50]
    density  = "LOW" if avg_occ < 50 else "MEDIUM" if avg_occ < 72 else "HIGH"
    mc       = _store["match_context"]
    return {
        "avg_occupancy_percent": round(avg_occ, 1),
        "avg_sentiment_score":   round(avg_sent, 2),
        "crowd_density":         density,
        "crowded_zones":         crowded,
        "clear_zones":           clear,
        "total_zones":           len(zones),
        "match_context":         mc,
    }


# ── Write ─────────────────────────────────────────────────────────────────────

def update_zone(name: str, patch: dict) -> bool:
    zone = _store["zones"].get(name)
    if not zone:
        return False
    for key, value in patch.items():
        if key == "emotion" and isinstance(value, dict):
            zone["emotion"].update(value)
        else:
            zone[key] = value
    if "occupancy_percent" in patch and "count" not in patch:
        zone["count"] = round(zone["occupancy_percent"] * zone["capacity"] / 100)
    zone["last_updated"] = _now()
    return True


def simulate_surge(zone_name: str) -> bool:
    zone = _store["zones"].get(zone_name)
    if not zone:
        return False
    zone["occupancy_percent"] = min(100, zone["occupancy_percent"] + 22)
    zone["count"]             = round(zone["occupancy_percent"] * zone["capacity"] / 100)
    zone["wait_time_min"]     = min(45, zone["wait_time_min"] + 10)
    em = zone["emotion"]
    em["frustrated"] = min(60, em["frustrated"] + 18)
    em["happy"]      = max(5,  em["happy"]      - 12)
    em["neutral"]    = max(5,  em["neutral"]    - 6)
    em["avg_sentiment_score"] = round(max(0.15, em["avg_sentiment_score"] - 0.2), 2)
    zone["last_updated"] = _now()
    return True


def simulate_event(event_name: str) -> None:
    ctx = _store["match_context"]
    ctx["recent_event"]    = event_name
    ctx["current_minute"]  = min(120, ctx["current_minute"] + 2)
    if any(w in event_name.lower() for w in ["wicket", "out"]):
        ctx["overall_crowd_sentiment"] = round(max(0.3, ctx["overall_crowd_sentiment"] - 0.06), 2)
        ctx["crowd_density"] = "HIGH"
    elif any(w in event_name.lower() for w in ["six", "four", "boundary"]):
        ctx["overall_crowd_sentiment"] = round(min(1.0, ctx["overall_crowd_sentiment"] + 0.04), 2)


def tick_match() -> None:
    """Called by background task every 60 s to simulate live match progress."""
    ctx = _store["match_context"]

    # Advance overs/minute
    ctx["current_minute"] = min(120, ctx["current_minute"] + 1)

    # Update overs string from minute (rough approximation)
    over_num  = min(20, ctx["current_minute"] // 4)
    ball_num  = (ctx["current_minute"] % 4) * 1 + random.randint(0, 1)
    ball_num  = min(ball_num, 5)
    ctx["overs"] = f"{over_num}.{ball_num}"

    # Run rate drift
    ctx["run_rate"] = round(max(6.0, min(12.5, ctx["run_rate"] + random.uniform(-0.15, 0.15))), 1)

    # Slight zone occupancy drift (±3%) to feel live
    for zone in _store["zones"].values():
        drift = random.randint(-3, 3)
        zone["occupancy_percent"] = max(10, min(100, zone["occupancy_percent"] + drift))
        zone["count"] = round(zone["occupancy_percent"] * zone["capacity"] / 100)
        # Tiny wait time drift
        wdrift = random.randint(-1, 1)
        zone["wait_time_min"] = max(1, min(40, zone["wait_time_min"] + wdrift))
        zone["last_updated"] = _now()


def patch_match_context(data: dict) -> None:
    ctx = _store["match_context"]
    for key, value in data.items():
        ctx[key] = value
    ctx["_live_api"] = True


def reset() -> None:
    fresh = copy.deepcopy(_INITIAL_DATA)
    _store["zones"].clear()
    _store["zones"].update(fresh["zones"])
    _store["match_context"].clear()
    _store["match_context"].update(fresh["match_context"])
