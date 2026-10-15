"""Browser-local UI preferences; never persist quotes, credentials or caches."""

from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components


CHOICES = {
    "page_navigation": ["行情分析", "市场总览", "指标说明"],
    "market_navigation": ["美股", "A股", "韩股"],
    "market_view_navigation": ["个股分析", "我的自选", "股票池排行"],
    "watchlist_view": ["总览", "详情"],
    "watchlist_sort": ["加入顺序", "最近加入优先", "涨幅优先", "跌幅优先", "价格从高到低", "价格从低到高", "涨跌额从高到低", "涨跌额从低到高", "成交额从高到低", "成交额从低到高"],
    "price_volume_metric": ["成交量", "成交额"],
    "market-overview-page-market": ["A股", "美股", "韩股 KOSPI"],
}
TEXT_KEYS = {
    "a_share_industry", "a_share_ticker", "a_share_watchlist_ticker",
    "kr_ticker", "us_ticker", "us_custom_ticker",
    "watchlist_search",
}
DATE_KEYS = {"display_start", "display_end"}
BOOL_KEYS = {"show_bbi", "show_boll"}
WATCHLIST_FIELDS = {"name", "ticker", "price", "change_pct", "intraday", "amount", "change", "turnover", "amplitude", "previous_close", "open", "high", "low", "return_5", "return_20", "market_cap", "tag"}
KEYS = set(CHOICES) | TEXT_KEYS | DATE_KEYS | BOOL_KEYS | {"ma_periods", "rsi_period", "a_share_live_names", "watchlist_columns"}


def valid_native_sort(value):
    if isinstance(value, dict) and isinstance(value.get("field"), str) and value["field"] in WATCHLIST_FIELDS - {"intraday"} and type(value.get("ascending")) is bool:
        return {"field": value["field"], "ascending": value["ascending"]}
    return None


def valid_preferences(raw):
    result = {}
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        if key in CHOICES and value in CHOICES[key]:
            result[key] = value
        elif key in TEXT_KEYS and isinstance(value, str) and len(value) <= 160:
            result[key] = value
        elif key in BOOL_KEYS and isinstance(value, bool):
            result[key] = value
        elif key in DATE_KEYS and isinstance(value, str):
            try:
                result[key] = date.fromisoformat(value)
            except ValueError:
                pass
        elif key == "rsi_period" and type(value) is int and 7 <= value <= 21:
            result[key] = value
        elif key == "ma_periods" and isinstance(value, list) and all(type(v) is int and v in [5, 10, 20, 30, 50, 60, 120] for v in value):
            result[key] = list(dict.fromkeys(value))
        elif key == "a_share_live_names" and isinstance(value, dict):
            result[key] = {k: v for k, v in value.items() if isinstance(k, str) and isinstance(v, str) and len(k) <= 16 and len(v) <= 80}
        elif key == "watchlist_columns" and isinstance(value, list):
            result[key] = list(dict.fromkeys(v for v in value if isinstance(v, str) and v in WATCHLIST_FIELDS))
    return result


_storage = components.component(
    "stock_insight_browser_state",
    js=(Path(__file__).parent / "assets" / "browser_state.js").read_text(encoding="utf-8"),
)


def sync_browser_state():
    ready = st.session_state.get("_browser_state_ready", False)
    result = _storage(
        data={"ready": ready, "idle": ready},
        key="browser_state_bridge", on_loaded_change=lambda: None, height=0,
    )
    if not ready:
        if result.loaded is None:
            st.stop()
        saved = result.loaded if isinstance(result.loaded, dict) else {}
        st.session_state.update(valid_preferences(saved.get("preferences")))
        table = saved.get("watchlistTable")
        if isinstance(table, dict):
            st.session_state["watchlist_native_sort"] = valid_native_sort(table.get("sort"))
        if type(saved.get("viewport_width")) is int:
            st.session_state["_viewport_width"] = saved["viewport_width"]
        st.session_state["_browser_state_ready"] = True
        st.rerun()
    for key in KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def save_browser_state(*, fragment=False):
    old_compact = st.session_state.get("_viewport_width", 1280) < 720
    old_sort = st.session_state.get("watchlist_native_sort")
    preferences = {key: st.session_state[key] for key in KEYS if key in st.session_state}
    preferences = {key: value.isoformat() if isinstance(value, date) else value for key, value in preferences.items()}
    result = _storage(
        data={"ready": True, "preferences": preferences, "watchlistLabels": st.session_state.get("_watchlist_column_labels", {})},
        key="browser_state_writer", on_viewportWidth_change=lambda: None, on_watchlistTable_change=lambda: None, height=0,
    )
    if type(getattr(result, "viewportWidth", None)) is int:
        st.session_state["_viewport_width"] = result.viewportWidth
    table = getattr(result, "watchlistTable", None)
    if isinstance(table, dict) and table.get("baseSort") == preferences.get("watchlist_sort"):
        st.session_state["watchlist_native_sort"] = valid_native_sort(table.get("sort"))
    if old_compact != (st.session_state.get("_viewport_width", 1280) < 720) or old_sort != st.session_state.get("watchlist_native_sort"):
        st.rerun(scope="fragment" if fragment else "app")
