import streamlit as st
import pandas as pd
import numpy as np
import importlib
import visualization
import pages.market_overviews as market_overviews

# 导入自定义模块
from data_fetcher import DataFetchError
import a_share_universe
from analysis import (
    calculate_bbi,
    calculate_bollinger_bands,
    calculate_ma,
    calculate_macd,
    calculate_rsi,
)
from indicator_help import render_indicator_help
from formatters import (
    format_amount,
    format_financial_report_table,
    format_statistics,
    format_volume,
)
from new_listing import (
    get_new_listing_state,
    is_new_listing_history,
    pad_new_listing_chart,
)
from visualization import plot_candlestick, plot_financial_report_bars, plot_intraday, plot_rsi, plot_macd
from config.app_config import VALUATION_CACHE_VERSION, configure_page, get_ths_access_token
from components.sidebar import render_sidebar
from services.market_data import (
    indicator_warmup_start,
    is_market_trading_session,
    load_data,
    load_financial_reports,
    load_intraday,
    load_krw_usd_rate,
    load_us_market_cap,
    load_valuation,
    trim_to_display_range,
)

# Streamlit reruns the app in the same process, so refresh the separately
# maintained stock universe before building sidebar options.
importlib.reload(a_share_universe)
importlib.reload(visualization)
importlib.reload(market_overviews)
A_SHARE_UNIVERSE = a_share_universe.A_SHARE_UNIVERSE


# ============ 页面配置 ============
configure_page()

