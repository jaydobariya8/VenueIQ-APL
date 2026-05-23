import json
import os
from google import genai
from google.genai import types
import store

# ── Agent System Prompts ──────────────────────────────────────────────────────

SYSTEM_PROMPT_ROUTING = """You are StadiumPulse's specialized Routing Agent (Gemini 2.5 Flash).
Your focus is spectator crowd flow, zone wait times, concessions shortcuts, and exit gate navigation at Narendra Modi Stadium.
You are helpful, witty, and extremely fast.

Rules:
1. Always call tools first — never guess zone or gate data from memory.
2. For routing out of the stadium: prioritize open exits. If Gate 3 is BLOCKED, dynamically suggest other open gates.
3. Keep answers friendly, snappy, and very concise (2-3 sentences max).
"""

SYSTEM_PROMPT_COMMS = """You are StadiumPulse's Sentiment & Comms Agent (Gemini 2.5 Flash).
Your focus is stadium vibe, fan sentiment, general match context, and public address (PA) system broadcasts.
You are energetic, engaging, and stadium-smart.

Rules:
1. Always call tools first — never guess stadium sentiment or match stats from memory.
2. Formulate engaging, calming, or celebrating fan announcements when requested.
3. Keep answers witty and brief (2-3 sentences max).
"""

SYSTEM_PROMPT_COMMANDER = """You are the StadiumPulse Incident Commander (Gemini 2.5 Pro).
You handle high-stakes safety scenarios, severe crowd surges, weather threats (e.g., storms), and exit blockages.
You have maximum authority and access to all tools to reason over complex safety telemetry.

Rules:
1. Always analyze telemetry and gate statuses before responding.
2. Provide authoritative, precise, and highly actionable operational plans for staff and volunteers.
3. Formulate clear, safe routing instructions for fans to avoid danger points (like blocked Gate 3).
4. Keep replies extremely decisive and structured (2-3 sentences max).
"""

# ── Tool Definitions ──────────────────────────────────────────────────────────

