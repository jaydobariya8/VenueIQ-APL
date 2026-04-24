import json
import os
from google import genai
from google.genai import types
import store

SYSTEM_PROMPT = """You are VenueIQ — the AI crowd intelligence agent for Narendra Modi Stadium, Ahmedabad during IPL 2026.

Venue zones:
- restroom_north (WC-N): Restroom Block A — North Stand, cap 60
- restroom_south (WC-S): Restroom Block B — South Stand, cap 60
- concession_main (FC-1): Main Concession Hall — Level 1 Concourse, cap 180
- concession_express (EK-E): Express Kiosk — East Wing, cap 80
- premium_pavilion (VIP-1): Premium Pavilion Lounge — Pavilion End, cap 90

Your job: give fans fast, actionable recommendations based on live occupancy, wait times, and crowd emotion data.

Rules:
1. Always call tools first — never guess zone data from memory
2. For specific zone questions: use get_zone_status; for comparisons or overviews: use get_all_zones
3. Factor in: occupancy %, wait_time_min, avg_sentiment_score, and upcoming break timing
4. Warn proactively: wicket → mass bathroom/food rush expected; innings break → 5 min warning
5. Response: 2-3 punchy sentences max. Lead with the number, follow with the insight.

Tone: Smart stadium friend who knows every shortcut. Witty but precise.

Example output: "Head to Restroom South (WC-S) — only 38% full, 2-min wait, crowd's happy. North block is 68% packed with a 7-min queue. Innings break in 38 min, so go now while it's calm."
"""

# Tool declarations as dicts (SDK converts automatically)
_TOOL_DEFS = [
    {
        "name": "get_zone_status",
        "description": "Get real-time status of a specific venue zone: occupancy %, count, wait time, and crowd emotion breakdown",
        "parameters": {
            "type": "object",
            "properties": {
                "zone_name": {
                    "type": "string",
                    "description": "Zone key. Must be one of: restroom_north, restroom_south, concession_main, concession_express, premium_pavilion",
                }
            },
            "required": ["zone_name"],
        },
    },
    {
        "name": "get_all_zones",
        "description": "Get real-time status of ALL venue zones at once — best for overview questions and comparison",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_match_context",
        "description": "Get current match timeline: minute, upcoming breaks, recent events, overall crowd sentiment and density",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "recommend_zone",
        "description": "Get top zone recommendations filtered by facility type and ranked by a priority metric",
        "parameters": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string",
                    "description": "Facility type: bathroom, food, seating, or any",
                },
                "priority": {
                    "type": "string",
                    "description": "Ranking metric: occupancy (least full), wait_time (shortest wait), sentiment (happiest crowd), or balanced (composite best)",
                },
            },
            "required": ["requirement", "priority"],
        },
    },
    {
        "name": "get_sentiment_insights",
        "description": "Rank all zones by avg crowd sentiment score — from happiest to most frustrated",
        "parameters": {"type": "object", "properties": {}},
    },
]


def _execute_tool(name: str, args: dict) -> str:
    if name == "get_zone_status":
        zone_name = args.get("zone_name", "")
        zone = store.get_zone(zone_name)
        return json.dumps(zone if zone else {"error": f"Zone '{zone_name}' not found. Valid: restroom_north, restroom_south, concession_main, concession_express, premium_pavilion"})

    if name == "get_all_zones":
        return json.dumps(store.get_all_zones())

    if name == "get_match_context":
        return json.dumps(store.get_match_context())

    if name == "recommend_zone":
        return json.dumps(_compute_recommendation(
            args.get("requirement", "any"),
            args.get("priority", "balanced"),
        ))

    if name == "get_sentiment_insights":
        zones = store.get_all_zones()
        ranked = sorted(
            [{"zone_key": k, **v} for k, v in zones.items()],
            key=lambda z: z["emotion"]["avg_sentiment_score"],
            reverse=True,
        )
        return json.dumps({
            "zones_by_sentiment": [
                {
                    "zone_key": z["zone_key"],
                    "name": z["name"],
                    "sentiment_score": z["emotion"]["avg_sentiment_score"],
                    "happy_pct": z["emotion"]["happy"],
                    "frustrated_pct": z["emotion"]["frustrated"],
                    "mood": "happy" if z["emotion"]["avg_sentiment_score"] >= 0.7 else "neutral" if z["emotion"]["avg_sentiment_score"] >= 0.5 else "frustrated",
                }
                for z in ranked
            ]
        })

    return json.dumps({"error": f"Unknown tool: {name}"})


