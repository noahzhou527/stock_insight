# Stock Insight

A local, single-user stock research app for China A-shares, US stocks and Korean stocks. A FastAPI
backend pulls free public data (Tonghuashun, Eastmoney, Yahoo Finance), stores daily bars
incrementally in SQLite, and serves a React single-page app on one port.

For personal research only. Nothing in the app is investment advice.

## Features

| Page | What it shows |
| --- | --- |
| **个股** `/stock/:market/:symbol` | Quote header and attribute bar (range and 52-week high/low, average volume, largest turnover day, volatility, market cap, PE TTM / static / dynamic, TTM net profit); K-line with MA, BBI and BOLL and a volume / amount / RSI / MACD sub-chart; intraday chart with average price, previous-close line, %-axis and no lunch-break gap; tabs for 技术信号 (descriptive, rule-based), 财务报表, 同业对比 and 数据明细 with CSV export; KRW / USD switch for Korean stocks |
| **自选** `/watchlist` | A-share watchlist: equal-weight summary, relative to CSI 300, add / remove / undo, filter, sort, optional columns including an intraday sparkline |
| **市场** `/market/:market` | Index cards for CN / US / KR, up/down breadth, intraday chart of the selected index |
| **排行** `/rankings` | The curated A-share pool ranked by change, turnover, market cap, PE TTM or latest quarterly profit |
| **新闻** `/news` | Last 72 hours from Yahoo Finance, Tonghuashun and Douyin hot topics, with per-source status |

Every data block shows where its data came from and how fresh it is (实时 / 已收盘 / 盘中合成 /
备用源 / 缓存). During a market's trading hours its data refreshes every 30 seconds; outside them
nothing is polled. Search any code with **Ctrl+K** (`300308`, `SZ300308`, `中际旭创`, `AAPL`,
`005930.KS`, …). Dark and light themes; up/down colours follow each market's convention.

## Quick start (Windows)

Requirements: **Python 3.11+** on `PATH`, and **Node.js 20+** for the first run (to build the frontend).

Double-click **`start.bat`**. It:

1. creates `.venv` and installs `backend/requirements.txt` (again only when that file changes),
2. builds `frontend/dist` if it does not exist yet,
3. on the very first run, imports any legacy `data/cache/` CSVs into the database (read-only),
4. starts the server at http://127.0.0.1:8000 and opens the browser.

Closing the window stops the server. Options: `set STOCK_INSIGHT_PORT=8010` to use another port,
`set STOCK_INSIGHT_NO_BROWSER=1` to skip opening the browser. After pulling frontend changes,
delete `frontend\dist` (or run `npm run build` in `frontend`) so it is rebuilt.

## Development

```bash
# backend (from the repo root)
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements.txt
.venv\Scripts\python -m uvicorn backend.app.main:app --reload --port 8000
```

```bash
# frontend dev server with hot reload; proxies /api to 127.0.0.1:8000
cd frontend
npm ci
npm run dev
```

The API documentation is at http://127.0.0.1:8000/docs. After changing a backend DTO, regenerate the
frontend types with `npm run gen:api` (in `frontend`).

### Tests

| Command | Where | What |
| --- | --- | --- |
| `.venv\Scripts\python -m pytest backend/tests` | repo root | Backend unit and API tests, offline on recorded golden samples |
| `.venv\Scripts\python -m pytest backend/tests -m network` | repo root | Live checks against the real data sources |
| `npm test` | `frontend` | Vitest unit tests |
| `npm run e2e` | `frontend` | Builds the SPA, then Playwright smoke tests against the real backend wired to fake data sources (offline). Uses the installed Microsoft Edge; set `PW_CHANNEL=chrome` to use Chrome |
| `npm run lint` | `frontend` | oxlint |

## Configuration

