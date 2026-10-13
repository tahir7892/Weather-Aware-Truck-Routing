# Weather-Aware Truck Routing — Backend

Django REST API that finds 3 truck routes between two places, checks the weather
the truck will meet at each checkpoint **at the time it gets there**, rates the
risk with the assessment's wind/rain/snow and load rules, and recommends the
safest route. It also serves a 0–48 h weather heatmap along the trip corridor.

| Need | Service | Key |
|---|---|---|
| Geocoding and autocomplete | [OpenRouteService](https://openrouteservice.org/) | Free key |
| Truck routing (`driving-hgv`) | OpenRouteService | Same key |
| Hourly weather | [Open-Meteo](https://open-meteo.com/) | None |

## Quick start

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then put your ORS key in ORS_API_KEY
python manage.py migrate
python manage.py runserver        # http://127.0.0.1:8000/api/health/
```

Run the tests (offline; external APIs are faked with recorded responses):

```bash
python -m pytest
```

## How a trip is planned

```
POST /api/plan-trip/
  1. Validate input                       serializers.py
  2. Geocode origin/destination            clients/geocoding_client.py
  3. Get 3 distinct truck routes           clients/routing_client.py
  4. Checkpoints every 10/25/50 mi + ETAs  services/checkpoints.py
  5. Hourly weather at each ETA            clients/weather_client.py
  6. Risk level per checkpoint             services/risk.py
  7. Miles per level, average risk         services/recommendation.py
  8. Rank routes, explain the choice       services/recommendation.py
     (orchestrated by services/trip_planner.py)

GET /api/heatmap/?trip_id=...              services/heatmap.py
```

**Routes.** ORS returns the fastest truck route. Two more come from forcing the
route through a via-point pushed left or right of the trip's midpoint (15%, then
30%/45% of the trip length if needed). Via-points are snapped to truck roads
first. Near-duplicates (>85% shared road) and detours over 1.5× the main
route's time are dropped. The truck's gross weight (35,000 lb assumed empty
weight + load) is sent to ORS so weight-restricted roads are avoided.
ORS's built-in alternative routes are not used: on the free API they only
work under ~100 km, take ~10 s and often return near-duplicates.

**ETAs.** ORS gives a duration for every step of the road, so ETAs follow real
speeds (slow city streets, fast highways) instead of one average speed. All
times are UTC internally and returned as ISO 8601 with an offset.

**Weather.** Open-Meteo hourly `wind_speed_10m`, `wind_gusts_10m`, `rain`,
`showers`, `snowfall` in mph and inches. Each checkpoint uses the hour nearest
its ETA (08:29 → 08:00, 08:30 → 09:00). Points are rounded to 0.1° so nearby
checkpoints share a lookup; up to 100 points go in one request and batches run
in parallel.

## Risk rules

Thresholds (from the assessment) live in [`planner/constants.py`](planner/constants.py):

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25 – < 35 | 35 – < 45 | 45 – < 55 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10 – < 0.25 | 0.25 – < 0.50 | 0.50 – 1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5 – < 1.0 | 1.0 – < 2.0 | 2.0 – 3.0 | > 3.0 |

Load rules (wind only): 45–54 mph with a load over 30,000 lb → No Travel;
35–44 mph with a load over 40,000 lb → Severe. A checkpoint's level is the
worst of wind, rain and snow.

## Recommendation

Each stretch of road between two neighbouring checkpoints takes the **worse**
level of its two ends. Routes are then ranked strictly in this order — a later
rule only breaks ties:

0. Fewest No Travel miles (any No Travel ranks a route below all others)
1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk (Low=0 … No Travel=4, weighted by miles)
4. Shortest travel time

The response includes a plain-English reason, e.g. *"Route B is recommended
(vs Route A: fewer Severe miles (0.0 vs 40.0); vs Route C: shorter travel
time (4 h 41 min vs 5 h 22 min))."*, plus warnings (every route has No Travel,
the best route still has Severe miles, weather data missing).

## Decisions on points the assessment leaves open

| Question | Decision |
|---|---|
| "Every 10 / 25 / 50 miles" | The user picks the interval (default 25) |
| Border values (0.25 in/hr is in two columns) | Border goes to the higher level; No Travel rain/snow use the PDF's strict ">" |
| Sustained wind or gusts | Sustained wind for the rules; gusts returned for display |
| Rain | `rain + showers` (showers carry thunderstorm rainfall) |
| Missing weather | "No data" — never counted as Low; reported in warnings |
| No Travel in the ranking | Ranked below everything (the PDF lists only Severe/High) |
| Heatmap hour 0 | Departure time (rounded to the hour), so it lines up with ETAs |
| Heatmap area | Grid points within 30 miles of any route, at most 250 points |
| How far ahead | Departure up to 7 days ahead (30 min in the past allowed for "leave now") |

**Known simplifications:** ETAs assume non-stop driving (no hours-of-service
rest breaks); weather is snapped to whole hours; the ranking is strictly
lexicographic as specified, so a much longer route can win on lower risk.

## API

All errors share one shape: `{"error": {"code", "message", "fields"?}}`.

### `GET /api/health/`
`{"status": "ok"}`

### `GET /api/geocode/?q=Nashvil`
`{"results": [{"name": "Nashville, TN, USA", "lat": 36.2369, "lon": -86.8347}, ...]}` — US places, `q` ≥ 3 characters.

### `POST /api/plan-trip/`

```json
{
  "origin": "Chicago, IL",
  "destination": {"lat": 39.7684, "lon": -86.1581, "name": "Indianapolis, IN"},
  "departure_time": "2026-10-13T14:00:00Z",
  "load_weight_lb": 42000,
  "checkpoint_interval_miles": 25
}
```

`origin`/`destination` accept text or coordinates (from autocomplete).
Response (abridged):

```json
{
  "trip_id": "9f1c…",
  "origin": {"name": "Chicago, IL, USA", "lat": 41.8781, "lon": -87.6298},
  "departure_time": "2026-10-13T14:00:00+00:00",
  "routes": [{
    "id": "A", "via": "I-94 / I-65", "rank": 1, "is_recommended": true,
    "geometry": [[41.8781, -87.6298], ...],
    "summary": {
      "distance_miles": 186.1, "duration_minutes": 280.9,
      "arrival_time": "2026-10-13T18:40:54+00:00",
      "miles_by_level": {"Low": 186.1, "Moderate": 0, "High": 0, "Severe": 0, "No Travel": 0, "No data": 0},
      "average_risk": 0.0, "max_level": "Low", "checkpoint_count": 9
    },
    "checkpoints": [{
      "index": 3, "lat": 41.3, "lon": -87.3, "mile": 75.0,
      "eta": "2026-10-13T15:52:10+00:00", "forecast_time": "2026-10-13T16:00:00+00:00",
      "weather": {"wind_mph": 12.4, "gust_mph": 21.0, "rain_in_per_hr": 0.0, "snow_in_per_hr": 0.0},
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
| 400 | `invalid_input` / `invalid_trip` | Bad fields; same origin and destination |
| 404 | `location_not_found` | Place not found |
| 422 | `no_route` | No truck route (e.g. a point at sea) |
| 429 | `throttled` / `service_rate_limited` | Our per-client limit, or an upstream API limit |
| 502 | `service_unavailable` | ORS/Open-Meteo down, slow, or rejecting the key |

### `GET /api/heatmap/?trip_id=…`
Uses the routes saved by `plan-trip` (cached for 1 hour). Returns all 49
hourly frames at once so a slider never waits on the network:

```json
{
  "start_time": "2026-10-13T14:00:00+00:00",
  "hours": [0, 1, …, 48], "times": ["…"],
  "grid_spacing_miles": 9.1, "corridor_miles": 30,
  "points": [[41.2, -87.9], …],
  "frames": [{"risk": [0, 2, null, …], "wind_mph": […], "rain_in_per_hr": […], "snow_in_per_hr": […]}]
}
```
`frames[h].risk[i]` is the 0–4 score at `points[i]`, hour `h` (null = no data),
computed with the same rules and load weight as the checkpoints.

## Performance and resilience

- Main route and first detours are fetched in parallel; weather batches too.
- Route lines are simplified (Douglas-Peucker, 30 m) before sending; responses are gzip-compressed.
- File-based cache shared by all gunicorn workers: geocoding 24 h, routes 1 h, weather 30 min, trips/heatmaps 1 h.
- Brief network errors and 502/503/504 are retried; if some weather batches still fail, those points show "No data" and the trip still completes.
- Per-client rate limits protect the free API quotas: plan-trip 20/min, heatmap 30/min, geocode 90/min.

Typical timings (real APIs, cold cache): Chicago → Indianapolis ~1–4 s,
Dallas → Denver at 10-mile checkpoints (266 checkpoints) ~5 s; heatmap ~1–2 s;
repeated trips ~0.5 s.

## Project layout

```
config/            settings (env-driven), root URLs
planner/
  constants.py     every threshold and tuning value
  exceptions.py    API errors + uniform JSON error handler
  serializers.py   input validation
  views.py         thin endpoints
  clients/         the only code that calls external APIs
  services/        pure logic: risk, checkpoints, recommendation, heatmap, pipeline
  utils/geo.py     distances, polyline decoding, line walking/simplifying
  tests/           unit + API tests, recorded API responses in fixtures/
```

## Deploying (Render example)

- Root directory: `backend`
- Build command: `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate --no-input`
- Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- Environment: `ORS_API_KEY`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`,
  `DJANGO_ALLOWED_HOSTS=<your-app>.onrender.com`, `CORS_ALLOWED_ORIGINS=<frontend URL>`,
  `CSRF_TRUSTED_ORIGINS=https://<your-app>.onrender.com`, `NUM_PROXIES=1`
- Health check path: `/api/health/`
