# VenueIQ — Crowd Intelligence Agentic System

> Real-time stadium crowd intelligence powered by Gemini 2.0 Flash + FastAPI.  
> Built for the **Build with AI** hackathon, Ahmedabad 2026.

---

## Quick Start (Local)

### 1. Get a free Gemini API key
Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → **Create API Key** → copy it.

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env and paste your key:
# GOOGLE_API_KEY=AIza...your_key_here
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run
```bash
python app.py
```

Open **http://localhost:8000** in your browser.

---

## Test the Agent (curl)

```bash
# Get all zone statuses
curl http://localhost:8000/zones

# Ask the agent a question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Where should I go to the bathroom right now?"}'

# Simulate a crowd surge at Food B
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"action": "surge", "zone_name": "food_concourse_b"}'

# Simulate a match event
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"action": "event", "event_name": "WICKET! Kohli out for 45"}'

# Reset all data to initial state
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"action": "reset"}'
```

---

## Deploy to Google Cloud Run

### Prerequisites
```bash
# Install gcloud CLI: https://cloud.google.com/sdk/docs/install
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### Deploy (one command)
```bash
gcloud run deploy venueiq \
  --source . \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY=YOUR_KEY_HERE \
  --port 8080 \
  --memory 512Mi
```

### Or build + push Docker manually
```bash
docker build -t venueiq .
docker run -p 8080:8080 -e GOOGLE_API_KEY=your_key venueiq
```

---

## API Reference

| Method | Path | Body | Description |
|--------|------|------|-------------|
| GET | `/zones` | — | All zone statuses |
| GET | `/stats` | — | Venue stats + match context |
| POST | `/ask` | `{"question": "..."}` | Run agent, get recommendation |
| POST | `/update-zone` | `{"zone_name": "...", "patch": {...}}` | Update any zone field |
| POST | `/simulate` | `{"action": "surge", "zone_name": "..."}` | Simulate crowd surge |
| POST | `/simulate` | `{"action": "event", "event_name": "..."}` | Simulate match event |
| POST | `/simulate` | `{"action": "reset"}` | Reset to initial data |

---

## Demo Script (Hackathon Walkthrough)

**Step 1 — Opening**  
Open dashboard. Point to 5 zone cards with live occupancy bars and emotion breakdown.

**Step 2 — Basic question**
> "Where should I go to the bathroom right now?"

Watch agent call `get_all_zones` + `recommend_zone` tools. See tool chips appear under response.

**Step 3 — Surge simulation**
Click **🌊 Surge Food B** in Demo Controls. Watch Food B card turn red instantly.

> "I'm hungry, which food area should I go to?"

Agent now recommends Food A instead of B. Shows system adapting to real-time data.

**Step 4 — Match event**
Click **💀 Wicket! Key batsman out**. Match context updates.

> "Wicket just fell — what should I do in the next 5 minutes?"

Agent considers match timing and warns about crowd surge before giving routing advice.

**Step 5 — Full report**
> "Give me a full venue status report"

Agent calls multiple tools: `get_all_zones`, `get_match_context`, `get_sentiment_insights`. Shows tool use chain.

**Step 6 — Sentiment question**
> "Which zone has the most frustrated fans right now?"

Shows emotion/sentiment intelligence, not just occupancy.

---

## Architecture

```
Browser (React + Tailwind CDN)
    │
    ├── GET /zones, /stats (auto-refresh every 10s)
    └── POST /ask ──► FastAPI ──► agent.py
                                     │
                    ┌────────────────┴──────────────────┐
                    │         Gemini 2.0 Flash           │
                    │    (tool use agentic loop)         │
                    └──────────────┬────────────────────┘
                                   │ calls
                    ┌──────────────▼────────────────────┐
                    │           store.py                 │
                    │    (in-memory zone + match data)   │
                    └────────────────────────────────────┘
```

## Agent Tools

| Tool | What it does |
|------|-------------|
| `get_zone_status` | Single zone: occupancy, wait time, emotions |
| `get_all_zones` | All 5 zones at once |
| `get_match_context` | Match timeline, breaks, recent events |
| `recommend_zone` | Filter by type + sort by priority metric |
| `get_sentiment_insights` | Rank zones by crowd mood |
