# Stock Insight

**Interactive Financial Data Analysis Dashboard**

A Streamlit and Plotly app for personal stock research across US, Korean, and China A-share equities. It combines historical price analysis, intraday monitoring, technical indicators, valuation snapshots, financial reports, and rule-based investment observations in one local dashboard.

## Product Overview

Stock Insight currently supports:

- Market data through official iFinD HTTP interfaces; overseas coverage depends on account permissions and confirmed symbols
- China A-share daily OHLCV, minute bars, quotes and financial data from iFinD
- A curated A-share universe focused on AI hardware and advanced manufacturing
- Custom ticker input for US and China A-share markets, plus a curated Korean-stock view
- Candlestick charts with MA, optional BBI, optional BOLL, and market-specific red/green colors
- Price-analysis subplot switching between volume and traded amount
- Trading-calendar cleanup that hides weekends and missing exchange sessions
- Intraday charts with price, average price, previous close, percentage scale, and volume/traded-amount toggle
- Korean-stock display-currency toggle between Korean won and US dollars, including prices, charts, market cap, and financial reports
- New-listing safeguards for incomplete history, including first-day K-line rendering and indicator/data-detail guards
- A-share valuation overview with PE TTM, static PE, dynamic PE, and market cap
- Full-universe A-share rankings for intraday gain, traded amount, market cap, and PE TTM
- Original news view preserved in the public-data backup; excluded from the iFinD edition
- Financial reports with the most recent four fiscal years and four reported quarters
- RSI and MACD technical indicator panels
- A dedicated indicator explanation page
- CSV export for loaded historical price data
- A-share watchlist overview with equal-weight daily performance, breadth, sortable quotes, and round-trip stock analysis; manual refresh by default, with optional 60-second automatic refresh during trading sessions determined by the official trading calendar

## Project Structure

```text
stock_insight/
|-- app.py                 # Main Streamlit application
|-- market_overviews.py    # Market overview, ranking, and news views
|-- services/              # Cached data-access and data-range services
|-- app_config.py          # App settings, page setup, and shared constants
|-- sidebar.py             # Sidebar controls
|-- *_view.py              # Financial report and investment insight views
|-- ifind_data.py          # Active official iFinD HTTP provider
|-- data_fetcher.py        # Legacy helpers and shared error/formatting utilities
|-- market_snapshot.py     # Batch A-share rankings and snapshot cache
|-- news_fetcher.py        # Three-source financial-news aggregation
|-- analysis.py            # Technical indicator calculations
|-- visualization.py       # Plotly chart builders
|-- indicator_help.py      # Indicator explanation page
|-- a_share_universe.py    # Curated A-share stock universe
|-- requirements.txt       # Python dependencies
|-- .streamlit/            # Streamlit configuration and secrets template
|-- assets/                # Static assets
|-- data/                  # Local data files
|-- tests/                 # Five topic-based regression test modules
`-- README.md
```

## Installation & Local Run

1. **Clone the repository**

   ```bash
   git clone https://github.com/noahzhou527/stock_insight.git
   cd stock_insight
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**

   On Windows, double-click `start.bat` (or run it in a terminal). It reuses the
   project's `.venv`, creates it and installs dependencies on first run, then
   starts the app on port 8501 and opens the browser automatically.

   Alternatively, run it manually with the project's virtual environment
   (do **not** use the global Python — it usually has no Streamlit installed):

   ```bash
   .venv\Scripts\python -m streamlit run app.py --server.port 8501
   ```

5. **Access the app**

   Open your browser and go to `http://localhost:8501`.

If port 8501 is already taken, Streamlit exits with
`Port 8501 is already in use` — stop the old process first
(`netstat -ano | findstr :8501` shows its PID, then `taskkill /PID <pid> /F`).

## Tests

Tests are grouped by responsibility instead of by individual feature:
`business_rules`, `data_fetcher`, `market_data`, `news_fetcher`, and
`visualization`.

```bash
python -m unittest discover -s tests -v
```

## Local Cache Retention Policy

