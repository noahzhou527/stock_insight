# 📊 Stock Insight

**Interactive Financial Data Analysis Dashboard**

A Streamlit-based personal tool for stock market analysis and visualization.

## 🎯 Product Overview

Stock Insight is a personal web application for everyday investment research.
It allows users to:

- Fetch real-time stock data from Yahoo Finance
- Browse a curated China A-share AI hardware and advanced manufacturing universe
- Fetch A-share daily OHLCV data from Tonghuashun
- Hide weekends and exchange holidays from financial charts
- View aligned candlestick and volume charts with market-specific colors
- Track Tonghuashun intraday prices with 30-second refresh
- Compare public PE (TTM), static PE, and dynamic PE
- Show the latest annual report and current fiscal-year quarterly reports
- Visualize price movements with interactive candlestick charts
- Calculate and display technical indicators (MA, RSI, MACD)
- Generate AI-driven investment insights
- Export data for further analysis

## 📁 Project Structure

```
stock_insight/
├── app.py                 # Main Streamlit application
├── data_fetcher.py        # Data acquisition module
├── analysis.py            # Technical analysis calculations
├── visualization.py       # Plotly visualization functions
├── requirements.txt       # Python dependencies
├── .streamlit/            # Cloud deployment configuration
└── README.md              # This file
```


## 🛠️ Installation & Local Run

1. **Clone the repository**
   ```bash
   git clone https://github.com/noahzhou527/stock_insight.git
   cd stock_insight
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**
   ```bash
   streamlit run app.py
   ```

4. **Access the app**
   Open your browser and go to `http://localhost:8501`

## Deploy to a Public URL

The repository is ready for deployment on Streamlit Community Cloud:

1. Push the project to GitHub.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create an app and select this repository.
4. Set the entry point to `app.py`, then deploy.

Streamlit will provide a public `*.streamlit.app` address that can be opened
directly from any browser. A custom domain can be connected later through a
hosting platform or reverse proxy if needed.

### Tonghuashun iFinD configuration

A-share daily prices, public valuation metrics, intraday prices, and financial
reports use Tonghuashun data. An iFinD access token is optional and remains
available for Beijing Stock Exchange prices and future official API features.
Add it to `.streamlit/secrets.toml` locally or to the Streamlit Cloud app
secrets:

```toml
THS_ACCESS_TOKEN = "your-iFinD-access-token"
```

Use `.streamlit/secrets.toml.example` as the local template. The real secrets
file is excluded from Git.

## 💡 Key Features

| Feature | Description |
|---------|-------------|
| **Multi-stock Support** | Pre-configured popular stocks + custom ticker input |
| **Interactive Charts** | Candlestick, volume, RSI, MACD with zoom/pan |
| **Technical Analysis** | Moving averages, RSI, MACD calculations |
| **AI Insights** | Rule-based investment signal generation |
| **Data Export** | Download raw data as CSV |

## 🧮 Technical Methods Used

### Data Acquisition
- **Library**: `yfinance`
- **Source**: Yahoo Finance API
- **Data**: OHLCV (Open, High, Low, Close, Volume)

### Technical Indicators
| Indicator | Formula | Interpretation |
|-----------|---------|--------------|
| **SMA** | (P1 + ... + Pn) / n | Trend direction |
| **RSI** | 100 - (100/(1+RS)) | Overbought (>70) / Oversold (<30) |
| **MACD** | EMA(12) - EMA(26) | Momentum and trend changes |

### Visualization
- **Library**: Plotly
- **Type**: Interactive web-based charts
- **Features**: Hover tooltips, zoom, pan, range selection

## 🎯 Intended Use

- Personal stock research and market monitoring
- Quick technical analysis for individual investors
- Informational analysis only, not professional financial advice

## ⚠️ Limitations & Future Improvements

### Current Limitations
1. **Data Source**: Limited to Yahoo Finance availability
2. **Real-time**: 15-minute delay for most markets
3. **AI Insights**: Rule-based only, no machine learning
4. **Coverage**: US stocks only (can be extended)

### Possible Improvements
- [ ] Add machine learning price prediction
- [ ] Support multiple international markets
- [ ] Implement portfolio tracking
- [ ] Add news sentiment analysis
- [ ] User authentication and saved preferences

