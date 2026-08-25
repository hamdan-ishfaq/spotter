# PRD: Spotter Assessment — Trip Planner + Drawn Daily Logs

**Version:** 4.1 (job-post aligned · assessment-scoped · fully free)  
**Assessment cap:** ≤ 4 days / ≤ 16 work hours (Spotter limit)  
**Execution model:** Solo build within Spotter’s ≤4 days / ≤16 work hours cap  
**Deliverables:** Public GitHub · Live hosted app (all free tiers) · 3–5 min Loom  
**Stack:** Django + DRF + React + **Material UI** (matches job + brief)  
**Bonus context:** Focus on required assessment features and polish, not extra infra  
**Architecture:** see [`SYSTEM_ARCHITECTURE.md`](./SYSTEM_ARCHITECTURE.md) (system design + detailed user flows + free-tier handling)

---

## 0. Job posting vs assessment (strategy lock)

### What the role cares about (prove **in this app**)
| Job “What You'll Do” | How this assessment proves it |
|---|---|
| Ship complete React + Django features | End-to-end plan → API → UI |
| Responsive React + **MUI** | Polished responsive MUI UI |
| Django/DRF APIs | Clean `/api/plan/`, autocomplete, health |
| Clean UI connected to services | Form → live API → map + logs |
| **Algorithmic / decision logic surfaced in UI** | HOS planner + verifier + visible assumptions, clocks, stops |
| Pragmatic production-ready code | Tests, README, free deploy, clear structure |

### Job “Bonus Points” — **resume / Loom only, NOT assessment scope**
| Bonus | Assessment decision | Where it belongs |
|---|---|---|
| Redis | **Do not add** | Resume (prior work) + optional Loom “I’d cache geocode in Redis in prod” |
| Docker / K8s | **Do not add** | Resume; optional one-line README “containerize later” — no Dockerfile required to pass |
| GCP | **Do not add** | Resume |
| React Native / mobile app | **Do not add** | Resume; assessment already asks responsive web — polish that instead |
| Productivity tooling | **Optional** | Mention in Loom if used; not a repo requirement |

**Why:** Reviewers grade the **hosted assessment** for HOS accuracy, drawn logs, map, and UI. Redis/Docker/RN burn hours, add free-tier friction, and do not appear in the assessment brief. Putting them here risks a half-baked core. **Best move: resume + interview story; keep this repo laser-focused.**

---

## 0.1 Grading reality → build for “cannot reject”

| They care about | Fail mode | Win mode |
|---|---|---|
| Hosted **accuracy** | Illegal HOS, wrong pickup/dropoff hours, missing fuel, logs ≠ 24h | Verifier-backed plans + golden demos |
| **Drawn** logs | Tables / sparse grids | Video-faithful SVG: connectors, brackets, remarks, multi-day |
| Map + stops/rests | Empty map / no rest info | Polyline + markers + instruction list |
| UI/UX | Ugly, confusing, broken states | Polished MUI freight UI; demos; autocomplete; loading/errors |
| Ship | Dead API, no README, weak Loom | Always-on free FE + free BE wake strategy + clear links |

**Principle:** Ship a **complete product slice**, not a thin MVP. Only cut items that do not raise pass probability.

---

## 1. Product one-liner

A production-feeling React + Django app that turns **current / pickup / dropoff / cycle hours** into an HOS-legal **route map + instructions** and **multi-day drawn FMCSA daily logs**.

---

## 2. Full scope (assessment bar)

### Must ship (in scope — all of this)
1. Trip form: current, pickup, dropoff, cycle used + editable start datetime  
2. Location **autocomplete** (backend-proxied ORS)  
3. Geocode + route (ORS HGV attempted when key present → **car fallback**; free tier usually lands on car — disclosed in assumptions)  
4. HOS planner + **separate verifier** (11h / 14h / 8h-break / 70 pool / 34h / fuel / 1h PU-DO)  
5. Pre-trip **0.5h ON** before first drive each window (video-accurate)  
6. Daily reset **0.5h OFF + 9.5h SB**; 34h SB restart  
7. Map (Leaflet): route, stops/rests, marker ↔ instruction highlight  
8. Route instructions timeline  
9. SVG daily logs: 4 rows, 15-min ticks, vertical connectors, **brackets**, remarks, headers, decimal on-duty, multi-day, print CSS  
10. Assumptions banner (honest 70/8 approximation)  
11. Three demo presets (Short / Long / Cycle)  
12. Client-side “copy share link” via query-string encoded inputs (no DB)  
13. README + architecture notes + free deploy docs  
14. Loom walkthrough of app + engine + logs  

