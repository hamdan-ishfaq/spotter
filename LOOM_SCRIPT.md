# LOOM SCRIPT — Exact words + story + architecture

**Target length:** 4:00–4:45 (hard cap 5:00)  
**Record:** screen share of the **live app** first; code only in the last ~75 seconds  
**Live app:** https://spotter-hamdan-ishfaqs-projects.vercel.app  
**GitHub (mention once):** https://github.com/hamdan-ishfaq/spotter  

Speak the **Say** blocks out loud. Do the **Do** blocks with the mouse. Architecture is woven into the story so you do not need a separate slides deck.

---

## Before you hit Record (2 minutes)

1. Chrome only, clean window, zoom **100%**, bookmarks bar hidden.  
2. Open the live app. Wait until **“Starting API…” / Waiting for API** is gone and **Plan trip** is enabled.  
3. Optional second tab: GitHub repo homepage (do not screen-share until close).  
4. Optional: VS Code with these two files ready on another desktop:
   - `backend/planning/hos_planner.py`
   - `frontend/src/components/DailyLogSheet.tsx`
5. Water, mute Slack/Discord, phone silent.  
6. If Render is sleeping, open `/api/health/` once and wait for `ok` **before** recording.

---

## Story arc (what the video is selling)

| Beat | Message |
|------|---------|
| Problem | Drivers need a legal HOS plan + paper-style daily logs, not a CRUD toy |
| Demo | Short → Long → Cycle proves 1-day, multi-day+fuel, and 34h restart |
| Architecture | Stateless free stack; all HOS math on the server; UI only paints |
| Trust | Planner + independent verifier; assumptions disclosed |
| Close | Links ready for Teamtailor |

---

## 0:00–0:35 — Intro + system architecture (spoken)

**Do:** Full-screen live app. Slowly scroll so the title and form are visible. Do **not** click Plan yet.

**Say (word-for-word):**

> “Hi, I’m Hamdan. This is my Spotter full-stack assessment — a React and Django app that plans property-carrying trips under FMCSA-style hours-of-service rules, shows the route on a map, and draws multi-day driver’s daily logs.
>
> Quick architecture in one breath: the frontend is a React SPA on Vercel. The backend is Django REST on Render Free. There is no trip database — every plan is a single POST. When you open the app, the UI hits a health endpoint to wake the free API. When you plan, the API geocodes and routes with free map services, runs an HOS planner that builds a legal duty timeline, then an independent verifier that re-checks the eleven-hour drive, fourteen-hour window, thirty-minute break, seventy-hour cycle, fuel, and pickup-dropoff rules. Only legal plans become JSON. The UI does zero HOS math — it only paints the map, the instruction list, and SVG paper logs.”

*(If you stumble, shorter backup line:)*

> “Vercel React front end, Render Django API, no database. Planner builds the trip; verifier proves it’s legal; UI only draws the result.”

---

## 0:35–1:35 — Demo: Short (prove the loop)

**Do:**

1. Click **Demo: Short** (Dallas → Houston).  
2. Click **Plan trip**.  
3. Wait for results. Point (cursor) at:
   - Summary chips (miles / hours / cycle)
   - Map polyline + pickup/dropoff markers
   - One instruction row (click it if it highlights the map)
   - Daily log sheet — the **four rows** (Off / Sleeper / Driving / On Duty Not Driving), the grid line, remarks under the axis, recap if visible

**Say:**

> “Inputs are current location, pickup, dropoff, and cycle hours already used. Short demo is Dallas to Houston — one clean day.
>
> Summary chips show distance and HOS clocks. The map is Leaflet on OpenStreetMap with the route line and stops. Instructions are a timed timeline from the API — start and end times, not fake front-end clocks.
>
> Below that is the daily log. I matched the FMCSA paper grammar: four status rows, a twenty-four-hour grid, remarks along the timeline, and recap fields. These are SVG drawings from the backend grid segments — not an HTML table.”

---

## 1:35–2:40 — Demo: Long (multi-day + fuel)

**Do:**

1. Click **Demo: Long** (Chicago → Los Angeles).  
2. Click **Plan trip** (may take a few seconds).  
3. Pan the map; point at a **fuel** or **rest** stop if visible.  
4. Switch **Day 1 / Day 2 / …** tabs on the log sheet.  
5. Briefly scroll the assumptions / Scope banner.

**Say:**

> “Long demo is Chicago to Los Angeles. That forces multi-day planning: eleven-hour drive and fourteen-hour window, a full ten-hour daily reset — we model that as half an hour off duty plus nine and a half hours sleeper — and fuel about every thousand miles as half an hour on-duty not driving.
>
> You get multiple daily log tabs, one calendar day each, each totaling twenty-four hours. The Scope banner is intentional honesty: this is an assessment subset, not a full ELD product. We disclose car routing on the free map tier, the seventy-hour pool approximation from cycle hours used, and that we are not implementing split sleeper, short-haul, or adverse-driving exceptions.”

---

## 2:40–3:25 — Demo: Cycle (34h restart) + share link

**Do:**

1. Click **Demo: Cycle** (Phoenix → Atlanta, high cycle used).  
2. Click **Plan trip**.  
3. Point at the **34h restart** chip / instruction / map marker if present.  
4. Click **Copy share link**; paste into the address bar or a notepad for one second (optional).  
5. Optional: hover **Print logs** — do not need to open the print dialog unless quick.

