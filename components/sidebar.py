from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import streamlit as st

from config.app_config import KR_TICKER_OPTIONS, US_TICKER_OPTIONS


@dataclass(frozen=True)
class DashboardControls:
    ticker: str
    start_date: object
    end_date: object
    ma_periods: list[int]
    show_bbi: bool
    show_boll: bool
    rsi_period: int


def render_sidebar(market: str, a_share_universe: dict) -> DashboardControls:
    """Render all dashboard inputs and return their values as one object."""
    st.sidebar.header("行情参数")
    if market == "CN":
        pending_ticker = st.session_state.pop("pending_a_share_ticker", None)
        if pending_ticker:
            for candidate_industry, stocks in a_share_universe.items():
                if any(code == pending_ticker for _, code in stocks):
                    st.session_state["a_share_industry"] = candidate_industry
                    break

        industry = st.sidebar.selectbox(
            "产业链赛道", list(a_share_universe.keys()), key="a_share_industry"
        )
        options = {f"{name} ({code})": code for name, code in a_share_universe[industry]}
        if pending_ticker in options.values():
            st.session_state["a_share_ticker"] = next(
                label for label, code in options.items() if code == pending_ticker
            )
        ticker = options[
            st.sidebar.selectbox("选择股票", list(options), key="a_share_ticker")
        ]
    elif market == "US":
        selected = st.sidebar.selectbox("选择股票", list(US_TICKER_OPTIONS))
        ticker = st.sidebar.text_input("输入股票代码", "AAPL").upper() if US_TICKER_OPTIONS[selected] == "CUSTOM" else US_TICKER_OPTIONS[selected]
    else:
        st.sidebar.caption("当前仅提供市值前五个股")
        ticker = KR_TICKER_OPTIONS[
            st.sidebar.selectbox("选择股票", list(KR_TICKER_OPTIONS), key="kr_ticker")
        ]

    first, second = st.sidebar.columns(2)
    with first:
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=365))
    with second:
        end_date = st.date_input("结束日期", datetime.now())

    st.sidebar.markdown("---")
    st.sidebar.subheader("技术指标设置")
    raw_periods = st.sidebar.multiselect(
        "移动平均线周期",
        options=[5, 10, 20, 30, 50, 60, 120],
        default=[5, 10, 20],
        accept_new_options=True,
    )
    ma_periods = []
    for value in raw_periods:
        try:
            period = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= period <= 500 and period not in ma_periods:
            ma_periods.append(period)

    first, second = st.sidebar.columns(2)
    with first:
        show_bbi = st.toggle("BBI 线", value=False)
    with second:
        show_boll = st.toggle("BOLL 线", value=False)
    rsi_period = st.sidebar.slider("RSI周期", 7, 21, 14)
    return DashboardControls(ticker, start_date, end_date, ma_periods, show_bbi, show_boll, rsi_period)
