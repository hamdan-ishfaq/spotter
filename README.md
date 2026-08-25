# Spotter HOS Trip Planner

Full-stack **React + Django** assessment app: plan a property-carrying trip under FMCSA-style **70h/8-day** HOS rules, show the route/stops on a map, and **draw** multi-day Driver’s Daily Logs.

Specs: [HANDOFF.md](./HANDOFF.md) · [PRD.md](./PRD.md) · [TRD.md](./TRD.md) · [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)

## Features
- Inputs: current / pickup / dropoff / cycle hours used (+ start time)
- Geocode + route via free APIs (ORS when available; otherwise Nominatim + OSRM). Free-tier routing typically uses the **car** profile — HGV/truck profile is attempted first but is often unavailable without a paid ORS plan; the UI assumptions banner discloses this.
- HOS planner + independent verifier (11h / 14h / 30m break / fuel @1000mi / 34h restart)
- Map (Leaflet + OSM) with route polyline + stop/rest markers
- Route instructions timeline (with start/end times)
- SVG daily logs (grid, connectors, brackets, remarks, computed recap)
- Demo chips: Short / Long / Cycle
- Copy share link (query-string trip URLs)
- Print all daily log sheets
- Free stack: Vercel + Render + ORS/OSRM/Nominatim

### Backend
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Optional: set ORS_API_KEY=... (falls back to Nominatim + OSRM)
python manage.py runserver
```

### Frontend
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open http://localhost:5173

### Tests
```bash
cd backend
.venv\Scripts\python manage.py test planning -v 2
cd ../frontend
npm run build
```

## API
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health/` | Liveness / Render wake |
| GET | `/api/autocomplete/?q=` | Location suggestions |
| POST | `/api/plan/` | Full plan JSON |

## Free deploy

### 1. OpenRouteService (optional but recommended)
https://openrouteservice.org/dev/#/signup → copy API key

### 2. Backend — Render Free
1. Push this repo to GitHub
2. Render → New Web Service → connect repo
3. Root directory: `backend`
4. Build: `pip install -r requirements.txt`
5. Start: `gunicorn config.wsgi:application`
6. Instance: **Free**
7. Env:
   - `DJANGO_SECRET_KEY` = long random string
   - `DJANGO_DEBUG` = `False`
   - `DJANGO_ALLOWED_HOSTS` = `.onrender.com`
   - `CORS_ALLOWED_ORIGINS` = `https://YOUR_APP.vercel.app` (set after FE exists)
   - `ORS_API_KEY` = your key (optional)
8. Health check path: `/api/health/`

### 3. Frontend — Vercel Hobby
1. Import same repo in Vercel
2. Root: `frontend`
3. Framework: Vite
4. Env: `VITE_API_BASE_URL` = `https://YOUR_SERVICE.onrender.com`
5. Deploy → copy URL → update Render CORS → redeploy API

### 4. Cold starts
Render Free sleeps after ~15 minutes. The UI calls `/api/health/` on load. Optional: [cron-job.org](https://cron-job.org) ping health every 10–14 minutes during review.

## Assumptions (shown in UI)
- Property-carrying, 70h/8-day, no adverse conditions
- Starts after ≥10h off
- 70/8 as remaining-hours pool (no prior day history)
- Fuel every 1000 mi (0.5h ON)
- Pickup/dropoff 1.0h ON each
- Pre-trip 0.5h ON before first drive each window
- Daily reset = 0.5h OFF + 9.5h SB
- Home terminal TZ: America/Chicago

## Deliverables checklist
- [x] GitHub-ready codebase — https://github.com/hamdan-ishfaq/spotter
- [x] Local app + tests
- [x] Hosted Vercel URL — https://spotter-hamdan-ishfaqs-projects.vercel.app
- [x] Shareable trip links (query-string, no DB)
- [x] Print-friendly daily logs
- [ ] Loom 3–5 min walkthrough — see [LOOM_SCRIPT.md](./LOOM_SCRIPT.md)