### Still out of scope (doesn’t help pass)
- Redis, Docker/K8s, GCP, React Native (job **bonuses** → resume only)  
- Real user auth / multi-tenant  
- True rolling 8-day history (inputs don’t allow it — stay honest)  
- Sleeper split pairing (7+2) as strategy  
- Adverse / short-haul exceptions  
- Paid map keys (Google), paid hosting  
- Native mobile / real ELD devices  
- Server-side trip DB (stateless is fine + free-friendly)

---

## 3. Locked product decisions

| Topic | Decision |
|---|---|
| Cycle | 70h/8-day; `remaining = 70 − cycle_used` (approx; disclosed) |
| Start | After ≥10h off; default today **06:00** `America/Chicago`; user-editable |
| Break | 0.5h OFF; fuel ON 0.5h can satisfy |
| Fuel | ≤1000 mi gap; 0.5h ON; on-polyline |
| PU / DO | 1.0h ON each |
| Pre-trip | 0.5h ON before first drive in window |
| Daily reset | 0.5h OFF + 9.5h SB |
| 34h | Full SB when cycle pool insufficient |
| Maps | **OpenRouteService free** + **Leaflet/OSM free** |
| Hosting | **100% free:** Vercel FE + Render BE (+ free GitHub + free Loom + free ORS) |
| Logs | SVG paper grammar from Schneider video + blank form |

---

## 4. Inputs / outputs

### Inputs
- Current location (autocomplete)  
- Pickup location  
- Dropoff location  
- Current cycle used (0–70)  
- Start datetime (optional UI; defaulted)

### Outputs
- Summary metrics  
- Ordered route instructions  
- Map geometry + stop/rest markers + synced list  
- `daily_logs[]` drawn sheets  

---

## 5. HOS accuracy (non-negotiable)

1. 11h drive limit  
2. 14h window (ON starts/burns window)  
3. 30m break after 8h driving  
4. 70h pool + 34h restart  
5. 10h OFF+SB reset  
6. Fuel ≤1000 mi  
7. PU/DO = 1.0h ON  
8. Each log day totals **24.00**  
9. `plan()` then `verify()` — never return illegal timelines  

---

## 6. Daily log bar (video-aligned)

- Paper look from `blank-paper-log.png`  
- Rows: OFF / SB / D / ON  
- Horizontal lines + vertical connectors  
- Brackets under stationary ON  
- Remarks: City, ST — activity  
- Totals + on-duty decimal  
- Multi-day tabs + print stylesheet  

---

## 7. UX bar (polish past “adequate”)

- Cohesive freight ops visual design (MUI theme, real fonts, atmosphere — not purple SaaS)  
- Hero product name + one-line + form as first composition  
- Demo chips, share-link copy, excellent empty/loading/error states  
- Map + instructions side-by-side on desktop; stacked on mobile  
- Assumptions always visible  
- Responsive down to ~375px  

---

## 8. Fully free platform stack

| Need | Free choice | Cost |
|---|---|---|
| Source | GitHub public repo | $0 |
| Frontend host | **Vercel Hobby** | $0 |
| Backend host | **Render Free** web service | $0 |
| Routing/geocode | **OpenRouteService** free key | $0 |
| Map tiles | **OSM** via Leaflet | $0 |
| Video | **Loom** free | $0 |
| Domain | `*.vercel.app` + `*.onrender.com` | $0 |

No credit card required for the happy path (Vercel/GitHub/ORS/Loom). Render may ask for card on some accounts but Free instance type stays $0 if you stay on free tier — prefer email signup and Free plan only.

**Do not use:** Google Maps paid, Mapbox paid tiers, Railway paid-only, AWS, custom domains that cost money.

---

## 9. Free deployment playbook (speed + pass reliability)

