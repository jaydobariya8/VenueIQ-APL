<div align="center">

# 🏟️ VenueIQ — AI Crowd Intelligence

### Real-time stadium crowd intelligence powered by Google Gemini AI

[![Live Demo](https://img.shields.io/badge/🚀%20Live%20Demo-venueiq.run.app-orange?style=for-the-badge)](https://venueiq-740813524695.asia-south1.run.app/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Gemini](https://img.shields.io/badge/Gemini-2.5%20Flash-purple?style=for-the-badge&logo=google)](https://aistudio.google.com)
[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-Deployed-4285F4?style=for-the-badge&logo=google-cloud)](https://cloud.google.com/run)

> **Built for Build with AI Hackathon, Ahmedabad 2026**  
> An agentic AI system that monitors crowd flow at Narendra Modi Stadium during IPL 2026 — giving fans smart routing advice and ops teams real-time alerts before problems escalate.

**[🔴 Try it Live →](https://venueiq-740813524695.asia-south1.run.app/)**

</div>

---

## 📸 What It Does

VenueIQ is an end-to-end **AI crowd intelligence platform** for large-scale stadium events. It combines real-time occupancy data, crowd sentiment analysis, live cricket match context, and a Gemini-powered conversational agent to:

- **Guide fans** — "Where's the shortest bathroom queue right now?" answered in 2 seconds with live data
- **Warn ops teams** — Auto-generated AI alerts when zones hit critical occupancy, with staff action plans and PA broadcast text
- **Predict surges** — Factors in match events (wickets, boundaries, innings breaks) to proactively reroute crowds before queues form
- **Detect people** — OpenCV computer vision demo detects people and faces from a live camera feed

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🤖 **Gemini Agentic Loop** | Multi-step tool-use: agent picks the right tools, executes them, synthesizes a response |
| 📊 **Live Zone Dashboard** | 5 venue zones with occupancy gauges, emotion breakdowns, wait times — auto-refreshes every 10s |
| 🔔 **AI Alert Engine** | Gemini generates staff alerts + PA announcements when zones breach thresholds |
| 😊 **Crowd Emotion Analysis** | Per-zone sentiment: happy / neutral / sad / frustrated breakdown with avg score |
| 🏏 **Live Cricket Data** | Integrates cricapi.com for real match scores, overs, run rate, batting team |
| 📷 **CV People Detection** | OpenCV HOG + Haar Cascade detector — upload a frame, get bounding boxes + count |
| ⚡ **Smart Fallback** | Template-based answers using real data when Gemini quota is exhausted — demo never breaks |
| 🐳 **Docker + Cloud Run** | One-command deploy to Google Cloud Run |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (React 18 CDN)                    │
│                                                                   │
│   ┌──────────────────┐   ┌─────────────┐   ┌────────────────┐   │
│   │  Zone Dashboard  │   │ Floating    │   │  Demo Controls │   │
│   │  (5 zone cards)  │   │ AI Chatbot  │   │  (surge/event) │   │
│   └────────┬─────────┘   └──────┬──────┘   └───────┬────────┘   │
│            │ GET /zones         │ POST /ask         │ POST /sim  │
└────────────┼────────────────────┼───────────────────┼────────────┘
             │                    │                   │
             ▼                    ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (app.py)                    │
│                                                                   │
│   /zones  /stats  /ask  /simulate  /alerts  /cv/detect           │
└──────────┬─────────────────┬──────────────────┬─────────────────┘
           │                 │                  │
           ▼                 ▼                  ▼
    ┌─────────────┐  ┌───────────────┐  ┌──────────────────┐
    │   store.py  │  │   agent.py    │  │   alerts.py      │
    │             │  │               │  │                  │
    │ In-memory   │  │ Gemini 2.5    │  │ Threshold check  │
    │ zone data   │  │ Flash tool    │  │ → Gemini alert   │
    │ + match ctx │  │ use loop      │  │   generation     │
    │ + tick()    │  │               │  │ 15-min cooldown  │
    └──────┬──────┘  └───────┬───────┘  └──────────────────┘
           │                 │
           ▼                 ▼
    ┌─────────────┐  ┌───────────────┐
    │ cricket_api │  │  Google       │
    │ .py         │  │  Gemini API   │
    │             │  │               │
    │ cricapi.com │  │ Tool calls:   │
    │ live scores │  │ get_zone_*    │
    │ (10m poll)  │  │ recommend_*   │
    │             │  │ get_match_*   │
    └─────────────┘  └───────────────┘
```

---

## 🤖 Gemini Agentic Tool-Use Flow

```
User: "I'm hungry — where should I go?"
          │
          ▼
┌─────────────────────┐
│   Gemini 2.5 Flash  │
│   Thinks: need food │
│   zone + priority   │
└──────────┬──────────┘
           │ calls tool
           ▼
┌─────────────────────┐
│  recommend_zone(    │
│    requirement=     │   ──► store.get_all_zones()
│      "food",        │         filter: concession zones
│    priority=        │         sort: by wait_time_min
│      "wait_time"    │         return: top 2 + avoid 1
│  )                  │
└──────────┬──────────┘
           │ tool result
           ▼
┌─────────────────────┐
│   Gemini synthesizes│
│   punchy 2-sentence │
│   recommendation    │
└──────────┬──────────┘
           │
           ▼
"Head to Express Kiosk (EK-E) — only 3 min wait,
 42% full, crowd's happy 😊. Skip Main Concession:
 18 min queue, innings break in 12m — go now."
```

---

## 🔔 AI Alert Pipeline

```
Background tick (every 60s) drifts zone data
          │
          ▼ (on surge or manual check)
┌──────────────────────────────────┐
│         alerts.check_and_generate()          │
│                                  │
│  zone.occupancy >= 85% → HIGH    │
│  zone.wait_time >= 15m  → MEDIUM │
│  zone.sentiment <= 0.45 → MEDIUM │
│                                  │
│  _recently_alerted()? → skip     │
│  (15-min per-zone cooldown)      │
└──────────────┬───────────────────┘
               │
               ▼
    ┌──────────────────────┐
    │   Gemini generates   │
    │                      │
    │  staff_alert: 1 line │  → Ops team action
    │  pa_message:  1 line │  → PA system broadcast
    │  action: enum        │  → deploy_staff / redirect
    └──────────┬───────────┘
               │
               ▼
    Toast notification + 🔔 Bell badge + Alert Panel
```

---

## 🗂️ Project Structure

```
VenueIQ-APL/
├── app.py              # FastAPI routes + async lifespan tasks
├── agent.py            # Gemini agentic loop + 5 tool definitions + smart fallback
├── alerts.py           # Alert engine: threshold checks + Gemini alert generation
├── store.py            # In-memory data store: zones, match context, tick/drift
├── cricket_api.py      # cricapi.com live match data poller
├── static/
│   ├── index.html      # React 18 CDN dashboard (no build step)
│   └── demo.html       # OpenCV CV people detection demo
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **AI Agent** | Google Gemini 2.5 Flash — function calling / tool use |
| **Backend** | FastAPI + Uvicorn (async Python) |
| **Computer Vision** | OpenCV — HOG people detector + Haar Cascade face detector |
| **Frontend** | React 18 (CDN) + Babel Standalone — no build step |
| **Live Data** | cricapi.com REST API (free tier, 100 calls/day) |
| **Deployment** | Google Cloud Run — serverless containers |
| **State** | In-memory Python dict (demo-optimized, no DB needed) |

---

## 🤖 Agent Tool Reference

| Tool | Trigger | What It Does |
|---|---|---|
| `get_zone_status` | Specific zone question | Returns occupancy %, count, wait time, full emotion breakdown for one zone |
| `get_all_zones` | Overview / comparison | Returns all 5 zones at once — best for "which is best?" questions |
| `get_match_context` | Match / timing questions | Current score, overs, run rate, next break, recent event, crowd density |
| `recommend_zone` | "Where should I go?" | Filters by type (bathroom/food/lounge), ranks by priority (occupancy/wait/sentiment/balanced) |
| `get_sentiment_insights` | Mood / vibe questions | Ranks all zones happiest → most frustrated with mood labels |

---

## 🚀 Quick Start (Local)

### Prerequisites
- Python 3.11+
- Free Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/VenueIQ-APL.git
cd VenueIQ-APL

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
```env
GOOGLE_API_KEY=AIza...your_key_here

# Optional: live cricket data (100 calls/day free)
# https://cricapi.com → Sign up → Dashboard → API Key
CRICKET_API_KEY=your_cricapi_key_here
```

### 3. Run

```bash
python app.py
```

Open **http://localhost:8000** — dashboard loads instantly.

---

## 📡 API Reference

| Method | Endpoint | Body | Description |
|---|---|---|---|
| `GET` | `/` | — | Dashboard UI |
| `GET` | `/health` | — | Server + API key status |
| `GET` | `/zones` | — | All 5 zone statuses |
| `GET` | `/stats` | — | Venue aggregates + match context |
| `POST` | `/ask` | `{"question": "..."}` | Run Gemini agent, get recommendation |
| `POST` | `/simulate` | `{"action": "surge", "zone_name": "..."}` | Simulate crowd surge in a zone |
| `POST` | `/simulate` | `{"action": "event", "event_name": "..."}` | Simulate match event |
| `POST` | `/simulate` | `{"action": "reset"}` | Reset all data to initial state |
| `GET` | `/alerts` | — | All active alerts |
| `POST` | `/alerts/check` | — | Force threshold check + generate alerts |
| `POST` | `/alerts/acknowledge/{id}` | — | Acknowledge an alert |
| `POST` | `/cv/detect` | `multipart/form-data (image)` | People + face detection |

### Example: Ask the agent

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Where should I go to the bathroom right now?"}'
```

```json
{
  "answer": "Head to Restroom South (WC-S) — only 38% full, 2-min wait, crowd's happy 😊. Skip Restroom North: 71% packed with a 9-min queue. Innings break in 14m — go now while it's calm.",
  "tools_used": ["recommend_zone"]
}
```

### Example: Simulate a surge

```bash
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"action": "surge", "zone_name": "concession_main"}'
```

---

## 🎬 Demo Walkthrough (Hackathon Script)

**Step 1 — Dashboard overview**  
Open the live URL. Point to 5 zone cards: circular occupancy gauges, emotion bars (😊😐😞😤), wait times, live-dot pulsing green/yellow/red.

**Step 2 — Ask the AI chatbot** (💬 button, bottom-right)  
Click the orange 💬 FAB. Type or click a suggestion chip:
> *"Where should I go to the bathroom right now?"*

Watch the agent call `recommend_zone` tool → synthesize a 2-sentence answer with live data. Tool chips appear under the response.

**Step 3 — Trigger a crowd surge** (⚙️ button, bottom-left)  
Click ⚙️ → **Simulate Surge → 🍕 Main Concession (FC-1)**. Zone card flips red instantly. A Gemini-generated 🔔 alert appears with staff action + PA announcement text.

**Step 4 — Ask again with new data**  
> *"I'm hungry — which food area should I go to?"*

Agent now routes to Express Kiosk instead, adapting to the surge. Shows real-time data intelligence.

**Step 5 — Match event**  
Click ⚙️ → **🏏 Wicket!** Match context updates. Ask:
> *"Wicket just fell — what should I do in the next 5 minutes?"*

Agent factors in crowd surge timing and innings break to give proactive advice.

**Step 6 — Full venue report**  
> *"Give me a full venue status report"*

Agent chains 3 tools: `get_all_zones` + `get_match_context` + `get_sentiment_insights`. Shows multi-step agentic reasoning.

---

## 🐳 Docker

```bash
docker build -t venueiq .
docker run -p 8080:8080 \
  -e GOOGLE_API_KEY=your_key \
  venueiq
```

Open **http://localhost:8080**

---

## ☁️ Deploy to Google Cloud Run

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud run deploy venueiq \
  --source . \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=YOUR_KEY \
  --port 8080 \
  --memory 512Mi
```

---

## 📋 Pre-planned Demo Questions

Copy-paste these during a live demo:

```
1. Where should I go to the bathroom right now?
2. Which food area has the shortest wait?
3. How is the overall crowd feeling?
4. Wicket just fell — what should I do in the next 5 minutes?
5. Which zone has the most frustrated fans?
6. Give me a full venue status report
7. Is the premium pavilion worth visiting right now?
8. How much time until the innings break?
```

---

## 🧠 Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| AI model | Gemini 2.5 Flash | Free tier, best function-calling quality, separate quota pool |
| No streaming | Single response | Simpler demo, tool-use loop needs full responses |
| In-memory state | Python dict | No DB setup for hackathon, instant resets, simple diffs |
| Smart fallback | Template answers | Demo never fails even when Gemini quota hits 0 |
| Alert cooldown | 15 min per zone | Prevents spam, keeps alerts actionable |
| CDN React | No build step | Live demo ready in seconds, works anywhere |
| Auto-refresh | 10s polling | Simple, reliable, no WebSocket complexity |

---

<div align="center">

**Built with ❤️ for Build with AI Hackathon, Ahmedabad 2026**

[🔴 Live Demo](https://venueiq-740813524695.asia-south1.run.app/) · [📷 CV Demo](https://venueiq-740813524695.asia-south1.run.app/demo)

</div>