_TOOL_DEFS = {
    "get_zone_status": {
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
    "get_all_zones": {
        "name": "get_all_zones",
        "description": "Get real-time status of ALL venue zones at once — best for overview questions and comparison",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_match_context": {
        "name": "get_match_context",
        "description": "Get current match timeline: score, overs, run rate, upcoming breaks, recent events, overall crowd sentiment and density",
        "parameters": {"type": "object", "properties": {}},
    },
    "recommend_zone": {
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
    "get_sentiment_insights": {
        "name": "get_sentiment_insights",
        "description": "Rank all zones by avg crowd sentiment score — from happiest to most frustrated",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_gate_status": {
        "name": "get_gate_status",
        "description": "Get real-time queue counts and operational status (OPEN/BLOCKED) of all stadium entry/exit gates",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_evacuation_routes": {
        "name": "get_evacuation_routes",
        "description": "Get optimized evacuation instructions and open exits when stadium-wide emergency mode is active",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_crowd_predictions": {
        "name": "get_crowd_predictions",
        "description": "Predict stadium-wide zone occupancy and queue wait times 5, 10, or 15 minutes into the future based on match timelines.",
        "parameters": {
            "type": "object",
            "properties": {
                "horizon_minutes": {
                    "type": "integer",
                    "description": "The forecast time horizon in minutes (e.g. 5, 10, 15, or 20 minutes).",
                }
            },
            "required": ["horizon_minutes"],
        },
    },
}

# ── Tool Mappings per Agent ───────────────────────────────────────────────────

AGENT_TOOLS_MAPPING = {
    "routing": ["get_zone_status", "recommend_zone", "get_all_zones", "get_gate_status", "get_crowd_predictions"],
    "comms": ["get_sentiment_insights", "get_match_context"],
    "commander": ["get_zone_status", "get_all_zones", "get_match_context", "recommend_zone", "get_sentiment_insights", "get_gate_status", "get_evacuation_routes", "get_crowd_predictions"]
}

# ── Tool Execution logic ──────────────────────────────────────────────────────

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

    if name == "get_gate_status":
        return json.dumps(store.get_gates())

    if name == "get_evacuation_routes":
        st = store.get_stadium_state()
        if not st["emergency_mode"]:
            return json.dumps({"status": "NORMAL", "message": "Stadium is operating under normal parameters. No evacuation active."})
        
        gates = st["gates"]
        open_gates = [k for k, v in gates.items() if v["status"] == "OPEN"]
        blocked_gates = [k for k, v in gates.items() if v["status"] == "BLOCKED"]
        
        ranked_open = sorted(
            [{"gate_key": k, **v} for k, v in gates.items() if k in open_gates],
            key=lambda g: g["queue_count"]
        )
        
        return json.dumps({
            "status": "EMERGENCY_EVACUATION",
            "emergency_type": st["emergency_type"],
            "weather": st["weather"],
            "recommended_exits": [
                {
                    "gate": g["gate_key"],
                    "name": g["name"],
                    "queue": g["queue_count"],
                    "instructions": f"Route fans to {g['name']}. Low traffic queue of {g['queue_count']} fans."
                }
                for g in ranked_open
            ],
            "danger_exits": [
                {
                    "gate": g,
                    "name": gates[g]["name"],
                    "reason": "BLOCKED" if gates[g]["status"] == "BLOCKED" else "HEAVILY CONGESTED"
                }
                for g in blocked_gates
            ]
        })

    if name == "get_crowd_predictions":
        horizon = int(args.get("horizon_minutes", 10))
        pred = store.get_predicted_state(horizon)
        summary = {
            "time_horizon_minutes": horizon,
            "overall_prediction": f"Expected average occupancy will be {pred['avg_occupancy_percent']}% with overall {pred['crowd_density']} density. Average crowd sentiment score: {pred['avg_sentiment_score']}/1.0.",
            "crowded_zones_forecasted": [
                {
                    "zone_key": k,
                    "name": z["name"],
                    "predicted_occupancy": f"{z['occupancy_percent']}%",
                    "predicted_wait_time": f"{z['wait_time_min']} mins",
                    "status": "CRITICAL SURGE Expected" if z["occupancy_percent"] >= 85 else "WARNING expected"
                }
                for k, z in pred["zones"].items() if k in pred["crowded_zones"]
            ],
            "clear_zones_forecasted": [
                {
                    "zone_key": k,
                    "name": z["name"],
                    "predicted_occupancy": f"{z['occupancy_percent']}%",
                    "predicted_wait_time": f"{z['wait_time_min']} mins"
                }
                for k, z in pred["zones"].items() if k in pred["clear_zones"]
            ]
        }
        return json.dumps(summary)

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

# ── Dynamic Query Classifier & Routing ────────────────────────────────────────

def classify_query(user_message: str) -> str:
    # 1. Proactive override: If emergency mode is active, always escalate to Incident Commander!
    st = store.get_stadium_state()
    if st.get("emergency_mode", False):
        return "commander"

    # 2. Ask Gemini to classify
    try:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        prompt = f"""You are the central dispatcher for StadiumPulse Command Center.
Classify the following user query into one of three specialized agents:
- "routing": If the query asks for directions, wait times, shortcuts, closest bathrooms, food concourse recommendations, entry/exit gates, or transit exits.
- "comms": If the query asks about overall crowd sentiment, general match vibes, timing of breaks, score context, or public address (PA) announcements.
- "commander": If the query involves active emergencies, rain storms, blocked gates, safety incidents, overcrowding warnings, or staff deployment plans.

Respond with exactly one word from this list: routing, comms, commander. Do not include markdown fences or any other text.
Query: "{user_message}"
Classification:"""
        
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        ans = resp.text.strip().lower()
        if "routing" in ans:
            return "routing"
        if "comms" in ans:
            return "comms"
        if "commander" in ans:
            return "commander"
    except Exception:
        pass

    # Simple fallback heuristic regex
    msg = user_message.lower()
    if any(w in msg for w in ["rain", "storm", "emergency", "fire", "breach", "block", "steward", "deploy", "commander", "evacuate"]):
        return "commander"
    if any(w in msg for w in ["feel", "vibe", "mood", "sentiment", "announcement", "score", "over", "wicket"]):
        return "comms"
    return "routing"

# ── Fallback templates ────────────────────────────────────────────────────────

def _smart_fallback(user_message: str, agent_used: str) -> dict:
    msg = user_message.lower()
    zones = store.get_all_zones()
    mc = store.get_match_context()
    break_in = mc.get("innings_break_minute", 90) - mc.get("current_minute", 0)

    if agent_used == "commander" or any(w in msg for w in ["bathroom", "restroom", "toilet", "wc"]):
        rooms = {k: v for k, v in zones.items() if v["type"] == "restroom"}
        best = min(rooms.items(), key=lambda x: x[1]["occupancy_percent"] * 0.6 + x[1]["wait_time_min"] * 0.4)
        worst = max(rooms.items(), key=lambda x: x[1]["occupancy_percent"])
        k, z = best
        wk, wz = worst
        return {
            "answer": f"[🛡️ Incident Commander Fallback] Head to {z['name']} — {z['occupancy_percent']}% full, {z['wait_time_min']}m queue. Avoid {wz['name']} which is heavily congested at {wz['occupancy_percent']}% full.",
            "agent_used": "commander",
            "tools_used": ["recommend_zone"],
        }

    if any(w in msg for w in ["food", "eat", "hungry", "concession"]):
        food = {k: v for k, v in zones.items() if v["type"] == "food"}
        best = min(food.items(), key=lambda x: x[1]["wait_time_min"])
        k, z = best
        return {
            "answer": f"[🧭 Routing Fallback] Head to {z['name']} — shortest wait time of {z['wait_time_min']}m, currently {z['occupancy_percent']}% full.",
            "agent_used": "routing",
            "tools_used": ["recommend_zone"],
        }

    return {
        "answer": f"[📢 Comms Fallback] Stadium atmosphere is currently {mc['overall_crowd_sentiment']*100:.0f}% positive. Match score is {mc['score']} in over {mc['overs']}.",
        "agent_used": "comms",
        "tools_used": ["get_match_context"]
    }

# ── Primary Agent Run Loop ────────────────────────────────────────────────────

def run_agent(user_message: str, role: str = "fan") -> dict:
    # 1. Determine specialized agent to route to
    agent_used = classify_query(user_message)

    # 2. Select model and prompt
    if agent_used == "commander":
        model_name = "gemini-2.5-pro"
        system_instruction = SYSTEM_PROMPT_COMMANDER
    elif agent_used == "comms":
        model_name = "gemini-2.5-flash"
        system_instruction = SYSTEM_PROMPT_COMMS
    else:
        model_name = "gemini-2.5-flash"
        system_instruction = SYSTEM_PROMPT_ROUTING

    # 3. Compile tools mapping
    agent_tool_names = AGENT_TOOLS_MAPPING[agent_used]
    agent_tool_defs = [_TOOL_DEFS[t] for t in agent_tool_names]
    tools_dict = [{"function_declarations": agent_tool_defs}]

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools_dict,
        temperature=0.7,
    )

    contents: list[dict] = [
        {"role": "user", "parts": [{"text": user_message}]}
      ]
    tools_used: list[str] = []

    for _ in range(8):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
        except Exception as e:
            err = str(e)
            if any(c in err for c in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota"]):
                return _smart_fallback(user_message, agent_used)
            raise

        candidate = response.candidates[0]
        parts = candidate.content.parts

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
            # Extraction
            text = " ".join(
                p.get("text", "") for p in model_parts if "text" in p
            ).strip()
            return {
                "answer": text,
                "agent_used": agent_used,
                "tools_used": list(dict.fromkeys(tools_used)),
            }

        # Executions
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
        "agent_used": agent_used,
        "tools_used": list(dict.fromkeys(tools_used)),
    }
