"""Browser-local UI preferences; never persist quotes, credentials or caches."""

from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components


CHOICES = {
    "page_navigation": ["行情分析", "市场总览", "指标说明", "新闻热点"],
    "market_navigation": ["美股", "A股", "韩股"],
    "market_view_navigation": ["个股分析", "我的自选", "股票池排行"],
    "price_volume_metric": ["成交量", "成交额"],
    "market-overview-page-market": ["A股", "美股", "韩股 KOSPI"],
}
TEXT_KEYS = {
    "a_share_industry", "a_share_ticker", "a_share_watchlist_ticker",
    "kr_ticker", "us_ticker", "us_custom_ticker",
}
DATE_KEYS = {"display_start", "display_end"}
BOOL_KEYS = {"show_bbi", "show_boll"}
KEYS = set(CHOICES) | TEXT_KEYS | DATE_KEYS | BOOL_KEYS | {"ma_periods", "rsi_period", "a_share_live_names"}


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
        if saved.get("theme") in ("light", "dark"):
            st.query_params["theme"] = saved["theme"]
        st.session_state["_browser_state_ready"] = True
        st.rerun()
    for key in KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def save_browser_state():
    preferences = {key: st.session_state[key] for key in KEYS if key in st.session_state}
    preferences = {key: value.isoformat() if isinstance(value, date) else value for key, value in preferences.items()}
    _storage(
        data={"ready": True, "preferences": preferences, "theme": st.query_params.get("theme", "dark")},
        key="browser_state_writer", height=0,
    )