**Say:**

> “Cycle demo starts with most of the seventy-hour pool already used. When remaining hours cannot finish the work, the planner inserts a thirty-four-hour sleeper restart, resets the cycle pool, and continues. That shows up in instructions, on the map, and on the logs.
>
> Share links are just query parameters — no database — so a reviewer can reopen the same trip. Print CSS is there for paper-style sheets.”

---

## 3:25–4:20 — Code walkthrough (architecture on screen)

**Do:** Alt-Tab to VS Code (or split). Keep narration calm; scroll, don’t edit.

### File 1 — `backend/planning/hos_planner.py`

**Say:**

> “On the backend, the planner is a deterministic state machine. It tracks driving toward eleven hours, the fourteen-hour window, driving since the last break, miles since fuel, and cycle remaining. Before each drive chunk it ensures cycle, daily reset, break or fuel, and pre-trip in a fixed order so behavior stays testable.”

### File 2 — `backend/planning/hos_verifier.py` (open briefly)

**Say:**

> “After the timeline is built, the verifier re-simulates the same clocks independently. If anything illegal slips through, the API fails closed — the UI never gets a bad plan.”

### File 3 — `frontend/src/components/DailyLogSheet.tsx`

**Say:**

> “On the frontend, DailyLogSheet only renders. It draws the paper header, the four duty rows, connectors, and remarks pins. Location labels prefer city and state from reverse geocode, and we deconflict dense remarks so they stay readable.”

### Deploy one-liner (still on screen or back on the app)

**Say:**

> “Deploy is free tier by design: Vercel for the SPA, Render for Django, optional OpenRouteService key server-side only. Cold starts are why the UI wakes health first and disables Plan until the API is ready.”

---

## 4:20–4:40 — Close

**Do:** Return to the live app homepage (or finished Cycle results). Stop moving the mouse.

**Say:**

> “That’s the full loop — trip in, legal HOS plan out, map plus drawn daily logs, with assumptions disclosed. Public GitHub, hosted Vercel app, and this Loom are my submission. Thanks for watching.”

**Stop recording.**

---

## Timing cheat sheet

| Time | Section | On screen |
|------|---------|-----------|
| 0:00–0:35 | Intro + architecture | Live app idle |
| 0:35–1:35 | Short demo | Plan + map + one log |
| 1:35–2:40 | Long demo | Multi-day tabs + assumptions |
| 2:40–3:25 | Cycle + share | 34h + copy link |
| 3:25–4:20 | Code + deploy | planner / verifier / DailyLogSheet |
| 4:20–4:40 | Close | Live app |

If you are over time, **cut code** first — keep Long + Cycle + architecture intro.

---

## Architecture card (if they ask in interview — same words)

**Stack**

```text
Browser → Vercel React SPA → Render Django API → ORS / Nominatim / OSRM
                              ↓
                    hos_planner → hos_verifier
                              ↓
              logs_builder + instructions → JSON → map + SVG logs
```

**Non-negotiables you can defend**

1. HOS math never runs in the browser.  
2. Verifier is independent of the planner.  
3. Stateless plans fit free hosting and the assessment clock.  
4. Assessment subset is disclosed — not hidden.  
5. Drawn SVG logs match how Spotter grades “daily logs,” not tables.

**Why no split sleeper (one sentence)**

> “Split sleeper is a real FMCSA rule, but it needs paired sleeper windows excluded from the fourteen-hour clock. For this assessment I used full ten-hour resets and thirty-four-hour restarts only — simpler, testable, and called out in assumptions.”

---

## If something goes wrong while recording

| Problem | What to say / do |
|---------|------------------|
| API still waking | “Render free tier cold start — health check is warming the API.” Wait; don’t panic-click. |
| Plan slow on Long | “Coast-to-coast plan on free routing — a few seconds is normal.” |
| Autocomplete empty | Use **Demo chips** only; don’t type addresses live. |
| Flubbed a sentence | Pause 1s, repeat the sentence cleanly; edit in Loom later if needed. |
| Total disaster take | Stop; re-warm API; do a second take — better than a shaky 6-minute video. |

---

## Teamtailor paste block (after Loom upload)

| Field | Value |
|-------|--------|
| GitHub | https://github.com/hamdan-ishfaq/spotter |
| Hosted app | https://spotter-hamdan-ishfaqs-projects.vercel.app |
| Loom | *(your Loom share URL)* |

---

## Checklist after export

- [ ] Video is **3–5 minutes** (ideally ~4:30)  
- [ ] Architecture spoken in the first 35 seconds  
- [ ] Short + Long + Cycle all appear  
- [ ] Daily log close-up is readable (four rows + remarks)  
- [ ] You said “verifier” and “UI does no HOS math”  
- [ ] You disclosed assessment subset / assumptions  
- [ ] Title the Loom clearly: `Spotter HOS Trip Planner — Hamdan`  
- [ ] Link is **anyone with the link can view**  
- [ ] Paste all three links into Teamtailor  

**Owner handoff (detailed):** [`PROJECT_HANDOFF.md`](./PROJECT_HANDOFF.md)
