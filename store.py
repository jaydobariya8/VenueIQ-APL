import copy
from datetime import datetime, timezone

_INITIAL_DATA = {
    "zones": {
        "bathroom_north": {
            "name": "Bathroom North",
            "occupancy_percent": 65,
            "count": 13,
            "capacity": 20,
            "wait_time_min": 8,
            "emotion": {
                "happy": 40,
                "neutral": 35,
                "sad": 15,
                "frustrated": 10,
                "avg_sentiment_score": 0.65,
            },
            "last_updated": "2026-04-24T19:30:00Z",
        },
        "bathroom_south": {
            "name": "Bathroom South",
            "occupancy_percent": 45,
            "count": 9,
            "capacity": 20,
            "wait_time_min": 3,
            "emotion": {
                "happy": 60,
                "neutral": 30,
                "sad": 5,
                "frustrated": 5,
                "avg_sentiment_score": 0.80,
            },
            "last_updated": "2026-04-24T19:30:00Z",
        },
        "food_concourse_a": {
            "name": "Food Concourse A",
            "occupancy_percent": 72,
            "count": 14,
            "capacity": 20,
            "wait_time_min": 15,
            "emotion": {
                "happy": 50,
                "neutral": 25,
                "sad": 10,
                "frustrated": 15,
                "avg_sentiment_score": 0.62,
            },
            "last_updated": "2026-04-24T19:30:00Z",
        },
        "food_concourse_b": {
            "name": "Food Concourse B",
            "occupancy_percent": 88,
            "count": 18,
            "capacity": 20,
            "wait_time_min": 22,
            "emotion": {
                "happy": 35,
                "neutral": 20,
                "sad": 20,
                "frustrated": 25,
                "avg_sentiment_score": 0.48,
            },
            "last_updated": "2026-04-24T19:30:00Z",
        },
        "seating_premium": {
            "name": "Premium Seating Area",
            "occupancy_percent": 95,
            "count": 19,
            "capacity": 20,
            "wait_time_min": 5,
            "emotion": {
                "happy": 75,
                "neutral": 20,
                "sad": 3,
                "frustrated": 2,
                "avg_sentiment_score": 0.88,
            },
            "last_updated": "2026-04-24T19:30:00Z",
        },
    },
    "match_context": {
        "current_minute": 45,
        "next_break_minute": 50,
        "team_a": "RCB",
        "team_b": "GT",
        "recent_event": "Wicket down! Crowd surge expected",
        "overall_crowd_sentiment": 0.72,
        "crowd_density": "HIGH",
    },
}

# Mutable in-place — never reassign _store at module level
_store: dict = copy.deepcopy(_INITIAL_DATA)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_zone(name: str) -> dict | None:
    return _store["zones"].get(name)


def get_all_zones() -> dict:
    return _store["zones"]


def get_match_context() -> dict:
    return _store["match_context"]


def update_zone(name: str, patch: dict) -> bool:
    zone = _store["zones"].get(name)
    if not zone:
        return False
    for key, value in patch.items():
        if key == "emotion" and isinstance(value, dict):
            zone["emotion"].update(value)
        else:
            zone[key] = value
    # Recalculate count from occupancy if not explicitly patched
    if "occupancy_percent" in patch and "count" not in patch:
        zone["count"] = round(zone["occupancy_percent"] * zone["capacity"] / 100)
    zone["last_updated"] = _now()
    return True


def simulate_surge(zone_name: str) -> bool:
    zone = _store["zones"].get(zone_name)
    if not zone:
        return False
    zone["occupancy_percent"] = min(100, zone["occupancy_percent"] + 20)
    zone["count"] = round(zone["occupancy_percent"] * zone["capacity"] / 100)
    zone["wait_time_min"] = min(60, zone["wait_time_min"] + 10)
    em = zone["emotion"]
    em["frustrated"] = min(60, em["frustrated"] + 15)
    em["happy"] = max(5, em["happy"] - 10)
    em["neutral"] = max(5, em["neutral"] - 5)
    em["avg_sentiment_score"] = round(max(0.15, em["avg_sentiment_score"] - 0.18), 2)
    zone["last_updated"] = _now()
    return True


def simulate_event(event_name: str) -> None:
    ctx = _store["match_context"]
    ctx["recent_event"] = event_name
    ctx["current_minute"] = min(120, ctx["current_minute"] + 2)
    # Wickets cause surges, boundaries cause joy
    if "wicket" in event_name.lower() or "out" in event_name.lower():
        ctx["overall_crowd_sentiment"] = round(max(0.3, ctx["overall_crowd_sentiment"] - 0.05), 2)
        ctx["crowd_density"] = "HIGH"
    elif "six" in event_name.lower() or "four" in event_name.lower():
        ctx["overall_crowd_sentiment"] = round(min(1.0, ctx["overall_crowd_sentiment"] + 0.05), 2)


def get_stats() -> dict:
    zones = _store["zones"]
    avg_occ = sum(z["occupancy_percent"] for z in zones.values()) / len(zones)
    avg_sent = sum(z["emotion"]["avg_sentiment_score"] for z in zones.values()) / len(zones)
    crowded = [k for k, v in zones.items() if v["occupancy_percent"] > 75]
    clear = [k for k, v in zones.items() if v["occupancy_percent"] < 50]
    density = "LOW" if avg_occ < 50 else "MEDIUM" if avg_occ < 72 else "HIGH"
    return {
        "avg_occupancy_percent": round(avg_occ, 1),
        "avg_sentiment_score": round(avg_sent, 2),
        "crowd_density": density,
        "crowded_zones": crowded,
        "clear_zones": clear,
        "total_zones": len(zones),
        "match_context": _store["match_context"],
    }


def reset() -> None:
    fresh = copy.deepcopy(_INITIAL_DATA)
    _store["zones"].clear()
    _store["zones"].update(fresh["zones"])
    _store["match_context"].clear()
    _store["match_context"].update(fresh["match_context"])
