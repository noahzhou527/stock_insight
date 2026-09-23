from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import streamlit as st

from app_config import KR_TICKER_OPTIONS, US_TICKER_OPTIONS
from watchlist import render_a_share_watchlist_sidebar, render_add_current_stock_button


MA_PERIOD_OPTIONS = [5, 10, 20, 30, 50, 60, 120]


@dataclass(frozen=True)
class DashboardControls:
    ticker: str | None
    start_date: object
    end_date: object
    ma_periods: list[int]
    show_bbi: bool
    show_boll: bool
    rsi_period: int


def render_sidebar(
    market: str,
    a_share_universe: dict,
    *,
    a_share_watchlist: bool = False,
) -> DashboardControls:
    """Render all dashboard inputs and return their values as one object."""
    st.sidebar.header("行情参数")
    if market == "CN":
        if a_share_watchlist:
            ticker = render_a_share_watchlist_sidebar(a_share_universe)
        else:
            pending_ticker = st.session_state.pop("pending_a_share_ticker", None)
            if pending_ticker:
                for candidate_industry, stocks in a_share_universe.items():
                    if any(code == pending_ticker for _, code in stocks):
                        st.session_state["a_share_industry"] = candidate_industry
                        break

            industry = st.sidebar.selectbox(
                "产业链赛道", list(a_share_universe.keys()), key="a_share_industry"
            )
            live_names = st.session_state.get("a_share_live_names", {})
            stock_names = {
                code: live_names.get(code, name)
                for name, code in a_share_universe[industry]
            }
            options = {
                f"{stock_names[code]} ({code})": code
                for _, code in a_share_universe[industry]
            }
            if pending_ticker in options.values():
                st.session_state["a_share_ticker"] = next(
                    label for label, code in options.items() if code == pending_ticker
                )
            ticker = options[
                st.sidebar.selectbox("选择股票", list(options), key="a_share_ticker")
            ]
            render_add_current_stock_button(ticker, stock_names[ticker])
    elif market == "US":
        selected = st.sidebar.selectbox("选择股票", list(US_TICKER_OPTIONS), key="us_ticker")
        ticker = st.sidebar.text_input("输入股票代码", "AAPL", key="us_custom_ticker").upper() if US_TICKER_OPTIONS[selected] == "CUSTOM" else US_TICKER_OPTIONS[selected]
    else:
        st.sidebar.caption("当前仅提供市值前五个股")
        ticker = KR_TICKER_OPTIONS[
            st.sidebar.selectbox("选择股票", list(KR_TICKER_OPTIONS), key="kr_ticker")
        ]

    first, second = st.sidebar.columns(2)
    with first:
        start_date = st.date_input("开始日期", datetime.now() - timedelta(days=365), key="display_start")
    with second:
        end_date = st.date_input("结束日期", datetime.now(), key="display_end")

    st.sidebar.markdown("---")
    st.sidebar.subheader("技术指标设置")
    raw_periods = st.sidebar.multiselect(
        "移动平均线周期",
        options=MA_PERIOD_OPTIONS,
        default=[5, 10, 20],
        key="ma_periods",
        # 下拉列表只列「尚未选中」的选项，点 Select all 把 7 个全选中后列表为空，
        # Streamlit 会渲染空状态文案。默认的 "No results" 看着像报错，像功能坏了。
        # max_selections 与选项数相等不收紧可选范围，但会让前端改说
        # "You can only select up to N options…"，语义与可操作提示都正确。
        max_selections=len(MA_PERIOD_OPTIONS),
        # 关掉输入过滤：这个控件的输入框被 dashboard.css 压成 1px 宽且不产生可见绘制
        # （为了让标签占满整行），但打字仍然生效——打进去的词看不见，一旦匹配不到任何
        # 选项就静默弹出空列表，看起来像控件坏了。选项只有 7 个数字，过滤没有价值，
        # 关掉之后空状态就只剩「已全选」一种成因，文案才说得准。
        filter_mode=None,
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
        show_bbi = st.toggle("BBI 线", value=False, key="show_bbi")
    with second:
        show_boll = st.toggle("BOLL 线", value=False, key="show_boll")
    rsi_period = st.sidebar.slider("RSI周期", 7, 21, 14, key="rsi_period")
    return DashboardControls(ticker, start_date, end_date, ma_periods, show_bbi, show_boll, rsi_period)
