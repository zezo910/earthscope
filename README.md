# EarthScope — Earth Systems Trend Detective

NASA Space Apps 2026 · *Be An Earth System Trend Detective!*

## Project structure

```
earthscope/
├── frontend/                 the EarthScope website (same design as earth-scope-detective.base44.app)
│   ├── index.html
│   ├── assets/               the site's compiled JavaScript + CSS (exported from Base44)
│   └── logo.png
├── backend/                  Python server: serves the website + the EarthScope API
│   ├── app/
│   │   ├── main.py           website, /api routes, pass-through to Base44
│   │   ├── core.py           queries, scoring, players
│   │   └── config.py         every path / URL in one place
│   ├── db/                   schema.sql, cases.json (8 cases, EN + AR)
│   ├── pipeline/             build.py (CSV → stats + SQLite), export_static.py
│   └── requirements.txt
├── data/
│   ├── raw/                  the 25 NASA CSV downloads
│   └── processed/            earthscope.db, index.json, series/*.json  (generated)
├── analysis/trend_report.py  stand-alone report: summaries, summary.csv, PNG plots
├── case-game/                the 8-case React game (source; not linked into the site yet)
└── tests/e2e/                browser test for case-game
```

## Setup (once)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
```

No Node.js / npm needed to run the website.

## Run

```powershell
cd backend
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000** — the full site: Home, Explore Data, Compare Regions, Earth Detective, Achievements, About.
API docs: **http://127.0.0.1:8000/docs**.
VS Code: `Ctrl+Shift+P` → **Tasks: Run Task** → **Run EarthScope**.

**Needs internet:** the Explore / Compare data, the AI helper and saved player profiles run as Base44 cloud
functions. The local server forwards those calls to the live Base44 app (`EARTHSCOPE_BASE44_URL` in `config.py`).

## Changing the design

`frontend/assets/` is compiled code, so edit the design in **Base44**, then download the site again and replace
`frontend/assets/` (and the two file names in `frontend/index.html` if they changed).

## Rebuild the data

```powershell
python backend/pipeline/build.py
python backend/pipeline/export_static.py
python analysis/trend_report.py        # optional: report + plots
```

## case-game (optional)

Needs Node.js and a network that allows npmjs.org:
```powershell
cd case-game
npm install
npm run dev        # http://localhost:5173 (uses the backend on :8000 if it is running)
```

## API

`GET /api/health` · `/api/catalog` · `/api/series` · `/api/series/{variable}/{region}` · `/api/stats/{variable}/{region}?period=` · `/api/compare?variable=&regions=a,b` · `/api/cases` · `/api/cases/{id}` · `/api/players/{device_id}` · `/api/leaderboard`
`POST /api/season-check` · `/api/cases/{id}/attempt` · `PUT /api/players/{device_id}`

## Method

Daily NO2 → monthly mean (≥5 valid days) / 1e15; K → °C; IMERG mm/hr → mm/month. Monthly anomaly = value − that calendar month's mean; annual = mean of anomalies (years with <10 months dropped). Mann-Kendall + OLS on annual anomalies: both p<0.05 = significant, one = weak, none = no evidence. Weatherhead n* from detrended monthly anomalies. Benjamini-Hochberg (q=0.05) across all 25 series.