### 9.1 Accounts to create first (15–20 min, do Day 0)
1. GitHub account (repo ready)  
2. [OpenRouteService](https://openrouteservice.org/dev/#/signup) → create API key → save as `ORS_API_KEY`  
3. [Vercel](https://vercel.com) → import will come later  
4. [Render](https://render.com) → New Web Service later  
5. Loom account for recording  

### 9.2 Backend on Render (Free) — Django
1. Push `backend/` to GitHub  
2. Render → **New → Web Service** → connect repo  
3. Settings:
   - **Runtime:** Python  
   - **Root directory:** `backend`  
   - **Build command:** `pip install -r requirements.txt`  
   - **Start command:** `gunicorn config.wsgi:application`  
   - **Instance type:** **Free**  
4. Environment variables:
   - `DJANGO_SECRET_KEY` = random long string  
   - `DJANGO_DEBUG` = `False`  
   - `DJANGO_ALLOWED_HOSTS` = `.onrender.com`  
   - `CORS_ALLOWED_ORIGINS` = `https://<your-app>.vercel.app` (update after FE URL exists; can temporarily `*` only for first bring-up then tighten)  
   - `ORS_API_KEY` = your key  
5. Deploy → copy URL `https://<service>.onrender.com`  
6. Verify `GET /api/health/` (first hit may take 30–60s on free cold start)

### 9.3 Frontend on Vercel (Free) — React/Vite
1. Vercel → Add New Project → import same repo  
2. **Root directory:** `frontend`  
3. Framework preset: Vite  
4. Env: `VITE_API_BASE_URL` = `https://<service>.onrender.com`  
5. Deploy → copy `https://<app>.vercel.app`  
6. Go back to Render and set `CORS_ALLOWED_ORIGINS` to that exact origin → redeploy BE  

### 9.4 Cold-start strategy (critical for reviewers)
Render **Free spins down after ~15 min idle**. Mitigations (all free):
1. README: “If first request is slow, wait ~60s or open `/api/health/` first”  
2. FE: on app load, **fire-and-forget** `GET /api/health/` to wake API  
3. Before Loom / before submitting, wake the API yourself  
4. Optional free uptime ping: [cron-job.org](https://cron-job.org) ping `/api/health/` every 10–14 min (free) — keeps Render warmer during review window  

### 9.5 Deploy order for maximum speed
```text
Day 0: ORS key + empty repos scaffolding committed
Hour 1 of build: deploy HELLO health+blank Vite (URLs exist early)
Continuous: push main → auto-deploy both
Final: tighten CORS, run demos on production URLs, record Loom
```
**Deploy early, deploy often** — don’t leave hosting for the last hour.

### 9.6 Submission URLs
- GitHub repo  
- Hosted app = **Vercel URL** (primary)  
- Mention API base in README  
- Loom link  

---

## 10. Build budget (~8h build + buffer)

| Block | Hours | Outcome |
|---|---|---|
| 0. Free accounts + hello deploy | 0.75 | Live FE/BE URLs |
| 1. Scaffold + theme + form/autocomplete UI | 1.0 | Polished shell |
| 2. ORS geo/route + map | 1.25 | Real routes on map |
| 3. HOS planner + verifier + tests | 2.5 | Accuracy core |
| 4. Logs SVG (connectors, brackets, print) | 1.5 | Drawn multi-day logs |
| 5. Instructions sync + demos + share link + assumptions | 0.75 | Reviewer UX |
| 6. Prod harden + README + demos on live | 0.5 | Ship confidence |
| 7. Buffer / bugfix / Loom | inside remaining ≤16h cap | Pass |

Use tests and live demos to validate HOS fixtures before submission.

---

## 11. Golden demos (must pass on free hosted URL)

| Demo | Intent |
|---|---|
| A Short | Clean single-day-ish log, PU/DO hours |
| B Long | Fuel + 10h reset + **multiple logs** |
| C Cycle 68 | **34h restart** visible, still legal |

---

## 12. Definition of done

- [ ] Vercel URL works end-to-end on free Render API  
- [ ] Autocomplete + plan + map + instructions + drawn logs  
- [ ] Demos A/B/C pass verifier on production  
- [ ] Cold-start wake on FE load + README note (+ optional cron)  
- [ ] Assumptions visible; share-link works  
- [ ] Public GitHub + Loom + Teamtailor links  
- [ ] $0 spent on infra/maps  

---

## 13. Loom (3–5 min)

1. Assumptions + free stack one-liner (20s)  
2. Demo B on **production URL** (2min) — map, rests, flip logs, brackets  
3. Planner + verifier code (1.5min)  
4. Log SVG (40s)  
5. Tradeoff: 70/8 approximation (20s)  

---

## 14. Risks (free-stack specific)

| Risk | Mitigation |
|---|---|
| Render sleep | FE health ping + cron-job.org + README |
| ORS free limits | Cache; demos; server-side key |
| CORS misconfig | Exact Vercel origin; test from prod FE |
| Vite env not baked | Set `VITE_*` in Vercel before build |
| Reviewer impatience on cold start | Wake before submitting; demos one-click |

---

## 15. Non-goals

No paid APIs, no paid hosts, no auth, no fake rolling recap, no sleeper-split engine, no ELD certification claim.