def _compute_recommendation(requirement: str, priority: str) -> dict:
    zones = store.get_all_zones()
    type_filters = {
        "bathroom":  ["restroom_north", "restroom_south"],
        "restroom":  ["restroom_north", "restroom_south"],
        "food":      ["concession_main", "concession_express"],
        "concession":["concession_main", "concession_express"],
        "lounge":    ["premium_pavilion"],
        "seating":   ["premium_pavilion"],
        "any":       list(zones.keys()),
    }
    valid_keys = type_filters.get(requirement, list(zones.keys()))
    candidates = {k: v for k, v in zones.items() if k in valid_keys}

    if not candidates:
        return {"error": f"No zones found for requirement '{requirement}'"}

    sort_fns = {
        "occupancy": lambda item: item[1]["occupancy_percent"],
        "wait_time": lambda item: item[1]["wait_time_min"],
        "sentiment": lambda item: -item[1]["emotion"]["avg_sentiment_score"],
        "balanced": lambda item: (
            item[1]["occupancy_percent"] * 0.35
            + item[1]["wait_time_min"] * 1.2
            + (1 - item[1]["emotion"]["avg_sentiment_score"]) * 25
        ),
    }
    sort_key = sort_fns.get(priority, sort_fns["balanced"])
    sorted_zones = sorted(candidates.items(), key=sort_key)

    return {
        "best_options": [
            {
                "zone_key": k,
                "name": v["name"],
                "occupancy_percent": v["occupancy_percent"],
                "wait_time_min": v["wait_time_min"],
                "sentiment_score": v["emotion"]["avg_sentiment_score"],
                "happy_pct": v["emotion"]["happy"],
                "frustrated_pct": v["emotion"]["frustrated"],
                "reason": f"{v['occupancy_percent']}% full · {v['wait_time_min']} min wait · {v['emotion']['happy']}% happy crowd",
            }
            for k, v in sorted_zones[:2]
        ],
        "avoid": [
            {
                "zone_key": k,
                "name": v["name"],
                "occupancy_percent": v["occupancy_percent"],
                "wait_time_min": v["wait_time_min"],
                "reason": f"{v['occupancy_percent']}% full · {v['wait_time_min']} min wait · {v['emotion']['frustrated']}% frustrated",
            }
            for k, v in sorted_zones[-1:]
            if len(sorted_zones) > 1
        ],
    }


