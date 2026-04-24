import json
import os
from google import genai
from google.genai import types
import store

SYSTEM_PROMPT = """You are VenueIQ — a Stadium Crowd Intelligence Agent at an IPL cricket match venue in Ahmedabad.

Your mission: help fans navigate the venue by analysing real-time occupancy, wait times, and crowd emotions.

When making recommendations:
1. Fetch the data you need (zone status, match context, sentiment)
2. Factor in: occupancy %, wait time, crowd emotions, upcoming match events
3. Warn fans BEFORE crowd surges (wickets, breaks)
4. Be concise, witty, and actionable — like a smart friend who knows the stadium

Response style:
- Lead with the recommendation and the most important number
- Back it up with emotion insight (happy vs frustrated crowd)
- Always mention timing context (match minute, upcoming break)
- Keep it under 4 sentences. Punchy, not wordy.

Example: "Head to Bathroom South NOW — 45% full, 3 min wait, crowd's happy (0.80 sentiment). Skip Food B at all costs: 88% full, 22 min queue, people are fuming. Drinks break in 5 mins — grab food at Concourse A right after when it clears."
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
                    "description": "Zone key. Must be one of: bathroom_north, bathroom_south, food_concourse_a, food_concourse_b, seating_premium",
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
        return json.dumps(zone if zone else {"error": f"Zone '{zone_name}' not found. Valid: bathroom_north, bathroom_south, food_concourse_a, food_concourse_b, seating_premium"})

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
        "bathroom": ["bathroom_north", "bathroom_south"],
        "food": ["food_concourse_a", "food_concourse_b"],
        "seating": ["seating_premium"],
        "any": list(zones.keys()),
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
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=config,
        )

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