`data/cache/` is reusable local project data, not disposable build output. Historical price CSV files and financial-report JSON files should be retained across app runs so previously fetched history can be reused and repeated provider requests can be reduced.

- Do not delete `data/cache/` during routine repository cleanup, dependency cleanup, or Smart Push preparation.
- When refreshing data, preserve valid historical rows and fetch only the missing or current range whenever the provider workflow supports it.
- Remove individual cache entries only when they are corrupt, incompatible with a parser change, or explicitly requested by the user. Do not bulk-delete valid history.
- Financial-report cache expiry is already handled by the application for entries unused for 30 days; manual blanket cleanup is unnecessary.
- Cache contents remain local and are excluded from Git. The `.gitkeep` exception only preserves the cache directory structure.

## Deployment

The app can be deployed on Streamlit Community Cloud.

1. Push the repository to GitHub.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create a new app from this repository.
4. Set the entry point to `app.py`.
5. Add `THS_ACCESS_TOKEN` in Streamlit secrets if your deployment needs it.

Streamlit will provide a public `*.streamlit.app` URL after deployment.

## Version branches

Both editions are kept as branches in this repository and run from the same project directory:

| Branch | Data source | Configuration |
| --- | --- | --- |
| `codex/ifind` | Official iFinD HTTP APIs | Valid iFinD credentials and data permissions required |
| `codex/public-data` | Original Tonghuashun public pages, Yahoo Finance and public-provider requests | No iFinD credentials needed for normal public-data paths |

