from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import asyncio
import uvicorn
import cv2
import numpy as np
import store
import alerts as alert_engine
from agent import run_agent
from cricket_api import fetch_live_match

load_dotenv()


async def _match_ticker():
    while True:
        await asyncio.sleep(60)
        store.tick_match()


async def _cricket_poller():
    while True:
        data = await asyncio.to_thread(fetch_live_match)
        if data:
            store.patch_match_context(data)
        await asyncio.sleep(600)  # poll every 10 min (60 calls/day on free tier)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(_match_ticker()),
        asyncio.create_task(_cricket_poller()),
    ]
    yield
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="VenueIQ Crowd Intelligence", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialise detectors once at startup (not per-request)
_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
_hog = cv2.HOGDescriptor()
_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


# ── Request models ────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    role: str = "fan"


class UpdateZoneRequest(BaseModel):
    zone_name: str
    patch: dict


class SimulateRequest(BaseModel):
    action: str
    zone_name: str | None = None
    event_name: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    import os
    return {
        "status": "ok",
        "google_api_key": bool(os.getenv("GOOGLE_API_KEY")),
        "cricket_api_key": bool(os.getenv("CRICKET_API_KEY")),
    }


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/landing")
async def landing():
    return FileResponse("static/landing.html")


@app.get("/demo")
async def demo():
    return FileResponse("static/demo.html")


@app.post("/cv/detect")
async def cv_detect(file: UploadFile = File(...)):
    """
    Receives a JPEG frame from the browser, runs Google Cloud Vision API
    (falling back to local OpenCV if credentials are not configured),
    returns bounding boxes and count as JSON.
    """
    data = await file.read()
    nparr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"count": 0, "faces": [], "bodies": []}

    h, w = img.shape[:2]

    # Try Google Cloud Vision API first
    try:
        from google.cloud import vision
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=data)
        
        # 1. Object Localization to find people
        objects_response = client.object_localization(image=image)
        bodies = []
        for obj in objects_response.localized_object_annotations:
            if obj.name.lower() == "person":
                vertices = obj.bounding_poly.normalized_vertices
                if len(vertices) >= 4:
                    xs = [v.x * w for v in vertices]
                    ys = [v.y * h for v in vertices]
                    x_min, x_max = int(min(xs)), int(max(xs))
                    y_min, y_max = int(min(ys)), int(max(ys))
                    bodies.append({
                        "box": [x_min, y_min, x_max - x_min, y_max - y_min],
                        "score": float(obj.score)
                    })

        # 2. Face Detection
        face_response = client.face_detection(image=image)
        faces = []
        for face in face_response.face_annotations:
            vertices = face.bounding_poly.vertices
            if len(vertices) >= 4:
                xs = [v.x for v in vertices]
                ys = [v.y for v in vertices]
                x_min, x_max = int(min(xs)), int(max(xs))
                y_min, y_max = int(min(ys)), int(max(ys))
                
                fw, fh = x_max - x_min, y_max - y_min
                body_y = y_min
                body_h = min(int(fh * 4.5), h - y_min)
                
                faces.append({
                    "face_box": [x_min, y_min, fw, fh],
                    "body_box": [int(x_min - fw // 3), body_y, int(fw * 1.6), body_h],
                    "score": float(face.detection_confidence)
                })

        count = max(len(faces), len(bodies))
        return {
            "count": count,
            "faces": faces,
            "bodies": bodies,
            "frame": {"w": w, "h": h},
            "source": "google_cloud_vision"
        }
        
    except Exception:
        # Fallback to local OpenCV if Google Cloud Vision is not configured or errors out
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        faces_raw = _face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        faces = []
        if len(faces_raw):
            for (x, y, fw, fh) in faces_raw:
                body_y = y
                body_h = min(int(fh * 4.5), h - y)
                faces.append({
                    "face_box":  [int(x), int(y), int(fw), int(fh)],
                    "body_box":  [int(x - fw // 3), body_y, int(fw * 1.6), body_h],
                    "score":     0.9,
                })

        scale = min(1.0, 640 / w)
        small = cv2.resize(img, (int(w * scale), int(h * scale)))
        hog_boxes, hog_weights = _hog.detectMultiScale(
            small,
            winStride=(8, 8),
            padding=(4, 4),
            scale=1.05,
            finalThreshold=2,
        )
        bodies = []
        if len(hog_boxes):
            for i, (x, y, bw, bh) in enumerate(hog_boxes):
                bodies.append({
                    "box":   [int(x / scale), int(y / scale), int(bw / scale), int(bh / scale)],
                    "score": float(hog_weights[i]),
                })

        count = max(len(faces), len(bodies))
        return {
            "count":  count,
            "faces":  faces,
            "bodies": bodies,
            "frame":  {"w": w, "h": h},
            "source": "opencv_fallback"
        }


@app.post("/ask")
async def ask(req: AskRequest):
    question = req.question.strip()
    role = req.role.strip() if req.role else "fan"
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        result = await asyncio.to_thread(run_agent, question, role)
        return result
    except Exception as e:
        return {"answer": f"Agent error: {e}", "tools_used": []}


@app.get("/zones")
async def zones():
    return store.get_all_zones()


@app.get("/stats")
async def stats():
    return store.get_stats()


@app.get("/stats/predicted")
async def stats_predicted(horizon: int = 10):
    return store.get_predicted_state(horizon)


@app.post("/update-zone")
async def update_zone(req: UpdateZoneRequest):
    ok = store.update_zone(req.zone_name, req.patch)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"Zone '{req.zone_name}' not found.",
        )
    return {"status": "updated", "zone": store.get_zone(req.zone_name)}


@app.post("/simulate")
async def simulate(req: SimulateRequest):
    if req.action == "surge":
        if not req.zone_name:
            raise HTTPException(status_code=400, detail="zone_name required for surge")
        ok = store.simulate_surge(req.zone_name)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Zone '{req.zone_name}' not found")
        new_alerts = await asyncio.to_thread(alert_engine.check_and_generate)
        return {"status": "surge simulated", "zone": store.get_zone(req.zone_name), "new_alerts": new_alerts}

    if req.action == "event":
        if not req.event_name:
            raise HTTPException(status_code=400, detail="event_name required for event")
        store.simulate_event(req.event_name)
        return {"status": "event simulated", "match_context": store.get_match_context()}

    if req.action == "reset":
        store.reset()
        alert_engine.clear()
        return {"status": "reset to initial demo state"}

    raise HTTPException(status_code=400, detail=f"Unknown action '{req.action}'")


@app.get("/alerts")
async def get_alerts():
    return {"alerts": alert_engine.get_all()}


@app.post("/alerts/check")
async def check_alerts():
    new = await asyncio.to_thread(alert_engine.check_and_generate)
    return {"new_alerts": new, "all_alerts": alert_engine.get_all()}


@app.post("/alerts/acknowledge/{alert_id}")
async def acknowledge_alert(alert_id: str):
    ok = alert_engine.acknowledge(alert_id)
    return {"ok": ok}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
