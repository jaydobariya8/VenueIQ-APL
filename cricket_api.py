import json
import os
import urllib.request


_BASE = "https://api.cricapi.com/v1"


def fetch_live_match() -> dict | None:
    """
    Fetch current live/recent T20/IPL match from cricapi.com.
    Requires CRICKET_API_KEY in .env. Free plan: 100 calls/day.
    Returns patch dict for store.patch_match_context(), or None.
    """
    key = os.getenv("CRICKET_API_KEY")
    if not key:
        return None

    try:
        url = f"{_BASE}/currentMatches?apikey={key}&offset=0"
        req = urllib.request.Request(url, headers={"User-Agent": "VenueIQ/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())

        if data.get("status") != "success":
            return None

        matches = data.get("data", [])
        match = _pick_best(matches)
        if not match:
            return None

        return _parse(match)
    except Exception:
        return None


def _pick_best(matches: list) -> dict | None:
    """Prefer live IPL/T20 match; fall back to any live match."""
    live_ipl, live_t20, any_live = None, None, None
    for m in matches:
        name   = m.get("name", "").upper()
        status = m.get("status", "").lower()
        mtype  = m.get("matchType", "").lower()
        # skip completed matches
        if "won" in status or "draw" in status or "tie" in status:
            continue
        if "ipl" in name:
            live_ipl = m
        elif mtype == "t20":
            live_t20 = m
        else:
            any_live = m

    return live_ipl or live_t20 or any_live


def _parse(m: dict) -> dict:
    teams   = m.get("teams", ["TBD", "TBD"])
    team_a  = teams[0] if teams else "TBD"
    team_b  = teams[1] if len(teams) > 1 else "TBD"
    scores  = m.get("score", [])

    score_str    = "0/0"
    overs_str    = "0.0"
    run_rate     = 0.0
    batting_team = team_a
    innings      = 1
    target       = None

    if scores:
        curr         = scores[-1]
        innings      = len(scores)
        inning_label = curr.get("inning", "")
        r            = curr.get("r", 0)
        w            = curr.get("w", 0)
        o            = float(curr.get("o", 0))

        score_str = f"{r}/{w}"
        overs_str = str(o)

        for team in teams:
            if team.lower() in inning_label.lower():
                batting_team = team
                break

        # Real over count: 14.3 → 14 full + 3 balls = 14.5 overs
        over_int   = int(o)
        balls      = round((o - over_int) * 10)
        real_overs = over_int + balls / 6
        if real_overs > 0:
            run_rate = round(r / real_overs, 1)

        if innings >= 2 and len(scores) >= 2:
            target = scores[0].get("r", 0) + 1

    return {
        "match_title":   m.get("name", "Live Match"),
        "team_a":        team_a,
        "team_b":        team_b,
        "batting_team":  batting_team,
        "score":         score_str,
        "overs":         overs_str,
        "run_rate":      run_rate,
        "innings":       innings,
        "target":        target,
        "recent_event":  m.get("status", "Match in progress"),
        "venue":         m.get("venue", _store_venue()),
    }


def _store_venue() -> str:
    try:
        import store
        return store.get_match_context().get("venue", "Narendra Modi Stadium, Ahmedabad")
    except Exception:
        return "Narendra Modi Stadium, Ahmedabad"
