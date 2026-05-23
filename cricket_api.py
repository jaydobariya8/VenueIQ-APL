import json
import os
import urllib.request


_BASE = "https://api.cricapi.com/v1"


def fetch_live_match() -> dict | None:
    """
    Fetch live IPL/T20 match first; fall back to most recent completed match.
    Requires CRICKET_API_KEY in env. Free plan: 100 calls/day.
    Returns patch dict for store.patch_match_context(), or None.
    """
    key = os.getenv("CRICKET_API_KEY")
    if not key:
        return None

    try:
        url = f"{_BASE}/currentMatches?apikey={key}&offset=0"
        req = urllib.request.Request(url, headers={"User-Agent": "StadiumPulse/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())

        if data.get("status") != "success":
            return None

        matches = data.get("data", [])

        live = _pick_live(matches)
        if live:
            return _parse_live(live)

        completed = _pick_completed(matches)
        if completed:
            return _parse_completed(completed)

        return None
    except Exception:
        return None


def _is_completed(m: dict) -> bool:
    status = m.get("status", "").lower()
    return "won" in status or "draw" in status or "tie" in status or m.get("matchEnded", False)


def _pick_live(matches: list) -> dict | None:
    """Prefer live IPL match, then T20, then any live."""
    live_ipl, live_t20, any_live = None, None, None
    for m in matches:
        if _is_completed(m):
            continue
        name  = m.get("name", "").upper()
        mtype = m.get("matchType", "").lower()
        if "ipl" in name:
            live_ipl = m
        elif mtype == "t20":
            live_t20 = m
        else:
            any_live = m
    return live_ipl or live_t20 or any_live


def _pick_completed(matches: list) -> dict | None:
    """Pick most recent completed IPL/T20 match."""
    ipl, t20, any_done = None, None, None
    for m in matches:
        if not _is_completed(m):
            continue
        name  = m.get("name", "").upper()
        mtype = m.get("matchType", "").lower()
        if "ipl" in name and ipl is None:
            ipl = m
        elif mtype == "t20" and t20 is None:
            t20 = m
        elif any_done is None:
            any_done = m
    return ipl or t20 or any_done


def _parse_live(m: dict) -> dict:
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

        over_int   = int(o)
        balls      = round((o - over_int) * 10)
        real_overs = over_int + balls / 6
        if real_overs > 0:
            run_rate = round(r / real_overs, 1)

        if innings >= 2 and len(scores) >= 2:
            target = scores[0].get("r", 0) + 1

    return {
        "match_title":   m.get("name", "Live Match"),
        "match_status":  "live",
        "match_result":  None,
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


def _parse_completed(m: dict) -> dict:
    teams  = m.get("teams", ["TBD", "TBD"])
    team_a = teams[0] if teams else "TBD"
    team_b = teams[1] if len(teams) > 1 else "TBD"
    scores = m.get("score", [])

    score_a, score_b = "—", "—"
    if len(scores) >= 1:
        s = scores[0]
        score_a = f"{s.get('r', 0)}/{s.get('w', 0)} ({s.get('o', 0)} ov)"
    if len(scores) >= 2:
        s = scores[1]
        score_b = f"{s.get('r', 0)}/{s.get('w', 0)} ({s.get('o', 0)} ov)"

    return {
        "match_title":   m.get("name", "Recent Match"),
        "match_status":  "completed",
        "match_result":  m.get("status", "Match completed"),
        "team_a":        team_a,
        "team_b":        team_b,
        "score_a":       score_a,
        "score_b":       score_b,
        "batting_team":  team_a,
        "score":         score_a,
        "overs":         "—",
        "run_rate":      0.0,
        "innings":       2,
        "target":        None,
        "recent_event":  m.get("status", "Match completed"),
        "venue":         m.get("venue", _store_venue()),
    }


def _store_venue() -> str:
    try:
        import store
        return store.get_match_context().get("venue", "Narendra Modi Stadium, Ahmedabad")
    except Exception:
        return "Narendra Modi Stadium, Ahmedabad"
