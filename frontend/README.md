# Weather-Aware Truck Routing — Frontend

React (Vite) app for the Django backend in `../backend`. The driver enters a
trip; the app shows 3 truck routes on a map, a weather checkpoint every
10 / 25 / 50 miles with the risk at the truck's arrival time, a route
recommendation, and a 0–48 h weather heatmap along the trip corridor.

## Run it

You need **Node.js 20+** and the backend running on `http://127.0.0.1:8000`
(see `../backend/README.md`).

```bash
cd frontend
npm install
cp .env.example .env    # points the app at the backend API
npm run dev             # http://localhost:5173
```

Other commands: `npm run build` (production build in `dist/`),
`npm run preview` (serve that build), `npm run lint`.

> The backend only accepts requests from the origins in its
> `CORS_ALLOWED_ORIGINS` setting (`http://localhost:5173` by default), so open
> the app at **localhost**, not 127.0.0.1.

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api` | Backend API address (no trailing slash) |

## What the user sees

- **Trip form** – origin/destination with place suggestions, departure time
  (in the user's own time zone), load weight, checkpoint interval.
- **Recommendation** – the best route and the backend's reason, plus warnings.
- **Route cards** – distance, drive time, arrival time, a bar of miles per risk
  level, No Travel / Severe / High miles and average risk. Click to select.
- **Checkpoint table** – every checkpoint of the selected route; click a row to
  open it on the map.
- **Map** (MapLibre GL, CARTO/OpenStreetMap tiles, no key) – the selected route
  in blue, others gray, each labelled with its letter and drive time;
  checkpoint dots colored by risk with a details popup (ETA, forecast hour,
  wind, gusts, rain, snow, reason); start/end markers; legend.
- **Forecast bar** – 0–48 h slider with play/pause, heatmap on/off. The heatmap
  and a truck icon (where the selected truck is at that hour) follow the slider.

All times come from the API in UTC and are shown in the browser's time zone.

## How it talks to the backend

| When | Request | Used for |
|---|---|---|
| Typing ≥ 3 letters (300 ms pause) | `GET /api/geocode/?q=` | Place suggestions |
| "Plan safest route" | `POST /api/plan-trip/` | Routes, checkpoints, recommendation, warnings |
| Right after a trip arrives | `GET /api/heatmap/?trip_id=` | 49 hourly heatmap frames |

Backend errors (`{"error": {"code", "message", "fields"}}`) are shown as a
readable message; field errors appear under the matching input. The form also
checks the same limits as the backend before sending.

## Code layout

```
src/
  api/          client.js (fetch, timeouts, errors) · tripApi.js (the 3 endpoints)
  hooks/        useTripPlanner · useHeatmap · useDebounce
  utils/        risk.js (levels + colors) · format.js (local times, durations)
                geo.js (truck position, bounds) · heatmap.js (prepares 49 frames)
  components/
    TripForm/   TripForm, PlaceInput (autocomplete)
    Routes/     RecommendationBanner, RouteList, RouteCard, CheckpointTable
    Map/        TripMap, RouteLayer, CheckpointLayer, HeatmapLayer, TruckMarker, MapLegend
    Heatmap/    ForecastSlider
    common/     Loader, ErrorMessage, Warnings
  App.jsx       layout and shared state (trip, selected route, hour)
```

## Performance notes

- The map draws on the GPU; React components only hand MapLibre new data.
- All 49 heatmap hours are turned into map layers once when they arrive, so the
  slider (and play) just swaps data — no network calls or recalculation.
- MapLibre (~1 MB) loads in its own file after the page is usable.
- Place search waits for typing to pause and cancels outdated requests.
