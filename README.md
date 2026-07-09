# 📊 StockInsight Pro

**Interactive Financial Data Analysis Dashboard**

A Streamlit-based interactive tool for stock market analysis and visualization, 
developed for ACC102 Mini Assignment (Track 4).

## 🎯 Product Overview

StockInsight Pro is a user-friendly web application that allows investors and 
students to:

- Fetch real-time stock data from Yahoo Finance
- Visualize price movements with interactive candlestick charts
- Calculate and display technical indicators (MA, RSI, MACD)
- Generate AI-driven investment insights
- Export data for further analysis

## 🚀 Live Demo

**Deployed App**: [Your Streamlit Cloud Link - 部署后填写]

**Demo Video**: [Your 1-3 minute video link - 制作后填写]

## 📁 Project Structure

```
stock_insight/
├── app.py                 # Main Streamlit application
├── data_fetcher.py        # Data acquisition module
├── analysis.py            # Technical analysis calculations
├── visualization.py       # Plotly visualization functions
├── requirements.txt       # Python dependencies
└── README.md             # This file
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

## 🎯 Target Audience

- **Primary**: Finance students learning technical analysis
- **Secondary**: Small investors needing quick stock insights
- **Use Case**: Educational analysis, not professional trading

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

## 📚 References

- Yahoo Finance. (2024). *Yahoo Finance API Documentation*.
- Murphy, J. J. (1999). *Technical Analysis of the Financial Markets*. Penguin.
- Streamlit Documentation: https://docs.streamlit.io/

## 👤 Author

- **Name**: [Your Name]
- **Student ID**: [Your ID]
- **Course**: ACC102 Mini Assignment
- **Date**: April 2026
