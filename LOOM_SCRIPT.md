# Loom script — Spotter HOS assessment (3–5 min)

Record your screen with this app open: **https://spotter-hamdan-ishfaqs-projects.vercel.app**

GitHub: **https://github.com/hamdan-ishfaq/spotter**

---

## Before you hit Record

1. Open the live app in Chrome (full screen or clean window).
2. Wait until the blue “Starting API…” banner disappears (API ready).
3. Have VS Code open on `backend/planning/hos_planner.py` and `frontend/src/components/DailyLogSheet.tsx` in another desktop or split later.
4. Target length: **4 minutes**.

---

## Minute 0:00–0:30 — Intro

**Say:**

> “Hi, I’m Hamdan. This is my Spotter Full Stack assessment — a Django + React app that plans FMCSA-style HOS trips, shows the route on a map, and draws multi-day driver daily logs.”

**Show:** Landing page title + form fields.

---

## Minute 0:30–1:30 — Live demo (Short trip)

**Do:**

1. Click **Demo: Short**
2. Click **Plan trip**
3. Point out summary chips: miles, drive hours, on-duty, cycle remaining
4. Pan the **map** — route line + stop markers (pickup, fuel if any, rest, dropoff)
5. Click one **route instruction** — highlight on map
6. Scroll to **Daily log sheet** — point out:
   - 4 duty rows (Off / Sleeper / Driving / On-duty)
   - Drawn horizontal lines on 15-min grid
   - Vertical connectors between status changes
   - Remarks + recap section

**Say:**

> “Inputs are current, pickup, dropoff, and cycle hours used. The backend geocodes and routes with free APIs, runs the HOS planner, and the frontend renders SVG daily logs — not tables.”

---

## Minute 1:30–2:30 — Long + Cycle demos

**Do:**

1. Click **Demo: Long** (Chicago → Los Angeles) → **Plan trip**
2. Show **multiple log tabs** (Day 1, Day 2, …)
3. Mention **fuel stops** on 1000+ mile routes
4. Click **Demo: Cycle** (Phoenix → Atlanta, high cycle use) → **Plan trip**
5. Point out **“34h restart used”** chip if shown
6. Click **Copy share link** — paste in notepad briefly to show query-string sharing

**Say:**

> “Long hauls span multiple daily logs. When cycle hours are nearly exhausted, the planner inserts a 34-hour sleeper restart. Assumptions are disclosed in the banner — 70-hour/8-day, 1-hour pickup and dropoff, fuel every thousand miles.”

---

## Minute 2:30–3:30 — Code walkthrough (backend)

**Switch to VS Code.**

**Open:** `backend/planning/hos_planner.py`

**Say:**

> “The core is a deterministic HOS state machine — 11-hour drive, 14-hour window, 30-minute break after 8 hours driving, daily reset, fuel every 1000 miles, 1-hour pickup and dropoff.”

**Open:** `backend/planning/hos_verifier.py`

**Say:**

> “Every plan is verified independently before returning JSON — so illegal timelines don’t reach the UI.”

**Open:** `backend/planning/routing.py` + `geocode.py`

**Say:**

> “Maps use free OpenRouteService when a key is set, with Nominatim and OSRM fallbacks. Frontend uses Leaflet and OpenStreetMap tiles.”

---

## Minute 3:30–4:15 — Code walkthrough (frontend) + deploy

**Open:** `frontend/src/components/DailyLogSheet.tsx`

**Say:**

> “Daily logs are SVG — grid segments, connectors, brackets, headers, and recap math from the API.”

**Open:** `README.md` or mention deploy

**Say:**

> “Frontend on Vercel, API on Render free tier, public GitHub repo. The UI wakes the API on load and retries during Render cold starts.”

---

## Minute 4:15–4:30 — Close

**Say:**

> “That’s the full loop — trip in, legal HOS plan out, map plus drawn ELD logs. Links are in my submission. Thanks for watching.”

---

## Submission checklist (Teamtailor)

| Field | Your link |
|-------|-----------|
| GitHub | https://github.com/hamdan-ishfaq/spotter |
| Hosted app | https://spotter-hamdan-ishfaqs-projects.vercel.app |
| Loom | *(paste after upload)* |

---

## Tips for a polished recording

- Speak clearly; don’t rush the log sheet close-up.
- If API is slow, say “Render free tier cold start” — reviewers know this.
- Show **Print logs** once (optional) — proves print CSS works.
- Keep code section under 90 seconds — they care more about the live app.
