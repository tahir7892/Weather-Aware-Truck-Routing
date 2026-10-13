# Weather-Aware Truck Routing

A **React + Django** web app that helps a truck driver choose the safest route
based on **weather, load weight and travel time**.

The driver enters an origin, a destination, a departure time and a load weight.
The app finds **3 truck routes**, checks the weather every **10, 25 or 50 miles**
for the moment the truck will **actually arrive** at each point, rates the risk
with the assessment's wind/rain/snow and load rules, **recommends the best
route**, and shows everything on a map together with a **0–48 hour weather
heatmap** along the trip corridor.

---

## Contents

1. [Features](#features)
2. [How it meets the requirements](#how-it-meets-the-requirements)
3. [Tech stack](#tech-stack)
4. [Architecture](#architecture)
5. [How a trip is planned](#how-a-trip-is-planned)
6. [Risk rules and recommendation](#risk-rules-and-recommendation)
7. [Design decisions](#design-decisions)
8. [Project structure](#project-structure)
9. [Setup](#setup)
10. [Running the app](#running-the-app)
11. [Using the app](#using-the-app)
12. [Testing and quality checks](#testing-and-quality-checks)
13. [API reference](#api-reference)
14. [Configuration](#configuration)
15. [Performance](#performance)
16. [Troubleshooting](#troubleshooting)
17. [Deployment notes](#deployment-notes)
18. [Known limitations](#known-limitations)

---

## Features

**Trip planning**
- Origin and destination with live place suggestions (type 3+ letters, use the
  arrow keys and Enter, or type a full address).
- Departure date and time in the user's **own time zone**, load weight in
  pounds, and a weather checkpoint every **10, 25 or 50 miles**.
- Input is checked in the browser and again on the server, with clear messages
  next to each field.

**Results**
- **3 distinct truck routes** (OpenRouteService heavy-goods-vehicle profile),
  each labelled with its main roads, e.g. "via I-94".
- **Recommendation banner** naming the best route and why, e.g.
  *"Route B is recommended (vs Route A: fewer Severe miles (0.0 vs 40.0) …)"*.
- **Route cards**: distance, drive time, arrival time, a colored bar of miles
  per risk level, No Travel / Severe / High miles and average risk.
- **Checkpoint table** for the selected route: mile, arrival time, wind, rain,
  snow and risk level.
- **Warnings**, e.g. when every route has No Travel conditions or weather data
  is missing.

**Map** (MapLibre GL, free CARTO / OpenStreetMap tiles, no key needed)
- All 3 routes, the selected one in blue on top, each with a label showing its
  letter and drive time.
- Checkpoint dots colored by risk; click one for its ETA, the forecast hour
  used, wind, gusts, rain, snow and the reason for its risk level.
- Start / End markers and a legend.

**Weather heatmap and timeline**
- Risk squares covering the area within 30 miles of the routes.
- A **0–48 hour slider** with play/pause; the heatmap and a **truck icon**
  (where the selected truck will be at that hour) follow the slider instantly.

**Reliability**
- Readable error messages for every failure (bad input, unknown place, no road,
  slow or unavailable outside services, rate limits), with "Try again".
- Caching, retries for brief network problems, and per-client rate limits.

---

## How it meets the requirements

| Requirement | Where it is handled |
|---|---|
| User enters origin, destination, departure time, load weight | Frontend `TripForm`; validated by backend `serializers.py` |
| Generate **3 route options** using a routing API | Backend `clients/routing_client.py` (OpenRouteService) |
| Sample weather every **10 / 25 / 50 miles** | Backend `services/checkpoints.py` |
| Use the truck's **estimated arrival time** at each checkpoint | ETAs from per-road-step travel times; forecast for the hour nearest each ETA |
| Calculate weather risk with the **risk / load rules** | Backend `services/risk.py`, thresholds in `constants.py` |
| Recommend the best route (Severe → High → average risk → time) | Backend `services/recommendation.py` |
| Show routes, checkpoints, risk levels, ETAs and summaries **on a map** | Frontend `components/Map/*`, `components/Routes/*` |
| **Weather heatmap** along the corridor with a **0–48 h slider** | Backend `services/heatmap.py` + frontend `HeatmapLayer`, `ForecastSlider` |
| Third-party APIs for routing, geocoding and weather | OpenRouteService and Open-Meteo |

---

## Tech stack

| Part | Technology |
|---|---|
| Backend | Python 3.11, Django 5.2, Django REST Framework, requests |
| Frontend | React 19, Vite 8, JavaScript, MapLibre GL 6 |
| Routing and geocoding | [OpenRouteService](https://openrouteservice.org/) (free API key) |
| Weather | [Open-Meteo](https://open-meteo.com/) hourly forecast (no key) |
| Map tiles | CARTO Positron (OpenStreetMap data, no key) |
| Tests and checks | pytest + pytest-django (backend), oxlint and Vite build (frontend) |

---

## Architecture

```
                        Browser — React app (http://localhost:5173)
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ TripForm ─► useTripPlanner ─► api/tripApi.js ──────┐                      │
   │ Route cards · Recommendation · Checkpoint table     │  JSON over HTTP      │
   │ Map (routes, checkpoints, heatmap, truck) · Slider  │                      │
   └─────────────────────────────────────────────────────┼──────────────────────┘
                                                         ▼
                        Django REST API (http://127.0.0.1:8000/api)
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ views.py ─► serializers.py (validate) ─► services/ (pure logic)          │
   │   trip_planner · checkpoints · risk · recommendation · heatmap           │
   │                     │                                                    │
   │                     ▼                                                    │
   │ clients/ (the only code that calls outside APIs) + cache                 │
   │   geocoding_client · routing_client ──► OpenRouteService                 │
   │   weather_client ─────────────────────► Open-Meteo                       │
   └──────────────────────────────────────────────────────────────────────────┘
```

**Three ideas run through both halves:**

1. **External calls are isolated.** On the backend only `clients/` talks to
   outside APIs; on the frontend only `api/` talks to the backend. The risk,
   checkpoint and recommendation logic is pure code, tested without a network.
2. **One source of truth.** Every risk threshold is in
   `backend/planner/constants.py`; every risk color is in
   `frontend/src/utils/risk.js`.
3. **Everything shown is explained.** Each checkpoint carries a plain-English
   reason ("Severe: wind 40.0 mph with 45,000 lb load (over 40,000 lb)") and
   the recommendation explains which rule decided it.

---

## How a trip is planned

**`POST /api/plan-trip/`**

1. **Validate** the input: weight 1–150,000 lb, interval 10/25/50, departure no
   more than 30 minutes in the past and at most 7 days ahead.
2. **Geocode** text places to coordinates (skipped when the frontend already
   sends coordinates from the suggestions).
3. **Find 3 routes.** The fastest truck route, plus two detours forced through
   a via-point pushed left and right of the trip's midpoint (15% of the trip
   length, then 30% / 45% if needed). Via-points are snapped to truck roads
   first. Near-duplicate routes (>85% shared road) and detours more than 1.5×
   slower are dropped. The truck's gross weight (35,000 lb empty truck + load)
   is sent to OpenRouteService so weight-restricted roads are avoided.
4. **Place checkpoints** at mile 0, every N miles, and at the destination.
5. **Work out ETAs** from the travel time of each road step, so slow city
   streets and fast highways are both reflected (not one average speed).
6. **Fetch the weather** for every checkpoint at the hour nearest its ETA
   (wind, gusts, rain + showers, snowfall in mph and inches). Nearby points
   share one lookup; up to 100 points go in one request, in parallel.
7. **Rate each checkpoint** with the risk rules below.
8. **Summarize each route**: miles at each risk level, average risk, worst level.
9. **Rank the routes** and write the reason and warnings.
10. **Save the trip** for one hour under a `trip_id` and return everything.

**`GET /api/heatmap/?trip_id=…`** (called by the frontend right after the routes
appear) lays a grid over the area within 30 miles of the routes (at most 250
points), fetches 49 hours of weather (hour 0 = departure) and rates every point
at every hour with the **same rules and load weight** as the checkpoints.

---

## Risk rules and recommendation

### Risk table (per checkpoint)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25 – < 35 | 35 – < 45 | 45 – < 55 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10 – < 0.25 | 0.25 – < 0.50 | 0.50 – 1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5 – < 1.0 | 1.0 – < 2.0 | 2.0 – 3.0 | > 3.0 |

### Load rules (wind only)

- Wind ≥ 55 mph → **No Travel** for any load.
- Wind 45–54 mph and load over 30,000 lb → **No Travel**.
- Wind 35–44 mph and load over 40,000 lb → **Severe**.

A checkpoint's level is the **worst** of wind, rain and snow. Missing weather is
shown as **"No data"** and is never counted as Low.

### Turning checkpoints into miles

The road between two neighbouring checkpoints is one stretch, and it takes the
**worse** level of its two ends. Average risk uses scores Low = 0 … No Travel = 4,
weighted by miles.

### Ranking (a later rule only breaks ties)

0. Fewest **No Travel** miles (any No Travel ranks a route below all others)
1. Fewest **Severe** miles
2. Fewest **High** miles
3. Lowest **average risk**
4. Shortest **travel time**

### Colors in the app

| Level | Color |
|---|---|
| Low | green `#1f9d55` |
| Moderate | yellow `#cf9800` |
| High | orange `#e2661a` |
| Severe | red `#b3202b` |
| No Travel | dark maroon `#5e1240` |
| No data | gray `#a8a7a0` |

Every color is always shown next to its text label, so meaning never depends on
color alone.

---

## Design decisions

These resolve points the assessment leaves open:

| Question | Decision |
|---|---|
| "Every 10 / 25 / 50 miles" | The user picks the interval (default 25) |
| A value exactly on a border (0.25 in/hr appears in two columns) | Goes to the higher level; No Travel for rain/snow uses the stated strict ">" |
| Sustained wind or gusts? | Sustained wind for the rules; gusts are shown for information |
| What counts as rain | `rain + showers` (showers carry thunderstorm rainfall) |
| No Travel in the ranking | Ranked below everything (the assessment only lists Severe/High) |
| Heatmap hour 0 | The departure time, so the slider lines up with the ETAs |
| Heatmap area | Grid points within 30 miles of any route, at most 250 |
| How far ahead | Departure up to 7 days ahead (weather forecasts reach ~15 days) |
| Times shown | Calculated in UTC, displayed in the user's own time zone |
| OpenRouteService's built-in "alternative routes" | Not used: on the free API they only work under ~100 km, take ~10 s and often return near-duplicates. Detour routes are used instead. |

---

## Project structure

```
full_stack/
├── README.md                      ← this file
├── .gitignore                     project-wide ignores (secrets, editor/OS files)
│
├── backend/                       Django REST API
│   ├── manage.py
│   ├── requirements.txt           pinned Python packages
│   ├── pytest.ini                 test settings
│   ├── .env.example               template for backend/.env (API key, Django settings)
│   ├── README.md                  backend details and full API reference
│   ├── config/                    Django project: settings.py (env-driven), urls.py, wsgi/asgi
│   └── planner/                   the app
│       ├── constants.py           every threshold and tuning value
│       ├── exceptions.py          API errors + uniform JSON error handler
│       ├── serializers.py         input validation
│       ├── views.py, urls.py      the 4 endpoints
│       ├── clients/               http.py · geocoding_client.py · routing_client.py · weather_client.py
│       ├── services/              trip_planner.py · checkpoints.py · risk.py · recommendation.py · heatmap.py
│       ├── utils/geo.py           distances, polylines, line walking/simplifying, spatial index
│       └── tests/                 246 tests + recorded API responses in fixtures/
│
└── frontend/                      React app (Vite)
    ├── index.html
    ├── package.json               scripts and packages
    ├── vite.config.js             dev server on port 5173
    ├── .env.example               template for frontend/.env (backend URL)
    ├── README.md                  frontend details
    └── src/
        ├── main.jsx, App.jsx      entry point, page layout and shared state
        ├── index.css, App.css     design tokens and layout
        ├── api/                   client.js (fetch, timeouts, errors) · tripApi.js
        ├── hooks/                 useTripPlanner · useHeatmap · useDebounce
        ├── utils/                 risk.js · format.js · geo.js · heatmap.js
        └── components/
            ├── TripForm/          TripForm, PlaceInput (autocomplete)
            ├── Routes/            RecommendationBanner, RouteList, RouteCard, CheckpointTable
            ├── Map/               TripMap, RouteLayer, CheckpointLayer, HeatmapLayer, TruckMarker, MapLegend
            ├── Heatmap/           ForecastSlider
            └── common/            Loader, ErrorMessage, Warnings
```

---

## Setup

### 1. Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Python | 3.11 or newer | `python --version` |
| Node.js | 20.19+ or 22.12+ (needed by Vite 8) | `node --version` |
| npm | comes with Node.js | `npm --version` |
| Git | any recent version | `git --version` |
| OpenRouteService API key | free | see below |

### 2. Get an OpenRouteService API key (free)

1. Sign up at [openrouteservice.org](https://openrouteservice.org/) and confirm your email.
2. Open the **Dashboard**, create a token on the free **Standard** plan, and copy the key.
3. Open-Meteo (weather) and the map tiles need **no key**.

### 3. Get the code

```bash
git clone <your-repository-url> full_stack
cd full_stack
```

### 4. Backend setup

**Windows (PowerShell)**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then open `backend/.env` and set at least:

```ini
ORS_API_KEY=your_openrouteservice_key_here
DJANGO_SECRET_KEY=any-long-random-string
DJANGO_DEBUG=True
```

To generate a secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Finally, create the small local database Django uses for its admin:
```bash
python manage.py migrate
```

| Command | What it does |
|---|---|
| `python -m venv venv` | Creates a private Python environment for this project |
| `activate` | Switches the terminal to that environment (`(venv)` appears) |
| `pip install -r requirements.txt` | Installs the exact package versions the backend needs |
| `copy/cp .env.example .env` | Creates your settings file from the template |
| `python manage.py migrate` | Creates `db.sqlite3` (only Django's admin uses it; trips are cached, not stored) |

### 5. Frontend setup

Open a **second terminal**:

**Windows (PowerShell)**
```powershell
cd frontend
npm install
copy .env.example .env
```

**macOS / Linux**
```bash
cd frontend
npm install
cp .env.example .env
```

`frontend/.env` only holds the backend address and works as-is for local use:
```ini
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

| Command | What it does |
|---|---|
| `npm install` | Downloads React, Vite, MapLibre GL and the other packages into `node_modules/` |
| `copy/cp .env.example .env` | Creates the frontend settings file |

---

## Running the app

You need **two terminals running at the same time**.

**Terminal 1 — backend**
```powershell
cd backend
.\venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
python manage.py runserver
```
Leave it running. Check it at <http://127.0.0.1:8000/api/health/> → `{"status": "ok"}`.

**Terminal 2 — frontend**
```bash
cd frontend
npm run dev
```
Then open **<http://localhost:5173>**.

> Use **localhost**, not 127.0.0.1, for the frontend: the backend only accepts
> browser requests from the addresses in its `CORS_ALLOWED_ORIGINS` setting.

To stop either server, press **Ctrl + C** in its terminal.

### All commands at a glance

| Where | Command | Purpose |
|---|---|---|
| backend | `python manage.py runserver` | Start the API on port 8000 |
| backend | `python -m pytest` | Run the 246 automated tests |
| backend | `python manage.py check` | Django configuration check |
| frontend | `npm run dev` | Start the app on port 5173 (auto-reloads on changes) |
| frontend | `npm run build` | Production build into `frontend/dist/` |
| frontend | `npm run preview` | Serve the production build locally |
| frontend | `npm run lint` | Code-style check (oxlint) |

---

## Using the app

1. Type a city in **Origin** (e.g. "Chicago") and pick it from the list; do the
   same for **Destination** (e.g. "Indianapolis"). You can also type a full
   address without picking.
2. Choose the **departure time** (your local time), the **load weight** and how
   often to **check the weather** (10, 25 or 50 miles).
3. Click **Plan safest route**. A new trip usually takes a few seconds.
4. Read the **recommendation** and compare the **route cards**. Click a card, a
   route line or a route label to select a route.
5. Click a **checkpoint dot** on the map, or a row in the **checkpoint table**,
   to see the weather and risk at the time the truck arrives there.
6. Drag the **forecast slider** or press **play** to watch the weather move over
   the next 48 hours. The truck icon shows where the selected truck will be.

Try a heavier load (e.g. 45,000 lb vs 20,000 lb) on a windy day to see the load
rules change the risk.

---

## Testing and quality checks

### Backend — 246 automated tests

```bash
cd backend
python -m pytest            # add -v to list every test
```

The tests run **offline**: recorded OpenRouteService and Open-Meteo responses
(`planner/tests/fixtures/`) replace the real services, so no API key or
internet is needed.

| File | What it proves |
|---|---|
| `test_risk.py` | Every border of the wind/rain/snow table, all load rules, worst-of-three, missing data |
| `test_checkpoints.py` | Checkpoints every 10/25/50 miles, ETAs follow road-step speeds, UTC handling |
| `test_recommendation.py` | Each ranking rule in order, No Travel handling, reason text, warnings |
| `test_geo.py` | Distances, polyline decoding, walking and simplifying lines, route overlap |
| `test_clients.py` | Talking to the outside APIs: parsing, caching, batching, retries, errors |
| `test_heatmap.py` | Corridor grid, 49 hours, same risk rules and load as checkpoints |
| `test_api.py` | Every endpoint: input checks, full pipeline output, error format, rate limits |

### Frontend

```bash
cd frontend
npm run lint                # oxlint: no warnings
npm run build               # production build must succeed
```

The full flow (autocomplete, planning, route selection, checkpoint popups,
slider and play, error messages, mobile layout) was also checked in a real
browser against the running backend.

---

## API reference

Base URL: `http://127.0.0.1:8000/api`. Every error has the same shape:
`{"error": {"code": "...", "message": "...", "fields": {...}}}` (`fields` only for
input errors). Full examples are in [backend/README.md](backend/README.md).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health/` | `{"status": "ok"}` — the server is running |
| GET | `/geocode/?q=Chic` | Up to 5 US place suggestions `{name, lat, lon}` |
| POST | `/plan-trip/` | 3 routes, checkpoints, risk, recommendation, warnings, `trip_id` |
| GET | `/heatmap/?trip_id=…` | Grid points + 49 hourly frames of risk, wind, rain and snow |

**Plan-trip request**
```json
{
  "origin": "Chicago, IL",
  "destination": {"lat": 39.7684, "lon": -86.1581, "name": "Indianapolis, IN"},
  "departure_time": "2026-10-14T14:00:00Z",
  "load_weight_lb": 45000,
  "checkpoint_interval_miles": 25
}
```

**Plan-trip response (shortened)**
```json
{
  "trip_id": "40b3ed80857f4ad789f2ba6f8eac7971",
  "origin": {"name": "Chicago, IL, USA", "lat": 41.879, "lon": -87.661},
  "departure_time": "2026-10-14T14:00:00+00:00",
  "routes": [{
    "id": "A", "via": "I-94", "rank": 1, "is_recommended": true,
    "geometry": [[41.879, -87.661], "..."],
    "summary": {
      "distance_miles": 186.1, "duration_minutes": 280.9,
      "arrival_time": "2026-10-14T18:40:54+00:00",
      "miles_by_level": {"Low": 186.1, "Moderate": 0, "High": 0, "Severe": 0, "No Travel": 0, "No data": 0},
      "average_risk": 0.0, "max_level": "Low", "checkpoint_count": 9
    },
    "checkpoints": [{
      "index": 1, "mile": 25.0, "lat": 41.577, "lon": -87.569,
      "eta": "2026-10-14T14:43:50+00:00", "forecast_time": "2026-10-14T15:00:00+00:00",
      "weather": {"wind_mph": 9.2, "gust_mph": 16.1, "rain_in_per_hr": 0.0, "snow_in_per_hr": 0.0},
      "risk": {"level": "Low", "score": 0, "wind": "Low", "rain": "Low", "snow": "Low",
               "reason": "Low: no significant wind, rain or snow"}
    }]
  }],
  "recommendation": {"route_id": "A", "reason": "Route A is recommended (…)."},
  "warnings": []
}
```

| Status | Code | When |
|---|---|---|
| 400 | `invalid_input` / `invalid_trip` | Wrong fields; origin and destination are the same |
| 404 | `location_not_found` / `trip_not_found` | Unknown place; heatmap trip expired (kept 1 hour) |
| 422 | `no_route` | No truck route (e.g. a point in the sea) |
| 429 | `throttled` / `service_rate_limited` | Too many requests here, or an outside API limit |
| 502 | `service_unavailable` | OpenRouteService / Open-Meteo down, slow or rejecting the key |

---

## Configuration

### `backend/.env`

| Variable | Default | Meaning |
|---|---|---|
| `ORS_API_KEY` | — (required) | OpenRouteService key |
| `DJANGO_SECRET_KEY` | dev-only value | Django secret key (set your own) |
| `DJANGO_DEBUG` | `False` | `True` for local development |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts the API answers to |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Frontend addresses allowed to call the API |
| `OPEN_METEO_BASE_URL` | Open-Meteo forecast URL | Weather API address |
| `EXTERNAL_API_TIMEOUT` | `15` | Seconds to wait for an outside API |
| `CACHE_DIR` | `backend/.cache` | Where cached answers are stored |
| `THROTTLE_PLAN_TRIP` / `THROTTLE_HEATMAP` / `THROTTLE_GEOCODE` | `20/min` / `30/min` / `90/min` | Per-client request limits |
| `LOG_LEVEL` | `INFO` | Backend log detail |
| `NUM_PROXIES`, `CSRF_TRUSTED_ORIGINS`, `SECURE_SSL_REDIRECT` | — | Production only (see deployment notes) |

### `frontend/.env`

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api` | Backend API address (no trailing slash) |

Both `.env` files are ignored by Git; only the `.env.example` templates are committed.

---

## Performance

- **Backend:** main route and first detours are fetched in parallel; weather is
  fetched in batches of up to 100 points, in parallel; answers are cached
  (geocoding 24 h, routes 1 h, weather 30 min, trips and heatmaps 1 h); route
  lines are simplified before sending; responses are gzip-compressed.
- **Frontend:** the map draws on the graphics card and React only hands it new
  data; all 49 heatmap hours are prepared once, so the slider just swaps data
  with no network calls; MapLibre (~1 MB) loads in its own file after the page
  is usable; place search waits for typing to pause and cancels old requests.
- **Typical timings** (real APIs): a new trip in about 1–5 s, the heatmap in
  1–3 s, a repeated trip in under 1 s. The outside services are occasionally
  much slower; the app then shows a progress message and waits up to 3 minutes.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Frontend says **"Can't reach the server"** | Start the backend (`python manage.py runserver`) and check <http://127.0.0.1:8000/api/health/> |
| Browser console shows a **CORS** error | Open the app at `http://localhost:5173` (not 127.0.0.1), or add your address to `CORS_ALLOWED_ORIGINS` in `backend/.env` and restart the backend |
| **"Service unavailable … API key or quota problem"** | Check `ORS_API_KEY` in `backend/.env` (no quotes or spaces), then restart the backend |
| **Port 5173 is already in use** | Close the other dev server; the port is fixed because the backend's CORS setting expects it |
| **Port 8000 is already in use** | Stop the other process, or run `python manage.py runserver 8001` and set `VITE_API_BASE_URL=http://127.0.0.1:8001/api` |
| **Planning takes a long time** | The outside routing/weather services are slow at that moment; wait or try again. Repeating a trip is fast because of caching |
| **"Too many requests"** | The per-client limit was reached; wait a minute |
| **"Trip not found or expired"** on the heatmap | Trips are kept for 1 hour; plan the trip again |
| **Map stays blank** | The map tiles need an internet connection; reload the page |
| `npm install` or `npm run dev` fails | Check `node --version` (Vite 8 needs Node 20.19+ or 22.12+) |
| PowerShell won't run `activate` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again |

---

## Deployment notes

The app is two separate services.

**Backend** (e.g. Render, Railway), root directory `backend`:
- Build: `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate --no-input`
- Start: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- Environment: `ORS_API_KEY`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`,
  `DJANGO_ALLOWED_HOSTS=<backend host>`, `CORS_ALLOWED_ORIGINS=<frontend URL>`,
  `CSRF_TRUSTED_ORIGINS=https://<backend host>`, `NUM_PROXIES=1`
- Health check path: `/api/health/`

**Frontend** (any static host, e.g. Netlify, Vercel, Render static site), root directory `frontend`:
- Build: `npm install && npm run build`
- Publish directory: `dist`
- Environment: `VITE_API_BASE_URL=https://<backend host>/api` (set before building)

---

## Known limitations

- **No driver rest breaks.** ETAs assume non-stop driving; legal hours-of-service
  breaks are not modelled, so ETAs on very long trips are earlier than in reality.
- **Strict ranking.** As specified, a route can be recommended even if it is much
  longer, as long as it ranks better on Severe / High miles or average risk.
- **Hourly weather.** Each checkpoint uses the forecast hour nearest its ETA;
  values between hours are not interpolated.
- **Fewer than 3 routes** is possible in rare cases (very remote or coastal trips);
  the app then shows a warning.
- **Detour routes** can include a short out-and-back where they pass through
  their via-point; it does not affect the risk results.
- **Free API limits.** OpenRouteService and Open-Meteo free plans have daily and
  per-minute limits; caching keeps normal use well within them.
- **US places.** Place search is limited to the United States.
