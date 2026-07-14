from __future__ import annotations

import os

import streamlit as st


VALUATION_CACHE_VERSION = 4
US_TICKER_OPTIONS = {
    "Apple (AAPL)": "AAPL",
    "Microsoft (MSFT)": "MSFT",
    "Tesla (TSLA)": "TSLA",
    "Amazon (AMZN)": "AMZN",
    "Google (GOOGL)": "GOOGL",
    "Meta (META)": "META",
    "NVIDIA (NVDA)": "NVDA",
    "SpaceX (SPCX)": "SPCX",
    "Broadcom (AVGO)": "AVGO",
    "SanDisk (SNDK)": "SNDK",
    "Micron (MU)": "MU",
    "Berkshire Hathaway (BRK-B)": "BRK-B",
    "JPMorgan (JPM)": "JPM",
    "Visa (V)": "V",
    "Custom Input": "CUSTOM",
}

KR_TICKER_OPTIONS = {
    "三星电子 (005930.KS)": "005930.KS",
    "SK 海力士 (000660.KS)": "000660.KS",
    "SK Square (402340.KS)": "402340.KS",
    "现代汽车 (005380.KS)": "005380.KS",
    "三星电机 (009150.KS)": "009150.KS",
}

CN_INDEX_CONFIG = (
    {"name": "上证指数", "symbol": "1A0001", "display_code": "000001"},
    {"name": "深证成指", "symbol": "399001", "display_code": "399001"},
    {"name": "创业板指", "symbol": "399006", "display_code": "399006"},
    {"name": "科创综指", "symbol": "1B0680", "display_code": "000680"},
    {"name": "北证50", "symbol": "899050", "display_code": "899050", "eastmoney_secid": "0.899050"},
)

US_INDEX_CONFIG = (
    {"name": "道琼斯", "symbol": "^DJI"},
    {"name": "纳斯达克综合", "symbol": "^IXIC"},
    {"name": "纳斯达克100", "symbol": "^NDX"},
    {"name": "标普500", "symbol": "^GSPC"},
)

KR_INDEX_CONFIG = (
    {"name": "韩国综合指数", "symbol": "^KS11", "display_code": "KOSPI"},
)


def configure_page() -> None:
    """Configure Streamlit before any UI element is rendered."""
    st.set_page_config(
        page_title="Stock Insight",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def get_ths_access_token() -> str | None:
    """Read the optional iFinD token without exposing it to page code."""
    token = os.getenv("THS_ACCESS_TOKEN")
    if token:
        return token
    try:
        return st.secrets.get("THS_ACCESS_TOKEN")
    except Exception:
        return None