Environment variables (or a `.env` file in the repo root), all prefixed with `STOCK_INSIGHT_`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `STOCK_INSIGHT_DB_PATH` | `data/stock_insight.db` | SQLite database |
| `STOCK_INSIGHT_FRONTEND_DIST` | `frontend/dist` | Built SPA served by the backend |
| `STOCK_INSIGHT_DISABLED_PROVIDERS` | `[]` | Skip data sources, e.g. `'["eastmoney"]'` |
| `STOCK_INSIGHT_REQUEST_TIMEOUT_S` | `20` | Upstream request timeout |
| `STOCK_INSIGHT_MIN_REQUEST_INTERVAL_S` | `0.3` | Minimum gap between requests to one source |

No API keys or tokens are needed.

## Data

| Market | Data | Sources (in fallback order) |
| --- | --- | --- |
| A-shares (SH / SZ / BJ) | Daily bars, intraday | Tonghuashun → Eastmoney |
| A-shares | Valuation, financial reports | Tonghuashun F10 |
| A-shares | Watchlist / ranking quotes, market breadth | Eastmoney (breadth falls back to the local stock pool, marked "非全市场") |
| US / Korea | Daily bars, intraday, financials, breadth (US) | Yahoo Finance |

- Daily bars are stored incrementally: only missing ranges are fetched, the recent tail is re-checked
  at most every 5 minutes, and a change of adjustment basis triggers a full refetch. Today's bar,
  built from intraday data before the close, is drawn as a hollow candle and never stored.
- Other responses go through a read-through cache. When a source fails, the last good copy is shown
  and marked 缓存.
- The stock pool (A-share sector groups plus the US and Korean shortlists) is seeded from
  `backend/app/seed/universe.json` into an empty database on first start; after that the database is
  the source of truth.
- Preferences (theme, default indicators, watchlist columns and sort, sidebar, last page) are stored in
  the database through `/api/prefs`.

### Local data retention policy

`data/` holds reusable local data, not disposable build output: the SQLite database
(`stock_insight.db`) and the legacy `data/cache/` files from the Streamlit edition.

- Do not delete `data/` or `data/cache/` during repository or dependency cleanup.
- Remove individual entries only when they are corrupt or the user asks for it; never bulk-delete
  valid history.
- Everything under `data/` stays local and is excluded from Git (the `.gitkeep` keeps the folder).

## Project structure

```text
backend/
  app/
    api/         routes, DTOs (OpenAPI), unified Chinese error bodies
    providers/   Tonghuashun, Eastmoney, Yahoo, Stooq (disabled) + composite fallback routing
    domain/      pure rules: indicators, sessions, snapshot, signals, rankings, formatting
    services/    daily-bar sync, read-through cache, one service per page
    db/, repo/   SQLAlchemy models, Alembic migrations, queries
    news/        news collection and de-duplication
    seed/        built-in stock pool
  scripts/       migrate_legacy_cache, record_fixtures, export_openapi
  tests/         pytest suites, golden samples, e2e_server for Playwright
frontend/
  src/routes/    one file per page; search.ts holds the URL parameter rules
  src/charts/    lightweight-charts K-line and intraday charts
  src/components/, src/lib/, src/theme/
  e2e/           Playwright smoke tests
docs/            plan-b-draft.md (design and acceptance checklist), frontend-upgrade-audit.md
start.bat        Windows launcher
```

## Limitations

- Free public sources can change, rate-limit or block an IP at any time. Eastmoney is the only source
  for watchlist and ranking quotes and for full-market A-share breadth; when it is unreachable those
  show cached or missing data.
- Trading sessions follow fixed weekday hours; exchange holidays are not modelled (on a holiday the
  page shows 已收盘 with the last trading day).
- 技术信号 are fixed descriptive rules, not predictions.

## Branches

| Branch | Purpose |
| --- | --- |
| `main` | Public-data edition (Streamlit) |
| `public-data` | Same line as `main`, kept under its own name |
| `feat/spa` | This FastAPI + React rewrite (docs/plan-b-draft.md) |
| `archive/ifind` | Archived iFinD API edition (tag `ifind-archive-2026-11-11`); not maintained |