Run `git switch codex/public-data` for the original public-data edition or `git switch codex/ifind` for the API edition, then run `start.bat` (http://localhost:8501). Stop any running Streamlit process before changing editions. `start_public.bat` and `start_ifind.bat` also switch to the corresponding branch before starting the app; Git refuses the switch if it would overwrite local edits.

The public-data branch preserves the original implementation, including its optional iFinD path for Beijing Stock Exchange prices. Public sources remain subject to network availability and coverage. The iFinD branch does not fall back to public sources when credentials are missing.

Ignored local credentials, caches and the Python environment remain on disk when switching branches. The editions share this directory's local watchlist and browser origin; keep that in mind when changing versions. The old archived public-data directory is no longer required by the launchers.

## Tonghuashun iFinD Configuration

This edition's active market-data paths use only official iFinD HTTP endpoints. News is excluded from navigation. Legacy public-provider helpers remain for their existing offline regression tests, but are not called by the application market-data services.

Local credentials in `.streamlit/secrets.toml` (ignored by Git):

```toml
THS_ACCESS_TOKEN = "your-iFinD-access-token"
# Optional: obtain a valid Access Token automatically instead of replacing it manually.
# THS_REFRESH_TOKEN = "your-iFinD-refresh-token"
```

Token validity, account expiry, and available data permissions depend on your iFinD account. Refresh Token support does not extend an account trial or grant additional data permissions. Never commit credentials.

### Verified trial coverage and limitations

- Live A-share batch quotes, daily OHLCV/turnover, minute bars, security names, valuation, disclosed cumulative financial reports, Chinese trading dates, Shanghai index and all-A-share breadth have been tested with the trial account.
- Financial dates after the actual disclosure date are excluded. Net profit is attributable-to-parent profit. Revenue uses the operating-revenue indicator; gross margin, debt ratio and operating cash flow per share are computed from iFinD fields. Dynamic PE is an explicitly labeled annualization of the latest reported cumulative profit.
- Deducted net profit and capital spending indicator definitions remain unverified; these cells stay unavailable. The app does not scrape F10 to fill them.
- US historical prices were retrieved, but US real-time prices returned an explicit permission error. Some overseas index codes returned no daily data. Korean equity codes, overseas financial statements, overseas breadth and KRW/USD indicators are not yet verified; the UI reports that limitation rather than changing providers. Official symbol overrides can be supplied in `[IFIND_CODES]` in the secrets file.
- Only iFinD-origin data are stored under `data/cache/ifind/`. Daily bars reuse cached history and fetch overlapping recent dates on refresh. Missing traded amounts stay missing. Requests are batched (100 securities) and paced; full-market breadth refreshes at most every five minutes. Older cached snapshots are labeled stale.
- Automatic refresh is off by default. Enable it separately for watchlist/rankings (60 seconds) or minute charts (5 minutes); polling fetches only during trading sessions, and ordinary control changes reuse the current session snapshot. Manual refresh remains available. Minute requests still retrieve the full trading day, at the reduced cadence. The all-A-share security list is saved to disk by date and reused after restarts and by local instances; concurrent first loads can still duplicate a request. Opening pages or clicking refresh may consume quota even with automatic refresh off.
- These are polling HTTP interfaces, not exchange push feeds. No claim of tick-by-tick or zero-delay updates is made.

## Key Features

| Feature | Description |
| --- | --- |
| **Multi-market Support** | US stocks, Korean stocks, and China A-share equities |
| **Interactive Charts** | Candlestick, MA, BBI, BOLL, RSI, MACD, and intraday charts |
| **Volume/Amount Toggle** | Switch chart subplots between traded volume and traded amount |
| **Valuation View** | PE TTM, static PE, dynamic PE, and market cap for A shares |
| **Financial Reports** | Latest four disclosed A-share fiscal years and four reported quarters through iFinD |
| **Korean Currency Toggle** | Switch Korean-stock prices, amounts, market cap, and financial reports between KRW and USD |
| **New-listing Support** | Safely renders first-day or short-history listings without invalid indicators or widgets |
| **A-share Rankings** | Full curated-universe rankings with live intraday refresh |
| **Market Overview** | China and US benchmark indices, A-share turnover comparison, and market breadth |
| **Financial News** | Preserved only in the original public-data edition |
| **Indicator Guide** | Built-in explanations for formulas and interpretation |
| **Data Export** | Download raw data as CSV |

## Technical Methods Used

### Data Acquisition

| Data | Active source |
| --- | --- |
| Daily OHLCV and traded amount | iFinD `cmd_history_quotation` |
| Current quotes and batch rankings | iFinD `real_time_quotation` |
| Minute bars | iFinD `high_frequency` |
| Names, static PE | iFinD `basic_data_service` |
| Financial reports | iFinD `date_sequence` |
| All-A-share security list | iFinD `data_pool` |
| Trading dates | iFinD `get_trade_dates` |

### Data Quality Notes

- iFinD daily prices use unadjusted prices, consistently with intraday bars; original currencies are retained.
- The completed official daily bar is retained outside regular trading hours. Intraday-derived bars during trading are provisional.
- Missing fields and permissions are explicit; no public data or demo data are substituted.

### Technical Indicators

| Indicator | Purpose |
| --- | --- |
| **MA** | Smooth price movement and identify trend direction |
| **RSI** | Measure overbought or oversold momentum zones |
| **MACD** | Compare short-term and long-term trend momentum |
| **BBI** | Combine multiple moving averages into one trend line |
| **BOLL** | Show price position relative to a volatility band |

### Visualization

- **Library**: Plotly
- **Type**: Interactive web-based charts
- **Features**: Hover tooltips, zoom, pan, range selection, synchronized axes

## Intended Use

- Personal stock research and market monitoring
- Quick technical analysis for individual investors
- Informational analysis only, not professional financial advice

## Limitations & Future Improvements

### Current Limitations

1. Market data can be delayed, incomplete, or temporarily unavailable.
2. Trial data coverage, overseas permissions and unverified indicator definitions limit available fields.
3. Investment insights are rule-based and should not be treated as predictions.
4. Financial metrics should be compared with companies in the same industry and similar growth stage.

### Possible Improvements

- [x] Personal A-share watchlist: add the current stock from **个股分析**, then select favorites under **我的自选** with the same complete analysis page
- [ ] News and announcement integration
- [ ] Saved user preferences
- [ ] More international markets
- [ ] More robust valuation and factor-analysis views

## Credentials

The iFinD edition requires an authorized iFinD account and a local Access Token or Refresh Token. It does not read optional Polygon/FMP credentials or switch to other market-data providers. Use the backed-up public-data edition if iFinD access expires.
