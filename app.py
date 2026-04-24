from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import uvicorn
import store
from agent import run_agent

load_dotenv()

app = FastAPI(title="VenueIQ Crowd Intelligence", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Request models ────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str


class UpdateZoneRequest(BaseModel):
    zone_name: str
    patch: dict


class SimulateRequest(BaseModel):
    action: str           # "surge" | "event" | "reset"
    zone_name: str | None = None
    event_name: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.post("/ask")
async def ask(req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    result = run_agent(question)
    return result


@app.get("/zones")
async def zones():
    return store.get_all_zones()


@app.get("/stats")
async def stats():
    return store.get_stats()


@app.post("/update-zone")
async def update_zone(req: UpdateZoneRequest):
    ok = store.update_zone(req.zone_name, req.patch)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"Zone '{req.zone_name}' not found. Valid: bathroom_north, bathroom_south, food_concourse_a, food_concourse_b, seating_premium",
        )
    return {"status": "updated", "zone": store.get_zone(req.zone_name)}


@app.post("/simulate")
async def simulate(req: SimulateRequest):
    if req.action == "surge":
        if not req.zone_name:
            raise HTTPException(status_code=400, detail="zone_name required for surge action")
        ok = store.simulate_surge(req.zone_name)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Zone '{req.zone_name}' not found")
        return {"status": "surge simulated", "zone": store.get_zone(req.zone_name)}

    if req.action == "event":
        if not req.event_name:
            raise HTTPException(status_code=400, detail="event_name required for event action")
        store.simulate_event(req.event_name)
        return {"status": "event simulated", "match_context": store.get_match_context()}

    if req.action == "reset":
        store.reset()
        return {"status": "reset to initial demo state"}

    raise HTTPException(status_code=400, detail=f"Unknown action '{req.action}'. Use: surge, event, reset")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
