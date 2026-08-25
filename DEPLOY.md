# Deploy Spotter HOS Trip Planner (Render + Vercel)

This guide walks you through deploying the full assessment stack from scratch. Your repo is **ready to deploy** — no code changes are required before going live.

| Layer | Platform | Folder | Purpose |
|-------|----------|--------|---------|
| **Frontend** (what reviewers open) | [Vercel](https://vercel.com) | `frontend/` | React + Vite static app |
| **Backend API** | [Render](https://render.com) | `backend/` | Django REST API (planning, geocode, HOS) |

GitHub repo: **https://github.com/hamdan-ishfaq/spotter**

**Live demo:** https://spotter-hamdan-ishfaqs-projects.vercel.app  
**Live API:** https://spotter-hos-api-xb1g.onrender.com

---

## Deployment readiness checklist

Before you start, confirm these are already in place (they are in this repo):

- [x] Code pushed to GitHub (`hamdan-ishfaq/spotter`)
- [x] `render.yaml` — Render Blueprint config for the API
- [x] `frontend/vercel.json` — Vercel build settings
- [x] `backend/requirements.txt` includes `gunicorn`
- [x] `backend/runtime.txt` — Python 3.12.8
- [x] Health endpoint at `/api/health/` (Render health check + frontend wake-up)
- [x] `.env` files **not** committed (secrets stay local; you set env vars in dashboards)
- [x] Frontend production build passes (`npm run build` in `frontend/`)

**Deploy order:** Backend (Render) first → Frontend (Vercel) second → Update CORS on Render third.

---

## Prerequisites

1. **GitHub account** with access to `hamdan-ishfaq/spotter` (already done).
2. **Render account** — sign up at https://render.com (use “Sign in with GitHub”).
3. **Vercel account** — sign up at https://vercel.com (use “Continue with GitHub”).
4. **Optional but recommended:** [OpenRouteService](https://openrouteservice.org/dev/#/signup) free API key for faster geocoding/routing. The app works without it (falls back to Nominatim + OSRM).

---

## Part 1 — Deploy the Django API on Render

You can use either **Blueprint** (easiest — reads `render.yaml`) or **manual Web Service**. Both work.

### Option A — Blueprint (recommended)

1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Blueprint**.
3. Connect your GitHub account if prompted, then select repository **`hamdan-ishfaq/spotter`**.
4. Render detects `render.yaml` and shows a service named **`spotter-hos-api`**.
5. Review settings (defaults are fine):
   - **Root directory:** `backend`
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn config.wsgi:application`
   - **Health check path:** `/api/health/`
6. When asked for environment variables, set:

   | Key | Value | Notes |
   |-----|-------|-------|
   | `DJANGO_SECRET_KEY` | *(generate a long random string)* | e.g. 50+ random chars; never reuse dev key |
   | `DJANGO_DEBUG` | `False` | Required in production |
   | `DJANGO_ALLOWED_HOSTS` | `.onrender.com` | Allows your `*.onrender.com` URL |
   | `CORS_ALLOWED_ORIGINS` | *(leave empty for now)* | Fill in after Vercel deploy (Part 2) |
   | `ORS_API_KEY` | *(optional)* | Your OpenRouteService key |
   | `HOME_TERMINAL_TZ` | `America/Chicago` | Already in blueprint default |

7. Choose **Free** instance type.
8. Click **Apply** / **Create** and wait for the first deploy (usually 3–8 minutes).
9. Copy your live API URL from the Render service page, e.g.:
   ```
   https://spotter-hos-api.onrender.com
   ```
   *(Your exact subdomain may differ — use whatever Render assigns.)*

10. **Verify the API:**
    - Open in browser: `https://YOUR-SERVICE.onrender.com/api/health/`
    - Expected JSON response includes `"status": "ok"` (or similar success payload).

### Option B — Manual Web Service

If Blueprint is unavailable, create manually:

1. **New +** → **Web Service** → connect **`hamdan-ishfaq/spotter`**.
2. Settings:

   | Field | Value |
   |-------|-------|
   | Name | `spotter-hos-api` (or any name) |
   | Region | Pick closest to you (e.g. Oregon / Frankfurt) |
   | Branch | `main` |
   | Root Directory | `backend` |
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `gunicorn config.wsgi:application` |
   | Instance Type | **Free** |

3. **Advanced** → Health Check Path: `/api/health/`
4. Add the same environment variables as in Option A (table above).
5. Deploy and verify `/api/health/` as in step 10.

### Render free tier notes

- The service **sleeps after ~15 minutes** of no traffic.
- First request after sleep can take **30–60 seconds** (cold start). The frontend calls `/api/health/` on load to wake it up.
- See [Part 4 — Keep API warm (optional)](#part-4--keep-api-warm-optional) if you want faster loads during review.

---

## Part 2 — Deploy the React frontend on Vercel

1. Log in to [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New…** → **Project**.
3. Import Git repository **`hamdan-ishfaq/spotter`**.
4. Configure the project:

   | Field | Value |
   |-------|-------|
   | Framework Preset | **Vite** (auto-detected) |
   | Root Directory | `frontend` ← **important** — click Edit and set to `frontend` |
   | Build Command | `npm run build` (default) |
   | Output Directory | `dist` (default) |
   | Install Command | `npm install` (default) |

5. **Environment Variables** — add before first deploy:

   | Name | Value | Environments |
   |------|-------|--------------|
   | `VITE_API_BASE_URL` | `https://YOUR-SERVICE.onrender.com` | Production, Preview, Development |

   **Rules:**
   - Use your **Render URL** from Part 1 (no trailing slash).
   - Example: `https://spotter-hos-api.onrender.com`
   - Do **not** use `http://127.0.0.1:8080` in production.

6. Click **Deploy** and wait (~1–3 minutes).
7. Copy your production URL, e.g.:
   ```
   https://spotter.vercel.app
   ```
   *(Vercel may assign `spotter-hamdan-ishfaq.vercel.app` or similar — any `*.vercel.app` URL works.)*

8. **Verify the frontend:**
   - Open the Vercel URL in a browser.
   - You should see the Spotter HOS Trip Planner UI.
   - Click a demo chip (**Short**, **Long**, or **Cycle**) and run a plan.
   - First plan after API sleep may be slow; wait up to ~60 seconds.

---

## Part 3 — Connect frontend and backend (CORS)

The browser blocks API calls unless Render allows your Vercel origin.

1. Go back to **Render** → your **`spotter-hos-api`** service → **Environment**.
2. Set **`CORS_ALLOWED_ORIGINS`** to your Vercel URL **exactly** (no trailing slash):

   ```
   https://spotter.vercel.app
   ```

   If you have multiple Vercel URLs (production + preview), comma-separate them:

   ```
   https://spotter.vercel.app,https://spotter-git-main-hamdan-ishfaq.vercel.app
   ```

3. Save changes. Render will **automatically redeploy** (or click **Manual Deploy** → **Deploy latest commit**).
4. After redeploy, test again from the Vercel URL:
   - Autocomplete on location fields should work.
   - **Plan Trip** should return map, instructions, and daily log sheets.

### Quick CORS troubleshooting

| Symptom | Fix |
|---------|-----|
| Browser console: CORS error | `CORS_ALLOWED_ORIGINS` must match Vercel URL exactly (`https://`, no trailing `/`) |
| Network tab: failed fetch to Render | Confirm `VITE_API_BASE_URL` on Vercel points to correct Render URL |
| 502 / timeout on first load | Render cold start — wait 60s and retry |
| Plans work locally but not hosted | Redeploy Vercel after changing `VITE_API_BASE_URL` |

---

## Part 4 — Keep API warm (optional)

During assessment review, reviewers may hit a cold API. Optional free ping:

1. Go to https://cron-job.org (free account).
2. Create a cron job:
   - **URL:** `https://YOUR-SERVICE.onrender.com/api/health/`
   - **Schedule:** every 10–14 minutes
3. This reduces cold starts during the review window.

---

## Part 5 — Optional: OpenRouteService API key

Without a key, the app uses Nominatim + OSRM (free, rate-limited). With a key, geocoding/routing is more reliable under load.

1. Sign up: https://openrouteservice.org/dev/#/signup
2. Copy your API key.
3. In **Render** → Environment → set `ORS_API_KEY` to your key.
4. Redeploy the Render service.

No frontend change needed.

---

## Part 6 — Full verification checklist

Run through this on the **live Vercel URL** before submitting the assessment:

- [ ] App loads with title/branding and assumptions banner
- [ ] Demo chip **Short** fills form and produces a plan
- [ ] Map shows route polyline and stop markers
- [ ] Route instructions timeline appears with times
- [ ] At least one **Driver’s Daily Log** sheet renders with drawn duty lines
- [ ] Long trip produces **multiple** daily log sheets
- [ ] Location autocomplete returns suggestions
- [ ] No CORS errors in browser DevTools → Console
- [ ] `/api/health/` on Render returns OK when opened directly

---

## Part 7 — What to submit to Spotter

| Deliverable | Your link |
|-------------|-----------|
| GitHub | https://github.com/hamdan-ishfaq/spotter |
| Hosted app | `https://YOUR-APP.vercel.app` ← share this as the live demo |
| Loom (3–5 min) | Record: app demo + brief code tour (planner, logs, map) |

Suggested Loom outline:

1. **30s** — Problem: trip inputs → HOS-compliant plan + ELD logs
2. **90s** — Live demo: Short + Long trip, map, instructions, daily logs
3. **60s** — Backend: `hos_planner.py`, verifier, `/api/plan/`
4. **30s** — Frontend: `DailyLogSheet.tsx`, `RouteMap.tsx`
5. **30s** — Deploy stack (Vercel + Render) and tests

---

## Reference — Environment variables summary

### Render (`backend`)

| Variable | Production value |
|----------|------------------|
| `DJANGO_SECRET_KEY` | Long random secret |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `.onrender.com` |
| `CORS_ALLOWED_ORIGINS` | `https://YOUR-APP.vercel.app` |
| `ORS_API_KEY` | *(optional)* |
| `HOME_TERMINAL_TZ` | `America/Chicago` |

### Vercel (`frontend`)

| Variable | Production value |
|----------|------------------|
| `VITE_API_BASE_URL` | `https://YOUR-SERVICE.onrender.com` |

---

## Reference — Repo files used at deploy time

| File | Role |
|------|------|
| `render.yaml` | Render Blueprint definition |
| `backend/requirements.txt` | Python dependencies + gunicorn |
| `backend/runtime.txt` | Python version for Render |
| `backend/config/wsgi.py` | WSGI entry for gunicorn |
| `frontend/vercel.json` | Vercel build + SPA rewrites |
| `frontend/package.json` | `npm run build` → `dist/` |

---

## Redeploying after code changes

1. Push commits to `main` on GitHub.
2. **Render** and **Vercel** auto-deploy on push (if enabled — default for Git-connected projects).
3. If you only changed env vars, trigger **Manual Deploy** on the affected platform.

---

## Local vs production

| | Local | Production |
|---|-------|------------|
| Frontend | `http://localhost:5173` | `https://*.vercel.app` |
| API | `http://127.0.0.1:8080` | `https://*.onrender.com` |
| Env file | `frontend/.env`, `backend/.env` | Dashboard env vars only |

Never commit `.env` files with real secrets. Use `.env.example` as templates locally.

---

## Support links

- Render docs: https://render.com/docs/deploy-django
- Vercel docs: https://vercel.com/docs/frameworks/vite
- Project README: [README.md](./README.md)
- Architecture / specs: [HANDOFF.md](./HANDOFF.md), [TRD.md](./TRD.md)

---

*Last updated: 2026-08-25 — repo verified build-ready for Render + Vercel deployment.*