# ============ 自定义样式 ============
st.markdown("""
<style>
    :root {
        --brand: #22d3ee;
        --brand-strong: #67e8f9;
        --accent: #8b5cf6;
        --positive: #2dd4bf;
        --negative: #fb7185;
        --ink: #e6edf7;
        --muted: #8b9bb1;
        --line: #1c293b;
        --line-strong: #26384f;
        --surface: #0d1422;
        --surface-raised: #111b2c;
        --canvas: #070b14;
    }
    html, body, [class*="css"] {
        font-family: Inter, "SF Pro Display", "Microsoft YaHei", system-ui, sans-serif;
    }
    .stApp {
        background:
            radial-gradient(circle at 50% -8%, rgba(34, 211, 238, 0.10), transparent 34rem),
            radial-gradient(circle at 100% 16%, rgba(139, 92, 246, 0.07), transparent 28rem),
            var(--canvas);
        color: var(--ink);
    }
    [data-testid="stHeader"] {
        background: rgba(7, 11, 20, 0.72);
        backdrop-filter: blur(14px);
        border-bottom: 1px solid rgba(28, 41, 59, 0.55);
    }
    [data-testid="stMainBlockContainer"] {
        max-width: 1440px;
        /* Leave clear space below Streamlit's fixed Deploy toolbar. */
        padding-top: 3.1rem;
        padding-bottom: 4rem;
    }
    [data-testid="stSidebar"] {
        background: rgba(9, 15, 26, 0.97);
        border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 1.5rem;
    }
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: var(--ink);
        letter-spacing: -0.02em;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label {
        color: #a9b7ca;
    }
    .main-header {
        font-size: clamp(2rem, 3.6vw, 2.7rem);
        font-weight: 750;
        line-height: 1.15;
        padding-bottom: 0.06em;
        letter-spacing: -0.04em;
        background: linear-gradient(110deg, #f3f8ff 15%, #67e8f9 58%, #a78bfa 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin: 0 0 0.8rem;
        filter: drop-shadow(0 0 24px rgba(34, 211, 238, 0.12));
    }
    /* MathJax fractions extend above their baseline; prevent clipping in expanders. */
    [data-testid="stExpanderDetails"] [data-testid="stLatex"] {
        margin: 0.4rem 0 0.9rem;
        padding: 0.35rem 0;
        overflow: visible;
    }
    [data-testid="stExpanderDetails"] [data-testid="stLatex"] mjx-container {
        overflow: visible !important;
    }
    .rsi-formula {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.42rem;
        min-height: 5.4rem;
        padding: 0.7rem 0 0.45rem;
        color: #dce7f5;
        font-family: "Times New Roman", "Microsoft YaHei", serif;
        font-size: clamp(1.35rem, 2.1vw, 1.75rem);
        line-height: 1.2;
    }
    .rsi-formula em {
        font-style: italic;
    }
    .rsi-fraction {
        display: inline-grid;
        grid-template-rows: auto auto;
        min-width: 3.1rem;
        text-align: center;
        line-height: 1.15;
    }
    .rsi-fraction span:first-child {
        padding: 0.15rem 0.35rem 0.22rem;
        border-bottom: 1px solid currentColor;
    }
    .rsi-fraction span:last-child {
        padding: 0.22rem 0.35rem 0.12rem;
    }
    .nav-label {
        display: flex;
        align-items: center;
        gap: 0.48rem;
        color: #a9b7ca;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        margin: 0 0 0.48rem 0.08rem;
    }
    .nav-label::before {
        content: "";
        width: 0.42rem;
        height: 0.42rem;
        border-radius: 999px;
        background: var(--brand);
        box-shadow: 0 0 0 0.22rem rgba(34, 211, 238, 0.10);
    }
    .st-key-top_navigation {
        position: relative;
        max-width: 1280px;
        margin: 0 auto 1.25rem;
        padding: 0.9rem 1rem 1rem;
        overflow: hidden;
        border: 1px solid rgba(50, 69, 94, 0.82);
        border-radius: 1.15rem;
        background:
            radial-gradient(circle at 20% 0%, rgba(34, 211, 238, 0.08), transparent 28rem),
            linear-gradient(145deg, rgba(15, 24, 40, 0.96), rgba(9, 15, 27, 0.98));
        box-shadow: 0 22px 54px rgba(0, 0, 0, 0.24);
    }
    .st-key-top_navigation::before {
        content: "";
        position: absolute;
        inset: 0 18% auto;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.8), transparent);
    }
    .top-nav-heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 0.2rem 0.68rem;
        color: #dce7f5;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.04em;
    }
    .top-nav-heading span:last-child {
        color: #71839b;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }
    .st-key-top_navigation [data-testid="stColumn"] {
        padding: 0.72rem 0.8rem 0.78rem;
        border: 1px solid rgba(38, 56, 79, 0.82);
        border-radius: 0.88rem;
        background: rgba(8, 14, 25, 0.58);
    }
    .st-key-top_navigation .st-key-page_navigation [data-baseweb="button-group"] {
        padding: 0.3rem !important;
        border-color: rgba(45, 65, 90, 0.92) !important;
        border-radius: 0.9rem !important;
        background: rgba(5, 10, 19, 0.76) !important;
    }
    .st-key-top_navigation .st-key-page_navigation button {
        min-height: 3rem !important;
        background: transparent !important;
        color: #8fa0b7 !important;
    }
    .st-key-top_navigation .st-key-page_navigation button:hover,
    .st-key-top_navigation .st-key-market_navigation button:hover,
    .st-key-top_navigation .st-key-market_view_navigation button:hover {
        color: #d7e3f2 !important;
        background: rgba(23, 35, 55, 0.72) !important;
    }
    .st-key-top_navigation .st-key-page_navigation button[aria-pressed="true"],
    .st-key-top_navigation .st-key-page_navigation button[aria-checked="true"],
    .st-key-top_navigation .st-key-page_navigation button[data-active="true"],
    .st-key-top_navigation .st-key-page_navigation button[data-selected="true"] {
        color: #e8fbff !important;
        background: linear-gradient(110deg, rgba(8, 145, 178, 0.34), rgba(37, 99, 235, 0.28)) !important;
        box-shadow:
            inset 0 0 0 1px rgba(103, 232, 249, 0.52),
            0 8px 22px rgba(3, 105, 161, 0.16) !important;
    }
    .st-key-top_navigation .st-key-market_navigation [data-baseweb="button-group"],
    .st-key-top_navigation .st-key-market_view_navigation [data-baseweb="button-group"] {
        padding: 0.18rem !important;
        border: 0 !important;
        background: rgba(15, 26, 43, 0.78) !important;
    }
    .st-key-top_navigation .st-key-market_navigation button,
    .st-key-top_navigation .st-key-market_view_navigation button {
        min-height: 2.4rem !important;
        background: transparent !important;
    }
    .st-key-top_navigation .st-key-market_navigation button[aria-pressed="true"],
    .st-key-top_navigation .st-key-market_navigation button[aria-checked="true"],
    .st-key-top_navigation .st-key-market_navigation button[data-active="true"],
    .st-key-top_navigation .st-key-market_navigation button[data-selected="true"],
    .st-key-top_navigation .st-key-market_view_navigation button[aria-pressed="true"],
    .st-key-top_navigation .st-key-market_view_navigation button[aria-checked="true"],
    .st-key-top_navigation .st-key-market_view_navigation button[data-active="true"],
    .st-key-top_navigation .st-key-market_view_navigation button[data-selected="true"] {
        color: var(--brand-strong) !important;
        background: #17263b !important;
        box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.24) !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, rgba(17, 27, 44, 0.94), rgba(11, 18, 31, 0.96));
        border-color: var(--line) !important;
        border-radius: 1rem !important;
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.22);
    }
    [data-testid="stVerticalBlockBorderWrapper"]:has(div[data-testid="stSegmentedControl"]) {
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
    }
    div[data-testid="stSegmentedControl"] [data-baseweb="button-group"] {
        width: 100%;
        padding: 0.24rem;
        border-radius: 0.78rem;
        background: #080e19;
        border: 1px solid var(--line);
    }
    div[data-testid="stSegmentedControl"] button {
        flex: 1;
        min-height: 2.55rem;
        border: 0 !important;
        border-radius: 0.62rem !important;
        background: #0f1a2b !important;
        font-weight: 650;
        color: #8fa0b7;
    }
    div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
    div[data-testid="stSegmentedControl"] button[aria-checked="true"],
    div[data-testid="stSegmentedControl"] button[data-active="true"],
    button[kind="segmented_control"][aria-pressed="true"],
    button[kind="segmented_control"][aria-checked="true"],
    button[kind="segmented_control"][data-active="true"] {
        background: #172337 !important;
        color: var(--brand-strong) !important;
        box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.28), 0 6px 18px rgba(0, 0, 0, 0.22);
    }
    div[data-testid="stSegmentedControl"] button * {
        color: inherit !important;
    }
    button[data-variant="segmented_control"] {
        background: #0f1a2b !important;
        color: #8fa0b7 !important;
    }
    button[data-variant="segmented_control"][aria-checked="true"],
    button[data-variant="segmented_control"][data-selected="true"] {
        background: #172337 !important;
        color: var(--brand-strong) !important;
        box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.28), 0 6px 18px rgba(0, 0, 0, 0.22);
    }
    button[data-variant="segmented_control"] * {
        color: inherit !important;
    }
    [data-testid="stMetric"] {
        position: relative;
        min-height: 7rem;
        padding: 1rem 1.15rem;
        overflow: hidden;
        border: 1px solid rgba(35, 51, 72, 0.94);
        border-radius: 1rem;
        background:
            radial-gradient(circle at 100% 0%, rgba(34, 211, 238, 0.055), transparent 11rem),
            linear-gradient(145deg, rgba(17, 27, 44, 0.98), rgba(11, 19, 32, 0.98));
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
        transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
    }
    [data-testid="stMetric"]::after,
    .compact-amount-card::after {
        content: "";
        position: absolute;
        inset: -1.35rem auto auto -0.45rem;
        width: 6rem;
        height: 3.2rem;
        border-radius: 50%;
        background: radial-gradient(
            ellipse at center,
            rgba(34, 211, 238, 0.24) 0%,
            rgba(34, 211, 238, 0.08) 44%,
            transparent 74%
        );
        filter: blur(7px);
        opacity: 0.58;
        pointer-events: none;
    }
    [data-testid="stMetric"]:hover {
        border-color: rgba(62, 88, 120, 0.96);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24);
        transform: translateY(-2px);
    }
    [data-testid="stMetricLabel"] {
        color: var(--muted);
        font-weight: 650;
        font-size: 0.82rem;
        letter-spacing: 0.015em;
    }
    [data-testid="stMetricValue"] {
        color: var(--ink);
        letter-spacing: -0.035em;
        line-height: 1.12;
    }
    [data-testid="stMetricValue"] p {
        font-size: clamp(1.75rem, 2.35vw, 2.55rem);
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"]) {
        border-color: rgba(34, 211, 238, 0.22);
        background:
            radial-gradient(circle at 100% 0%, rgba(34, 211, 238, 0.12), transparent 15rem),
            linear-gradient(145deg, rgba(17, 31, 49, 0.99), rgba(11, 19, 32, 0.99));
    }
    [data-testid="stMetricDelta"] {
        width: fit-content;
        padding: 0.2rem 0.48rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.055);
    }
    .compact-amount-card {
        position: relative;
        box-sizing: border-box;
        min-height: 7rem;
        padding: 1rem 1.15rem;
        overflow: hidden;
        border: 1px solid rgba(35, 51, 72, 0.94);
        border-radius: 1rem;
        background:
            radial-gradient(circle at 100% 0%, rgba(139, 92, 246, 0.08), transparent 11rem),
            linear-gradient(145deg, rgba(17, 27, 44, 0.98), rgba(11, 19, 32, 0.98));
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
        transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
    }
    .compact-amount-card:hover {
        border-color: rgba(62, 88, 120, 0.96);
        box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24);
        transform: translateY(-2px);
    }
    .compact-amount-label {
        color: var(--muted);
        font-size: 0.86rem;
        font-weight: 600;
    }
    .compact-amount-value {
        color: var(--ink);
        font-size: clamp(1.25rem, 1.65vw, 2rem);
        letter-spacing: -0.035em;
        line-height: 1.3;
        white-space: nowrap;
    }
    .compact-amount-date {
        color: var(--muted);
        font-size: clamp(0.65rem, 0.9vw, 1rem) !important;
        font-weight: 500;
        letter-spacing: 0;
        margin-left: 0.32rem;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"]) > div {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        column-gap: 0.75rem;
        row-gap: 0.2rem;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"])
        [data-testid="stMetricLabel"] {
        flex: 0 0 100%;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"])
        [data-testid="stMetricValue"] {
        flex: 0 0 auto;
    }
    [data-testid="stMetric"]:has([data-testid="stMetricDelta"])
        [data-testid="stMetricDelta"] {
        margin: 0;
        white-space: nowrap;
    }
    .cn-price-direction {
        display: none;
    }
    .metric-section-heading {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        margin: 0.15rem 0 0.72rem;
    }
    .metric-section-heading strong {
        color: #dfe9f6;
        font-size: 0.98rem;
        letter-spacing: -0.01em;
    }
    .metric-section-heading span {
        color: #71839b;
        font-size: 0.76rem;
    }
    .secondary-metric-marker {
        display: none;
    }
    [data-testid="stColumn"]:has(.secondary-metric-marker) [data-testid="stMetricValue"] p {
        font-size: clamp(1.35rem, 1.8vw, 2rem);
    }
    [data-testid="stColumn"]:has(.cn-price-up) [data-testid="stMetricValue"],
    [data-testid="stColumn"]:has(.cn-price-up) [data-testid="stMetricValue"] p {
        color: #e53935 !important;
    }
    [data-testid="stColumn"]:has(.cn-price-down) [data-testid="stMetricValue"],
    [data-testid="stColumn"]:has(.cn-price-down) [data-testid="stMetricValue"] p {
        color: #1e9d55 !important;
    }
    .stTabs [role="tablist"] {
        align-items: center;
        gap: 1.2rem;
        padding: 0 0.16rem;
        background: transparent;
        border-bottom: 1px solid var(--line);
    }
    .stTabs [role="tablist"]::after {
        content: "分析模块 · 6 个视图";
        position: static;
        z-index: auto;
        flex: 0 0 auto;
        margin-left: auto;
        padding-right: 0.32rem;
        color: #667990;
        font-size: 0.7rem;
        font-weight: 650;
        letter-spacing: 0.06em;
        white-space: nowrap;
    }
    .stTabs [role="tab"] {
        position: relative;
        padding: 0.76rem 0.92rem 0.82rem;
        border-radius: 0.72rem 0.72rem 0 0;
        font-weight: 650;
        color: #9cabbe;
        transition: color 160ms ease, background 160ms ease, transform 160ms ease;
    }
    .stTabs [role="tab"]:hover {
        color: #dbe7f5;
        background: rgba(34, 211, 238, 0.06);
        transform: translateY(-1px);
    }
    .stTabs [aria-selected="true"] {
        color: #c8f8ff !important;
        background: linear-gradient(180deg, rgba(34, 211, 238, 0.18), rgba(34, 211, 238, 0.045)) !important;
        box-shadow: 0 8px 22px rgba(3, 105, 161, 0.1);
        text-shadow: 0 0 16px rgba(103, 232, 249, 0.28);
    }
    .stTabs [aria-selected="true"]::after {
        content: "";
        position: absolute;
        inset: auto 9% -1px;
        height: 3px;
        border-radius: 999px;
        background: linear-gradient(90deg, transparent, var(--brand) 28%, var(--brand-strong) 50%, var(--brand) 72%, transparent);
        box-shadow: 0 -3px 14px rgba(34, 211, 238, 0.42);
    }
    .stTabs [role="tab"]:focus-visible {
        outline: 1px solid rgba(103, 232, 249, 0.24);
        outline-offset: -3px;
    }
    .valuation-note-right {
        padding-top: 0.1rem;
        color: #71839b;
        font-size: 0.76rem;
        line-height: 1.45;
        text-align: right;
    }
    .stButton > button {
        border-radius: 0.7rem;
        border-color: var(--line-strong);
        background: #111b2c;
        color: #d9e4f2;
        font-weight: 650;
    }
    .stButton > button:hover {
        border-color: var(--brand);
        color: var(--brand-strong);
        background: #152338;
    }
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-testid="stDateInput"] input,
    [data-testid="stNumberInput"] input {
        background-color: #0b1320 !important;
        border-color: var(--line-strong) !important;
        color: var(--ink) !important;
    }
    [data-baseweb="select"] > div:focus-within,
    [data-baseweb="input"] > div:focus-within,
    [data-testid="stDateInput"] input:focus,
    [data-testid="stNumberInput"] input:focus {
        border-color: rgba(34, 211, 238, 0.72) !important;
        box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.10) !important;
    }
    [data-baseweb="popover"],
    [data-baseweb="menu"],
    [data-baseweb="calendar"] {
        background-color: #111b2c !important;
        color: var(--ink) !important;
    }
    [data-testid="stExpander"] {
        border-color: var(--line) !important;
        background: rgba(13, 20, 34, 0.72);
        border-radius: 0.85rem;
    }
    [data-testid="stPlotlyChart"],
    [data-testid="stDataFrame"] {
        overflow: hidden;
        border: 1px solid var(--line);
        border-radius: 1rem;
        background: var(--surface);
        box-shadow: 0 14px 34px rgba(0, 0, 0, 0.18);
    }
    [data-testid="stDataFrame"] iframe {
        color-scheme: dark;
    }
    hr {
        border-color: var(--line) !important;
    }
    .indicator-summary-grid,
    .rsi-zone-grid {
        display: grid;
        gap: 0.8rem;
        margin: 0.85rem 0;
    }
    .indicator-summary-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .rsi-zone-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .indicator-summary-card,
    .rsi-zone-card {
        padding: 0.9rem 1rem;
        border: 1px solid var(--line);
        border-radius: 0.8rem;
        background: #0b1320;
    }
    .indicator-summary-card strong,
    .rsi-zone-card strong {
        display: block;
        color: var(--ink);
        font-size: 0.88rem;
        margin-bottom: 0.3rem;
    }
    .indicator-summary-card span,
    .rsi-zone-card span {
        color: var(--muted);
        font-size: 0.82rem;
        line-height: 1.55;
    }
    .rsi-zone-card {
        border-top-width: 3px;
    }
    .rsi-zone-card.oversold {
        border-top-color: var(--positive);
        background: rgba(45, 212, 191, 0.07);
    }
    .rsi-zone-card.neutral {
        border-top-color: #64748b;
    }
    .rsi-zone-card.overbought {
        border-top-color: var(--negative);
        background: rgba(251, 113, 133, 0.07);
    }
    .indicator-note {
        margin-top: 0.75rem;
        padding: 0.75rem 0.9rem;
        border-left: 3px solid var(--brand);
        border-radius: 0 0.55rem 0.55rem 0;
        background: rgba(34, 211, 238, 0.055);
        color: #9babc0;
        font-size: 0.86rem;
        line-height: 1.6;
    }
    .pe-formula-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 1rem;
        margin: 0.75rem 0 1.25rem;
    }
    .pe-formula-card {
        min-height: 9rem;
        padding: 1.1rem 0.8rem;
        border: 1px solid var(--line);
        border-radius: 0.8rem;
        background: #0b1320;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 0.8rem;
    }
    .pe-formula-title {
        color: #93a4ba;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .pe-formula {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.55rem;
        color: #dce7f5;
        font-family: "Times New Roman", "Microsoft YaHei", serif;
        font-size: 1.15rem;
        line-height: 1.45;
        white-space: nowrap;
    }
    .pe-formula sub {
        font-size: 0.68em;
    }
    .pe-fraction {
        display: inline-grid;
        grid-template-rows: auto auto;
        text-align: center;
        font-family: "Microsoft YaHei", sans-serif;
        font-size: 0.95rem;
        line-height: 1.55;
    }
    .pe-fraction span:first-child {
        padding: 0 0.5rem 0.2rem;
        border-bottom: 1px solid currentColor;
    }
    .pe-fraction span:last-child {
        padding: 0.2rem 0.5rem 0;
    }
    [data-testid="stAlert"] {
        border: 1px solid var(--line-strong);
        color: #cbd7e6;
        border-radius: 0.8rem;
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.12);
    }
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
        margin: 0;
        font-size: 0.9rem;
    }
    [data-testid="stDownloadButton"] button {
        background: linear-gradient(110deg, #0891b2, #2563eb);
        border: 0;
        color: white;
    }
    a { color: var(--brand-strong); }
    .nav-context {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        margin-top: 0.72rem;
        padding: 0.72rem 0 0.62rem;
        border-top: 1px solid rgba(38, 56, 79, 0.72);
    }
    .nav-context::before {
        content: "分析范围";
        color: #71839b;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.08em;
    }
    .nav-context::after {
        content: "";
        flex: 1;
        height: 1px;
        background: linear-gradient(90deg, rgba(38, 56, 79, 0.55), transparent);
    }
    @media (max-width: 1200px) {
        .stTabs [role="tablist"] {
            gap: 0.55rem;
        }
        .stTabs [role="tablist"]::after {
            display: none;
        }
    }
    @media (max-width: 900px) {
        [data-testid="stMainBlockContainer"] {
            padding-top: 2.5rem;
        }
        .nav-context {
            margin-top: 0.5rem;
            padding-top: 0.5rem;
        }
        .st-key-top_navigation {
            padding: 0.72rem;
            border-radius: 0.95rem;
        }
        .top-nav-heading span:last-child {
            display: none;
        }
        .st-key-top_navigation [data-testid="stColumn"] {
            flex: 1 1 100% !important;
            width: 100% !important;
            padding: 0.62rem 0.68rem;
        }
        .st-key-top_navigation [data-testid="stHorizontalBlock"],
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
            flex-wrap: wrap;
        }
        [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {
            flex: 1 1 12rem !important;
            width: auto !important;
            min-width: min(12rem, 100%) !important;
        }
        [data-testid="stMetric"],
        .compact-amount-card {
            min-height: 6.4rem;
        }
        .valuation-note-right {
            text-align: left;
        }
        .pe-formula-grid {
            grid-template-columns: 1fr;
        }
        .indicator-summary-grid,
        .rsi-zone-grid {
            grid-template-columns: 1fr;
        }
        .pe-formula-card {
            min-height: 7.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)


# ============ 标题区域 ============
st.markdown('<div class="main-header">Stock Insight</div>', unsafe_allow_html=True)

# ============ 顶部导航 ============
market_label = None
a_share_view = None
with st.container(key="top_navigation"):
    st.markdown(
        '<div class="top-nav-heading"><span>市场工作台</span><span>行情 · 指标 · 资讯</span></div>',
        unsafe_allow_html=True,
    )
    page = st.segmented_control(
        "主导航",
        ["行情分析", "指标说明", "新闻热点"],
        default="行情分析",
        key="page_navigation",
        label_visibility="collapsed",
        width="stretch",
    )
    if page == "行情分析":
        st.markdown('<div class="nav-context"></div>', unsafe_allow_html=True)
        market_nav, a_share_nav = st.columns(2, gap="medium")
        with market_nav:
            st.markdown('<div class="nav-label">股票市场</div>', unsafe_allow_html=True)
            market_label = st.segmented_control(
                "股票市场",
                ["美股", "A股", "韩股"],
                default="A股",
                key="market_navigation",
                label_visibility="collapsed",
                width="stretch",
            )
        with a_share_nav:
            view_label = {"A股": "A股视图", "美股": "美股视图", "韩股": "韩股视图"}[market_label]
            view_options = ["个股分析", "股票池排行"] if market_label == "A股" else ["个股分析"]
            if (
                "market_view_navigation" not in st.session_state
                or st.session_state["market_view_navigation"] not in view_options
            ):
                st.session_state["market_view_navigation"] = "个股分析"
            st.markdown(f'<div class="nav-label">{view_label}</div>', unsafe_allow_html=True)
            a_share_view = st.segmented_control(
                view_label,
                view_options,
                key="market_view_navigation",
                label_visibility="collapsed",
                width="stretch",
            )

# 非行情页面在构建侧栏及请求市场数据前完成路由。
if page == "指标说明":
    st.markdown("---")
    render_indicator_help()
    st.stop()
if page == "新闻热点":
    st.markdown("---")
    market_overviews.render_news_page()
    st.stop()
if market_label == "A股" and a_share_view == "股票池排行":
    st.markdown("---")
    market_overviews.render_a_share_rankings(A_SHARE_UNIVERSE)
    st.stop()

# ============ 侧边栏控制面板 ============
market = {"A股": "CN", "美股": "US", "韩股": "KR"}[market_label]
ths_access_token = get_ths_access_token()
controls = render_sidebar(market, A_SHARE_UNIVERSE)
ticker = controls.ticker
start_date = controls.start_date
end_date = controls.end_date
ma_periods = controls.ma_periods
show_bbi = controls.show_bbi
show_boll = controls.show_boll
rsi_period = controls.rsi_period


def refresh_intraday_data(selected_ticker: str) -> None:
    """Clear the intraday snapshot so the next app run fetches a fresh quote."""
    load_intraday.clear()
    for key in list(st.session_state):
        if key.startswith("intraday:") and key.endswith(f":{selected_ticker}"):
            st.session_state.pop(key, None)


def convert_krw_frame_to_usd(frame: pd.DataFrame, rate: float) -> pd.DataFrame:
    """Convert display-only Korean price and amount fields while preserving metadata."""
    result = frame.copy()
    for column in ("Open", "High", "Low", "Close", "Price", "AvgPrice", "Amount"):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce") * rate
    result.attrs.update(frame.attrs)
    for attr in ("pre_close",):
        if result.attrs.get(attr) is not None:
            result.attrs[attr] = float(result.attrs[attr]) * rate
    return result


@st.fragment(run_every="30s")
def render_intraday_panel(selected_ticker, selected_market, display_market=None, currency_rate=1.0):
    session_key = f"intraday:{selected_market}:{selected_ticker}"
    manually_refreshed = st.button(
        "立即刷新",
        key=f"refresh-intraday:{selected_market}:{selected_ticker}",
        width="content",
    )
    if manually_refreshed:
        refresh_intraday_data(selected_ticker)
        st.rerun()

    should_fetch = is_market_trading_session(selected_market) or session_key not in st.session_state
    if should_fetch:
        try:
            st.session_state[session_key] = load_intraday(selected_ticker, selected_market)
        except DataFetchError as error:
            if session_key not in st.session_state:
                st.warning(str(error))
                return

    intraday = st.session_state.get(session_key)
    if intraday is None or intraday.empty:
        st.info("暂时没有可显示的分时数据。")
        return

    display_market = display_market or selected_market
    if selected_market == "KR" and display_market == "US":
        intraday = convert_krw_frame_to_usd(intraday, currency_rate)

    trade_date = intraday.attrs.get("trade_date", "")
    source = intraday.attrs.get("source", "同花顺")
    refresh_note = "交易时段每 30 秒自动刷新" if is_market_trading_session(selected_market) else "非交易时段显示最近数据"
    st.caption(f"交易日：{trade_date} · 数据来源：{source} · {refresh_note}")
    volume_metric_label = st.segmented_control(
        "副图指标",
        ["成交量", "成交额"],
        default="成交量",
        key=f"intraday-volume-metric:{selected_market}:{selected_ticker}",
    )
    st.plotly_chart(
        plot_intraday(
            intraday,
            market=display_market,
            volume_metric="amount" if volume_metric_label == "成交额" else "volume",
        ),
        width="stretch",
        key=f"intraday-chart:{selected_market}:{selected_ticker}",
    )


loading_message = st.empty()

try:
    loading_message.info(f"正在获取 {ticker} 数据...")
    calculation_start_date = indicator_warmup_start(
        start_date,
        ma_periods,
        rsi_period,
        show_bbi,
        show_boll,
    )
    indicator_history_df = load_data(
        ticker,
        calculation_start_date,
        end_date,
        market,
        ths_access_token,
    )
    df = trim_to_display_range(indicator_history_df, start_date, end_date)
    loading_message.empty()

    if df.empty:
        st.error(f"无法获取 {ticker} 的数据，请检查股票代码是否正确。")
        st.stop()

    raw_daily_close = float(pd.to_numeric(df["Close"], errors="coerce").dropna().iloc[-1])
    data_source = indicator_history_df.attrs.get("source", "Yahoo Finance")
    live_name = indicator_history_df.attrs.get("symbol_name")
    if market == "CN" and live_name:
        a_share_live_names = dict(st.session_state.get("a_share_live_names", {}))
        if a_share_live_names.get(ticker) != live_name:
            a_share_live_names[ticker] = live_name
            st.session_state["a_share_live_names"] = a_share_live_names
            st.rerun()
    display_market = market
    krw_usd_rate = 1.0
    if market == "KR":
        currency_choice = st.segmented_control(
            "韩股显示币种",
            ["韩元", "美元"],
            default="韩元",
            key=f"kr-display-currency:{ticker}",
        )
        if currency_choice == "美元":
            try:
                krw_usd_rate = load_krw_usd_rate()
            except DataFetchError as error:
                st.warning(f"美元换算暂不可用，当前仍按韩元显示：{error}")
            else:
                display_market = "US"
                indicator_history_df = convert_krw_frame_to_usd(indicator_history_df, krw_usd_rate)
                df = convert_krw_frame_to_usd(df, krw_usd_rate)
                st.caption(f"已切换为美元显示 · 参考汇率：1 美元 = {1 / krw_usd_rate:,.2f} 韩元")

    new_listing = get_new_listing_state(df, rsi_period)
    st.success(f"成功加载 {ticker} 从 {start_date} 到 {end_date} 的数据")
    if indicator_history_df.attrs.get("includes_intraday_daily_bar"):
        st.caption("日 K 已包含当日分时合成的实时 K 线；收盘后数据源完成结算时会以正式日线为准。")
    if data_source in {"同花顺", "同花顺 iFinD"}:
        st.caption("数据来源：同花顺")
    elif data_source == "同花顺本地缓存":
        st.warning("同花顺当前不可用，正在显示本地缓存数据。")
    elif data_source == "Yahoo Finance":
        st.caption("Data source: Yahoo Finance")
    elif data_source == "local cache":
        st.warning("Yahoo Finance 当前不可用，正在显示本地缓存数据。")
    elif data_source == "demo data":
        st.warning("Yahoo Finance 和备用数据源当前不可用，正在显示演示数据；请勿用于真实投资判断。")
    else:
        st.info(f"Yahoo Finance 当前不可用，已自动切换到 {data_source}。")

except DataFetchError as e:
    loading_message.empty()
    st.error(str(e))
    st.caption(f"Diagnosis: {e.category}")
    with st.expander("Technical details"):
        st.code(e.diagnostics, language="text")
    st.stop()
except Exception as e:
    loading_message.empty()
    st.error(f"数据获取失败: {str(e)}")
    st.info("提示：如果持续失败，可能是API限制，请稍后再试。")
    st.stop()

# ============ 关键指标展示 ============
st.markdown("---")

# 计算关键指标。A 股优先使用最新分时价，接口暂不可用时回退日线收盘价。
latest_price = df['Close'].iloc[-1]
intraday_currency_rate = krw_usd_rate
has_previous_price = new_listing["previous_close"] is not None
prev_price = new_listing["previous_close"] if has_previous_price else latest_price
current_price_label = "当前价格"
if market in {"CN", "US", "KR"}:
    intraday_session_key = f"intraday:{market}:{ticker}"
    intraday_snapshot = st.session_state.get(intraday_session_key)
    if intraday_snapshot is None:
        try:
            intraday_snapshot = load_intraday(ticker, market)
            st.session_state[intraday_session_key] = intraday_snapshot
        except DataFetchError:
            intraday_snapshot = None
    if intraday_snapshot is not None and not intraday_snapshot.empty:
        latest_price = float(intraday_snapshot["Price"].iloc[-1])
        intraday_pre_close = intraday_snapshot.attrs.get("pre_close")
        if intraday_pre_close is not None and np.isfinite(intraday_pre_close) and intraday_pre_close > 0:
            prev_price = float(intraday_pre_close)
            has_previous_price = True
        current_price_label = "当前价格（分时）"
    else:
        current_price_label = "当前价格（最近收盘）"

if market == "KR" and display_market == "US":
    # Some cached Yahoo intraday snapshots are already denominated in USD while
    # the corresponding daily bars remain in KRW.  Detect that representation
    # from the latest daily close and never convert the same quote twice.
    intraday_is_already_usd = (
        intraday_snapshot is not None
        and not intraday_snapshot.empty
        and raw_daily_close > 0
        and np.isclose(latest_price / raw_daily_close, krw_usd_rate, rtol=0.12)
    )
    if intraday_snapshot is None or intraday_snapshot.empty:
        pass  # Daily prices and the new-listing reference were converted above.
    elif intraday_is_already_usd:
        intraday_currency_rate = 1.0
    else:
        latest_price *= krw_usd_rate
        prev_price *= krw_usd_rate

price_change = latest_price - prev_price if has_previous_price else 0.0
price_change_pct = (price_change / prev_price) * 100 if has_previous_price and prev_price else 0.0

high_52w = df['High'].max()
low_52w = df['Low'].min()
volume_avg = df['Volume'].mean()
daily_amount = (
    pd.to_numeric(df["Amount"], errors="coerce")
    if "Amount" in df.columns
    else pd.Series(np.nan, index=df.index)
)
max_daily_amount = daily_amount.max()
max_daily_amount_date = (
    pd.Timestamp(daily_amount.idxmax()).strftime("%Y-%m-%d")
    if daily_amount.notna().any()
    else ""
)
volatility = df['Close'].pct_change().std() * np.sqrt(252) * 100
volatility_label = f"{volatility:.1f}%" if new_listing["volatility_ready"] and np.isfinite(volatility) else "数据不足"
currency_symbol = "¥" if display_market == "CN" else "₩" if display_market == "KR" else "$"
if has_previous_price:
    price_change_sign = "+" if price_change >= 0 else "-"
    price_delta_label = (
        f"{price_change_sign}{currency_symbol}{abs(price_change):.2f} "
        f"({price_change_pct:+.2f}%)"
    )
else:
    price_delta_label = "首日上市，暂无前收盘价"

valuation = {
    "pe_ttm": None,
    "pe_static": None,
    "pe_dynamic": None,
    "market_cap": None,
    "source": None,
}
valuation_error = None
if market == "CN":
    try:
        valuation = load_valuation(ticker, VALUATION_CACHE_VERSION)
    except Exception as error:
        valuation_error = str(error)
    market_cap = valuation.get("market_cap")
else:
    market_cap = load_us_market_cap(ticker)
    if market == "KR" and display_market == "US" and market_cap is not None:
        market_cap *= krw_usd_rate


def format_market_cap(value, selected_market):
    if value is None or not np.isfinite(value):
        return "暂不可用"
    if selected_market == "CN":
        if value >= 1e12:
            return f"¥{value / 1e12:.2f}万亿"
        if value >= 1e8:
            return f"¥{value / 1e8:.2f}亿"
        if value >= 1e4:
            return f"¥{value / 1e4:.2f}万"
        return f"¥{value:,.0f}"
    if selected_market == "KR":
        if value >= 1e12:
            return f"₩{value / 1e12:.2f}万亿"
        if value >= 1e8:
            return f"₩{value / 1e8:.2f}亿"
        return f"₩{value:,.0f}"
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.0f}"


def data_detail_column_config(index_label: str):
    """Keep the two data-detail tables compact and consistently right-aligned."""
    return {
        "_index": st.column_config.TextColumn(index_label, width=120, alignment="right"),
        "开盘价": st.column_config.NumberColumn(width=110, alignment="right"),
        "最高价": st.column_config.NumberColumn(width=110, alignment="right"),
        "最低价": st.column_config.NumberColumn(width=110, alignment="right"),
        "收盘价": st.column_config.NumberColumn(width=110, alignment="right"),
        "成交量": st.column_config.TextColumn(width=155, alignment="right"),
        "成交额": st.column_config.TextColumn(width=155, alignment="right"),
        "RSI（相对强弱指标）": st.column_config.NumberColumn(width=190, alignment="right"),
    }


def render_max_daily_amount_card(value: str, date: str):
    st.markdown(
        f'''<div class="compact-amount-card">
            <div class="compact-amount-label">区间单日最大成交额</div>
            <div class="compact-amount-value">{value}<span class="compact-amount-date">（{date}）</span></div>
        </div>''',
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="metric-section-heading"><strong>市场快照</strong><span>价格 · 成交 · 波动 · 规模</span></div>',
    unsafe_allow_html=True,
)

if market == "CN":
    price_columns = st.columns(3)
    with price_columns[0]:
        direction_class = "cn-price-up" if price_change_pct >= 0 else "cn-price-down"
        st.metric(
            current_price_label,
            f"{currency_symbol}{latest_price:.2f}",
            price_delta_label,
            delta_color="inverse",
        )
        st.markdown(
            f'<span class="cn-price-direction {direction_class}"></span>',
            unsafe_allow_html=True,
        )
    with price_columns[1]:
        st.metric("52周最高", f"{currency_symbol}{high_52w:.2f}")
    with price_columns[2]:
        st.metric("52周最低", f"{currency_symbol}{low_52w:.2f}")

    secondary_columns = st.columns(4)
    with secondary_columns[0]:
        st.metric("平均成交量", format_volume(volume_avg, display_market))
        st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
    with secondary_columns[1]:
        render_max_daily_amount_card(format_amount(max_daily_amount, display_market), max_daily_amount_date)
    with secondary_columns[2]:
        st.metric("年化波动率", volatility_label)
        st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
    with secondary_columns[3]:
        st.metric("总市值", format_market_cap(market_cap, display_market))
        st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)

    st.markdown("#### 估值概览")
    valuation_columns = st.columns(3)
    valuation_items = [
        ("市盈率 TTM", "pe_ttm"),
        ("静态市盈率", "pe_static"),
        ("动态市盈率", "pe_dynamic"),
    ]
    for column, (label, key) in zip(valuation_columns, valuation_items):
        value = valuation.get(key)
        with column:
            st.metric(label, f"{value:.2f} 倍" if value is not None else "亏损 / 不适用")
    if valuation_error:
        st.caption(f"公开估值数据暂不可用：{valuation_error}")
    elif valuation.get("source"):
        valuation_source_note, valuation_profit_note = st.columns([1.45, 1], gap="large")
        with valuation_source_note:
            st.caption(
                f"估值数据来源：{valuation['source']} · {valuation.get('as_of', '')}"
            )
        if valuation.get("ttm_net_profit") is not None:
            with valuation_profit_note:
                st.markdown(
                    '<div class="valuation-note-right">TTM 净利润（最近四个季度）：'
                    f"{format_amount(valuation['ttm_net_profit'], market)}</div>",
                    unsafe_allow_html=True,
                )
else:
    primary_metric_columns = st.columns(3)
    with primary_metric_columns[0]:
        st.metric(
            current_price_label,
            f"{currency_symbol}{latest_price:.2f}",
            price_delta_label,
            delta_color="normal",
        )
    with primary_metric_columns[1]:
        st.metric("52周最高", f"{currency_symbol}{high_52w:.2f}")
    with primary_metric_columns[2]:
        st.metric("52周最低", f"{currency_symbol}{low_52w:.2f}")

    secondary_metric_columns = st.columns(4)
    with secondary_metric_columns[0]:
        st.metric("平均成交量", format_volume(volume_avg, display_market))
        st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
    with secondary_metric_columns[1]:
        render_max_daily_amount_card(format_amount(max_daily_amount, display_market), max_daily_amount_date)
    with secondary_metric_columns[2]:
        st.metric("年化波动率", volatility_label)
        st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)
    with secondary_metric_columns[3]:
        st.metric("总市值", format_market_cap(market_cap, display_market))
        st.markdown('<span class="secondary-metric-marker"></span>', unsafe_allow_html=True)

# ============ 主内容区域 ============
tab1, tab_intraday, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "价格分析",
        "当日分时",
        "技术指标",
        "数据详情",
        "投资洞察",
        "财务报表",
    ]
)

history_rsi = calculate_rsi(indicator_history_df, rsi_period)
df['RSI'] = history_rsi.reindex(df.index)
df_macd = trim_to_display_range(calculate_macd(indicator_history_df), start_date, end_date)

# ============ Tab 1: 价格分析 ============
with tab1:
    price_chart_heading, refresh_col = st.columns([5, 1])
    with price_chart_heading:
        st.subheader("K线图与成交量")
    with refresh_col:
        refresh_price_page = st.button(
            "立即刷新",
            key=f"refresh-intraday-from-price:{ticker}",
            width="stretch",
        )
    if refresh_price_page:
        refresh_intraday_data(ticker)
        st.rerun()
    volume_metric_label = st.segmented_control(
        "副图指标",
        ["成交量", "成交额"],
        default="成交量",
        key="price_volume_metric",
    )
    volume_metric = "amount" if volume_metric_label == "成交额" else "volume"

    # 计算移动平均线
    df_with_ma = indicator_history_df.copy()
    for period in ma_periods:
        df_with_ma[f'MA_{period}'] = calculate_ma(df_with_ma, period)
    if show_bbi:
        df_with_ma["BBI"] = calculate_bbi(df_with_ma)
    if show_boll:
        df_with_ma = calculate_bollinger_bands(df_with_ma)
    df_with_ma = trim_to_display_range(df_with_ma, start_date, end_date)

    # 绘制K线图
    chart_df = pad_new_listing_chart(
        df_with_ma,
        is_new_listing_history(indicator_history_df, calculation_start_date),
        start_date,
        end_date,
    )
    fig = plot_candlestick(
        chart_df,
        ma_periods,
        currency="CNY" if display_market == "CN" else "KRW" if display_market == "KR" else "USD",
        market=display_market,
        show_bbi=show_bbi,
        show_boll=show_boll,
        volume_metric=volume_metric,
    )
    st.plotly_chart(fig, width="stretch")

# ============ 当日分时 ============
with tab_intraday:
    render_intraday_panel(ticker, market, display_market, intraday_currency_rate)

# ============ Tab 2: 技术指标 ============
with tab2:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("RSI (相对强弱指标)")
        fig_rsi = plot_rsi(df, rsi_period)
        st.plotly_chart(fig_rsi, width="stretch")

        # RSI 解读
        latest_rsi = df['RSI'].iloc[-1]
        if not new_listing["rsi_ready"]:
            st.info(f"历史日 K 不足 {rsi_period + 1} 根，暂无法计算 RSI。")
        elif latest_rsi > 70:
            st.warning(f"⚠️ RSI = {latest_rsi:.1f} > 70，可能处于**超买**状态")
        elif latest_rsi < 30:
            st.success(f"✅ RSI = {latest_rsi:.1f} < 30，可能处于**超卖**状态")
        else:
            st.info(f"ℹ️ RSI = {latest_rsi:.1f}，处于中性区间")

    with col2:
        st.subheader("MACD (指数平滑异同平均线)")
        fig_macd = plot_macd(df_macd)
        st.plotly_chart(fig_macd, width="stretch")

        # MACD 解读
        latest_macd = df_macd['MACD'].iloc[-1]
        latest_signal = df_macd['Signal'].iloc[-1]
        if not new_listing["macd_ready"]:
            st.info("历史日 K 不足 26 根，暂不解读 MACD 信号。")
        elif latest_macd > latest_signal:
            st.success(f"✅ MACD ({latest_macd:.2f}) > Signal ({latest_signal:.2f})，**看涨信号**")
        else:
            st.warning(f"⚠️ MACD ({latest_macd:.2f}) < Signal ({latest_signal:.2f})，**看跌信号**")

# ============ Tab 3: 数据详情 ============
with tab3:
    st.subheader("原始数据")

    # 数据筛选
    col1, col2 = st.columns([1, 3])
    with col1:
        max_rows = min(100, len(df))
        rows_to_show = (
            st.slider("显示行数", 1, max_rows, min(20, max_rows))
            if new_listing["show_rows_slider"]
            else max_rows
        )

    # 显示数据
    display_df = df.tail(rows_to_show).copy()
    display_df.index = display_df.index.strftime('%Y-%m-%d')
    display_df = display_df.round(2)
    if "Volume" in display_df:
        display_df["Volume"] = display_df["Volume"].map(lambda value: format_volume(value, display_market))
    if "Amount" in display_df:
        display_df["Amount"] = display_df["Amount"].map(lambda value: format_amount(value, display_market))
    display_df.index.name = "日期"
    display_df = display_df.rename(
        columns={
            "Open": "开盘价",
            "High": "最高价",
            "Low": "最低价",
            "Close": "收盘价",
            "Volume": "成交量",
            "Amount": "成交额",
            "RSI": "RSI（相对强弱指标）",
        }
    )

    st.dataframe(
        display_df,
        width="stretch",
        column_config=data_detail_column_config("日期"),
    )

    # 下载按钮
    csv = df.to_csv().encode('utf-8')
    st.download_button(
        label="下载完整数据 (CSV)",
        data=csv,
        file_name=f"{ticker}_stock_data.csv",
        mime="text/csv"
    )

    # 数据统计
    st.subheader("数据统计摘要")
    st.dataframe(
        format_statistics(df, display_market),
        width="stretch",
        column_config=data_detail_column_config("统计项"),
    )

# ============ Tab 4: 投资洞察 ============
with tab4:
    st.subheader("AI 驱动的投资分析")

    # 简单规则引擎（模拟"AI分析"）
    signals = []

    # 价格趋势
    if not new_listing["trend_ready"]:
        signals.append(("历史数据", "待观察", f"上市以来仅 {new_listing['daily_bars']} 根日 K，暂不生成技术信号", "blue"))
    elif df['Close'].iloc[-1] > df['Close'].iloc[-20:].mean():
        signals.append(("价格趋势", "看涨", "当前价格高于20日均线", "green"))
    else:
        signals.append(("价格趋势", "看跌", "当前价格低于20日均线", "red"))

    # RSI
    if not new_listing["rsi_ready"]:
        signals.append(("RSI指标", "待观察", "历史日 K 不足，暂不生成 RSI 信号", "blue"))
    elif df['RSI'].iloc[-1] < 30:
        signals.append(("RSI指标", "超卖", "RSI低于30，可能存在反弹机会", "green"))
    elif df['RSI'].iloc[-1] > 70:
        signals.append(("RSI指标", "超买", "RSI高于70，可能存在回调风险", "red"))
    else:
        signals.append(("RSI指标", "中性", "RSI处于正常区间", "gray"))

    # MACD
    if not new_listing["macd_ready"]:
        signals.append(("MACD指标", "待观察", "历史日 K 不足，暂不生成 MACD 信号", "blue"))
    elif df_macd['MACD'].iloc[-1] > df_macd['Signal'].iloc[-1]:
        signals.append(("MACD指标", "金叉", "MACD上穿Signal线，买入信号", "green"))
    else:
        signals.append(("MACD指标", "死叉", "MACD下穿Signal线，卖出信号", "red"))

    # 波动率
    if not new_listing["volatility_ready"]:
        signals.append(("波动率", "待观察", "至少需要两根日 K 才能计算波动率", "blue"))
    elif volatility > 30:
        signals.append(("波动率", "高风险", f"年化波动率达{volatility:.1f}%，需注意风险", "orange"))
    else:
        signals.append(("波动率", "正常", f"年化波动率为{volatility:.1f}%", "green"))

    # 显示信号
    for name, status, desc, color in signals:
        with st.container():
            col1, col2, col3 = st.columns([2, 2, 6])
            col1.markdown(f"**{name}**")
            col2.markdown(f":{color}[{status}]")
            col3.markdown(f"*{desc}*")
            st.markdown("---")

    # 综合评分
    st.subheader("综合评分")
    if not new_listing["trend_ready"]:
        st.info("新股历史数据不足，暂不提供综合技术评分。")
    else:
        bullish_count = sum(1 for _, status, _, _ in signals if status in ["看涨", "超卖", "金叉", "正常"])
        score = (bullish_count / len(signals)) * 100
        st.progress(score / 100, text=f"看涨评分: {score:.0f}/100")
        if score > 60:
            st.success("综合建议：技术指标偏向看涨，可考虑适量建仓")
        elif score > 40:
            st.warning("综合建议：信号混合，建议观望或轻仓操作")
        else:
            st.error("综合建议：技术指标偏向看跌，建议谨慎或减仓")

# ============ Tab 5: 财务报表 ============
with tab5:
    st.subheader("年度与季度财务报告")
    try:
            financial_reports = load_financial_reports(ticker, market, cache_version=2)
            annual_reports = financial_reports[
                financial_reports["报告类型"] == "年报"
            ].head(4)
            quarter_reports = financial_reports[
                financial_reports["报告类型"] != "年报"
            ].head(4)
            quarter_chart_reports = quarter_reports
            if market == "CN" and not quarter_reports.empty:
                quarter_dates = pd.to_datetime(quarter_reports["报告期"])
                annual_fill_reports = financial_reports[
                    (financial_reports["报告类型"] == "年报")
                    & pd.to_datetime(financial_reports["报告期"]).between(
                        quarter_dates.min(), quarter_dates.max()
                    )
                ]
                quarter_chart_reports = (
                    pd.concat([quarter_reports, annual_fill_reports], ignore_index=True)
                    .drop_duplicates(subset=["报告期"], keep="first")
                    .sort_values("报告期", ascending=False)
                )

            source_note = "；季报指标为报告期累计口径。" if market == "CN" else "；金额按报告币种展示。"
            if market == "KR" and display_market == "US":
                source_note = f"；金额与每股收益按参考汇率换算为美元（1 美元 = {1 / krw_usd_rate:,.2f} 韩元）。"
            st.caption(f"数据来源：{financial_reports.attrs.get('source', '—')}{source_note}")

            if market == "CN" and (not annual_reports.empty or not quarter_reports.empty):
                st.markdown("#### 财报趋势")
                annual_chart_column, quarter_chart_column = st.columns(2)
                with annual_chart_column:
                    if not annual_reports.empty:
                        st.plotly_chart(
                            plot_financial_report_bars(annual_reports, "年报：营收与净利润"),
                            width="stretch",
                            key=f"financial-annual-bars:{ticker}",
                            config={"displayModeBar": False},
                        )
                with quarter_chart_column:
                    if not quarter_reports.empty:
                        st.plotly_chart(
                            plot_financial_report_bars(quarter_chart_reports, "季报趋势（年报补齐第四季度）"),
                            width="stretch",
                            key=f"financial-quarter-bars:{ticker}",
                            config={"displayModeBar": False},
                        )
                        if len(quarter_chart_reports) > len(quarter_reports):
                            st.caption("季度图以年报补齐缺失的第四季度；下方季度表不受影响。")

            annual_heading = f"近{len(annual_reports)}个财年" if not annual_reports.empty else "财年报告"
            st.markdown(f"#### {annual_heading}")
            if annual_reports.empty:
                st.info("暂未读取到可展示的年报。")
            else:
                st.table(
                    format_financial_report_table(annual_reports, display_market, krw_usd_rate),
                    width="stretch",
                    hide_index=True,
                )

            quarter_heading = f"最新{len(quarter_reports)}个季度" if not quarter_reports.empty else "季度报告"
            st.markdown(f"#### {quarter_heading}")
            if quarter_reports.empty:
                st.info("暂未读取到可展示的季度报告。")
            else:
                st.table(
                    format_financial_report_table(quarter_reports, display_market, krw_usd_rate),
                    width="stretch",
                    hide_index=True,
                )
    except DataFetchError as error:
        st.warning(str(error))

# ============ 页脚 ============
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>Stock Insight | Personal market analysis dashboard | Data: Tonghuashun, Yahoo Finance, Eastmoney & Douyin</p>
</div>
""", unsafe_allow_html=True)
