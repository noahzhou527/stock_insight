"""Local persistence and sidebar controls for the A-share watchlist."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import streamlit as st


WATCHLIST_PATH = Path(__file__).resolve().parent / "data" / "cache" / "watchlist.json"
_A_SHARE_TICKER = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")


def normalize_ticker(ticker: str) -> str:
    """Return a provider-compatible A-share ticker."""
    value = re.sub(r"\s+", "", str(ticker).upper()).replace("。", ".").replace("．", ".")
    prefix = re.fullmatch(r"(SH|SZ|BJ)[._-]?(\d{6})", value)
    suffix = re.fullmatch(r"(\d{6})[._-]?(SH|SZ|BJ)", value)
    copied_label = re.search(r"[（(](\d{6})(?:[._-]?(SH|SZ|BJ))?[）)]$", value)
    if prefix:
        value = f"{prefix.group(2)}.{prefix.group(1)}"
    elif suffix:
        value = f"{suffix.group(1)}.{suffix.group(2)}"
    elif copied_label:
        code, exchange = copied_label.groups()
        value = f"{code}.{exchange}" if exchange else code
    if re.fullmatch(r"\d{6}", value):
        value += ".SH" if value.startswith("6") else ".SZ" if value[0] in "023" else ".BJ"
    if not _A_SHARE_TICKER.fullmatch(value):
        raise ValueError("A股代码格式不正确，例如：300308 或 300308.SZ。")
    return value


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[dict[str, str]]:
    """Load valid locally saved A-share entries."""
    try:
        items = json.loads(path.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    result: list[dict[str, str]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            ticker = normalize_ticker(str(item.get("ticker", "")))
        except ValueError:
            continue
        if not any(saved["ticker"] == ticker for saved in result):
            result.append({"ticker": ticker, "name": str(item.get("name", "")).strip()})
    return result


def save_watchlist(items: list[dict[str, str]], path: Path = WATCHLIST_PATH) -> None:
    """Atomically persist the watchlist under the ignored local cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".tmp", dir=path.parent, delete=False
    ) as handle:
        json.dump({"items": items}, handle, ensure_ascii=False, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def add_watchlist_item(items: list[dict[str, str]], ticker: str, name: str = "") -> list[dict[str, str]]:
    normalized_ticker = normalize_ticker(ticker)
    if any(item["ticker"] == normalized_ticker for item in items):
        raise ValueError("该股票已在自选股中。")
    return [*items, {"ticker": normalized_ticker, "name": name.strip()}]


def _save_current_stock(ticker: str, name: str) -> None:
    """Add the stock already selected in the normal analysis view."""
    save_watchlist(add_watchlist_item(load_watchlist(), ticker, name))
    st.session_state["a_share_watchlist_notice"] = f"已将 {name} 加入自选股。"


def render_add_current_stock_button(ticker: str, name: str) -> None:
    """Render the watchlist action beside the normal A-share selector."""
    saved = any(item["ticker"] == ticker for item in load_watchlist())
    st.sidebar.button(
        "已在自选股" if saved else "加入自选股",
        disabled=saved,
        width="stretch",
        on_click=_save_current_stock if not saved else None,
        args=(ticker, name) if not saved else None,
    )
    if notice := st.session_state.pop("a_share_watchlist_notice", None):
        st.sidebar.success(notice)


def _save_manual_stock(a_share_universe: dict) -> None:
    """Add a typed A-share code while keeping the watchlist active."""
    known_names = {
        ticker: name
        for stocks in a_share_universe.values()
        for name, ticker in stocks
    }
    st.session_state["page_navigation"] = "行情分析"
    st.session_state["market_navigation"] = "A股"
    st.session_state["market_view_navigation"] = "我的自选"
    try:
        ticker = normalize_ticker(st.session_state.get("manual_watchlist_ticker", ""))
        save_watchlist(
            add_watchlist_item(
                load_watchlist(), ticker, known_names.get(ticker, "")
            )
        )
    except ValueError as error:
        st.session_state["manual_watchlist_error"] = str(error)
        return
    st.session_state["pending_a_share_watchlist_ticker"] = ticker
    st.session_state["manual_watchlist_ticker"] = ""


def render_a_share_watchlist_sidebar(a_share_universe: dict) -> str | None:
    """Manage favorites and return the ticker for the existing analysis page."""
    items = load_watchlist()
    known_names = {
        ticker: name
        for stocks in a_share_universe.values()
        for name, ticker in stocks
    }

    st.sidebar.subheader("我的自选股")
    selected_ticker = None
    if items:
        options = {
            f"{item['name'] or known_names.get(item['ticker'], item['ticker'])} ({item['ticker']})": item["ticker"]
            for item in items
        }
        pending_ticker = st.session_state.pop("pending_a_share_watchlist_ticker", None)
        if pending_ticker in options.values():
            st.session_state["a_share_watchlist_ticker"] = next(
                label for label, ticker in options.items() if ticker == pending_ticker
            )
        selected = st.sidebar.selectbox(
            "选择自选股",
            list(options),
            key="a_share_watchlist_ticker",
            label_visibility="collapsed",
        )
        selected_ticker = options[selected]
        if st.sidebar.button("移出自选股", width="stretch"):
            save_watchlist([item for item in items if item["ticker"] != selected_ticker])
            st.rerun()

    with st.sidebar.form("manual-watchlist-add", enter_to_submit=True, border=False):
        st.text_input(
            "股票代码",
            placeholder="输入股票代码",
            key="manual_watchlist_ticker",
            label_visibility="collapsed",
        )
        st.form_submit_button(
            "加入自选股",
            width="stretch",
            on_click=_save_manual_stock,
            args=(a_share_universe,),
        )
    if error := st.session_state.pop("manual_watchlist_error", None):
        st.sidebar.error(error)
    return selected_ticker
