# Stock Insight

**Interactive Financial Data Analysis Dashboard**

A Streamlit and Plotly app for personal stock research across US stocks and China A-share equities. It combines historical price analysis, intraday monitoring, technical indicators, valuation snapshots, financial reports, and rule-based investment observations in one local dashboard.

## Product Overview

Stock Insight currently supports:

- US stock daily OHLCV and market-cap data through Yahoo Finance / `yfinance`
- China A-share daily OHLCV data from Tonghuashun public data sources
- A curated A-share universe focused on AI hardware and advanced manufacturing
- Custom ticker input for both supported markets
- Candlestick charts with MA, optional BBI, optional BOLL, and market-specific red/green colors
- Price-analysis subplot switching between volume and traded amount
- Trading-calendar cleanup that hides weekends and missing exchange sessions
- A-share intraday charts with price, average price, previous close, percentage scale, and volume/traded-amount toggle
- A-share valuation overview with PE TTM, static PE, dynamic PE, and market cap
- Latest annual report plus current fiscal-year quarterly financial reports
- RSI and MACD technical indicator panels
- A dedicated indicator explanation page
- CSV export for loaded historical price data

## Project Structure

```text
stock_insight/
|-- app.py                 # Main Streamlit application
|-- data_fetcher.py        # Yahoo Finance and Tonghuashun data acquisition
|-- analysis.py            # Technical indicator calculations
|-- visualization.py       # Plotly chart builders
|-- indicator_help.py      # Indicator explanation page
|-- a_share_universe.py    # Curated A-share stock universe
|-- requirements.txt       # Python dependencies
|-- .streamlit/            # Streamlit configuration and secrets template
|-- assets/                # Static assets
|-- data/                  # Local data files
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

   ```bash
   streamlit run app.py
   ```

5. **Access the app**

   Open your browser and go to `http://localhost:8501`.

If the Windows `streamlit.exe` launcher points to an old virtual environment, use this equivalent command:

```bash
python -m streamlit run app.py
```

## Deployment

The app can be deployed on Streamlit Community Cloud.

1. Push the repository to GitHub.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create a new app from this repository.
4. Set the entry point to `app.py`.
5. Add `THS_ACCESS_TOKEN` in Streamlit secrets if your deployment needs it.

Streamlit will provide a public `*.streamlit.app` URL after deployment.

## Tonghuashun iFinD Configuration

Most A-share daily, valuation, intraday, and financial-report features use public Tonghuashun pages. `THS_ACCESS_TOKEN` is optional and currently kept for Beijing Stock Exchange prices and future official iFinD API support.

For local development, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and add:

```toml
THS_ACCESS_TOKEN = "your-iFinD-access-token"
```

The real secrets file is ignored by Git.

## Key Features

| Feature | Description |
| --- | --- |
| **Multi-market Support** | US stocks and China A-share equities |
| **Interactive Charts** | Candlestick, MA, BBI, BOLL, RSI, MACD, and intraday charts |
| **Volume/Amount Toggle** | Switch chart subplots between traded volume and traded amount |
| **Valuation View** | PE TTM, static PE, dynamic PE, and market cap for A shares |
| **Financial Reports** | Latest annual report and current fiscal-year quarterly reports |
| **Indicator Guide** | Built-in explanations for formulas and interpretation |
| **Data Export** | Download raw data as CSV |

## Technical Methods Used

### Data Acquisition

| Market | Data | Source |
| --- | --- | --- |
| US stocks | Daily OHLCV and market cap | Yahoo Finance / `yfinance` |
| China A shares | Daily OHLCV, valuation, intraday, financial reports | Tonghuashun public pages |
| Beijing Stock Exchange | Daily prices when configured | Tonghuashun iFinD token path |

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
2. Tonghuashun public page structures may change and require parser updates.
3. Investment insights are rule-based and should not be treated as predictions.
4. Financial metrics should be compared with companies in the same industry and similar growth stage.

### Possible Improvements

- [ ] Portfolio tracking and watchlists
- [ ] News and announcement integration
- [ ] Saved user preferences
- [ ] More international markets
- [ ] More robust valuation and factor-analysis views