def _smart_fallback(user_message: str) -> dict:
    """Template-based answers using real zone data. Fires when Gemini quota is exhausted."""
    msg = user_message.lower()
    zones = store.get_all_zones()
    mc = store.get_match_context()
    break_in = mc.get("innings_break_minute", 90) - mc.get("current_minute", 0)

    def fmt(k, z):
        sm = z["emotion"]["avg_sentiment_score"]
        mood = "happy crowd 😊" if sm >= 0.7 else "neutral crowd 😐" if sm >= 0.5 else "frustrated crowd 😤"
        return f"{z['name']} ({z['zone_id']}): {z['occupancy_percent']}% full · {z['wait_time_min']} min wait · {mood}"

    # Bathroom / restroom
    if any(w in msg for w in ["bathroom", "restroom", "toilet", "wc", "washroom"]):
        rooms = {k: v for k, v in zones.items() if v["type"] == "restroom"}
        best = min(rooms.items(), key=lambda x: x[1]["occupancy_percent"] * 0.6 + x[1]["wait_time_min"] * 0.4)
        worst = max(rooms.items(), key=lambda x: x[1]["occupancy_percent"])
        k, z = best
        wk, wz = worst
        return {
            "answer": f"Go to {z['name']} ({z['zone_id']}) — {z['occupancy_percent']}% full, {z['wait_time_min']} min wait. "
                      f"{'Crowd is happy too. ' if z['emotion']['avg_sentiment_score'] >= 0.7 else ''}"
                      f"Skip {wz['name']} ({wz['zone_id']}): {wz['occupancy_percent']}% packed with {wz['wait_time_min']} min queue. "
                      f"Break in {break_in} min — move now.",
            "tools_used": ["recommend_zone"],
        }

    # Food / concession
    if any(w in msg for w in ["food", "eat", "hungry", "concession", "kiosk", "snack", "drink"]):
        food = {k: v for k, v in zones.items() if v["type"] == "food"}
        best = min(food.items(), key=lambda x: x[1]["wait_time_min"])
        worst = max(food.items(), key=lambda x: x[1]["wait_time_min"])
        k, z = best
        wk, wz = worst
        return {
            "answer": f"Head to {z['name']} ({z['zone_id']}) — only {z['wait_time_min']} min wait, {z['occupancy_percent']}% full. "
                      f"Avoid {wz['name']} ({wz['zone_id']}): {wz['wait_time_min']} min queue, {wz['emotion']['frustrated']}% fans frustrated. "
                      f"Innings break in {break_in} min — queues will spike after.",
            "tools_used": ["recommend_zone"],
        }

    # Sentiment / vibe
    if any(w in msg for w in ["feel", "mood", "vibe", "sentiment", "happy", "frustrated", "crowd"]):
        ranked = sorted(zones.items(), key=lambda x: x[1]["emotion"]["avg_sentiment_score"], reverse=True)
        best_k, best_z = ranked[0]
        worst_k, worst_z = ranked[-1]
        return {
            "answer": f"Overall venue vibe: {mc['overall_crowd_sentiment']:.2f}/1.0 — {mc['crowd_density']} density. "
                      f"Happiest zone: {best_z['name']} ({best_z['emotion']['avg_sentiment_score']:.2f}, {best_z['emotion']['happy']}% happy). "
                      f"Most frustrated: {worst_z['name']} ({worst_z['emotion']['frustrated']}% frustrated, {worst_z['wait_time_min']} min wait).",
            "tools_used": ["get_sentiment_insights"],
        }

    # Full report
    if any(w in msg for w in ["report", "status", "overview", "all", "everything"]):
        lines = [f"**Venue Status — {mc['score']} ({mc['overs']} ov) | Break in {break_in}m**\n"]
        for k, z in zones.items():
            lines.append(fmt(k, z))
        return {"answer": "\n".join(lines), "tools_used": ["get_all_zones", "get_match_context"]}

    # Match context
    if any(w in msg for w in ["match", "score", "over", "wicket", "run", "innings"]):
        return {
            "answer": f"{mc['team_a']} vs {mc['team_b']}: {mc['score']} in {mc['overs']} overs. "
                      f"Run rate: {mc['run_rate']}. {mc.get('next_break_type','Innings break')} in {break_in} min. "
                      f"Latest: {mc['recent_event']}.",
            "tools_used": ["get_match_context"],
        }

    # Default: best overall zone
    best = min(zones.items(), key=lambda x: x[1]["occupancy_percent"] * 0.4 + x[1]["wait_time_min"] * 0.6)
    k, z = best
    return {
        "answer": f"Quietest spot right now: {z['name']} ({z['zone_id']}) — {z['occupancy_percent']}% full, {z['wait_time_min']} min wait. "
                  f"Overall venue is {mc['crowd_density']} density. {mc['recent_event']}.",
        "tools_used": ["get_all_zones"],
    }


def run_agent(user_message: str) -> dict:
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    # Pass tools as raw dicts — SDK accepts and converts internally.
    # This avoids FunctionDeclaration/Schema version compatibility issues.
    tools_dict = [{"function_declarations": _TOOL_DEFS}]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools_dict,
        temperature=0.75,
    )

    # Conversation history as list of dicts (SDK handles conversion)
    contents: list[dict] = [
        {"role": "user", "parts": [{"text": user_message}]}
    ]
    tools_used: list[str] = []

    for _ in range(8):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=config,
            )
        except Exception as e:
            err = str(e)
            if any(c in err for c in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                return _smart_fallback(user_message)
            raise

        candidate = response.candidates[0]
        parts = candidate.content.parts

        # Serialize model turn back into dict for history
        model_parts = []
        fn_call_parts = []
        for p in parts:
            fc = getattr(p, "function_call", None)
            if fc and fc.name:
                fn_call_parts.append(p)
                model_parts.append({
                    "function_call": {
                        "name": fc.name,
                        "args": dict(fc.args),
                    }
                })
            elif getattr(p, "text", None):
                model_parts.append({"text": p.text})

        contents.append({"role": "model", "parts": model_parts})

        if not fn_call_parts:
            # Final answer — extract text
            text = " ".join(
                p.get("text", "") for p in model_parts if "text" in p
            ).strip()
            return {
                "answer": text,
                "tools_used": list(dict.fromkeys(tools_used)),  # deduplicated, order-preserved
            }

        # Execute all tool calls and add results
        fn_responses = []
        for p in fn_call_parts:
            fc = p.function_call
            tools_used.append(fc.name)
            result = _execute_tool(fc.name, dict(fc.args))
            fn_responses.append({
                "function_response": {
                    "name": fc.name,
                    "response": {"result": result},
                }
            })

        contents.append({"role": "user", "parts": fn_responses})

    return {
        "answer": "I hit my analysis limit. Try a more specific question.",
        "tools_used": list(dict.fromkeys(tools_used)),
    }
