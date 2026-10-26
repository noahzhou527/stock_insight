"""Local persistence and sidebar controls for the A-share watchlist."""

from __future__ import annotations

import json
import html
import re
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np

from market_snapshot import fetch_a_share_market_snapshot, MarketSnapshotError
from services.market_data import is_a_share_trading_session
from browser_state import save_browser_state


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
    st.session_state["watchlist_view"] = "总览"
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
        options = {item["ticker"]: f"{item['name'] or known_names.get(item['ticker'], item['ticker'])} ({item['ticker']})" for item in items}
        pending_ticker = st.session_state.pop("pending_a_share_watchlist_ticker", None)
        if pending_ticker in options:
            st.session_state["a_share_watchlist_ticker"] = pending_ticker
        if st.session_state.get("a_share_watchlist_ticker") not in options:
            st.session_state["a_share_watchlist_ticker"] = next(iter(options))
        selected = st.sidebar.selectbox(
            "选择自选股",
            list(options),
            key="a_share_watchlist_ticker",
            format_func=options.get,
            label_visibility="collapsed",
        )
        selected_ticker = selected
        if st.sidebar.button("移出自选股", width="stretch"):
            save_watchlist([item for item in items if item["ticker"] != selected_ticker])
            st.session_state["watchlist_view"] = "总览"
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


def reset_watchlist_view() -> None:
    st.session_state["watchlist_view"] = "总览"
    st.session_state["_watchlist_needs_refresh"] = True


def open_watchlist_stock(ticker: str) -> None:
    st.session_state["pending_a_share_watchlist_ticker"] = ticker
    st.session_state["a_share_watchlist_ticker"] = ticker
    st.session_state["watchlist_view"] = "详情"


def summarize_watchlist(snapshot: pd.DataFrame) -> dict:
    """Summarize one quote date; cached and invalid quotes never count as flat."""
    dates = pd.to_datetime(snapshot["trade_date"], errors="coerce").dt.normalize()
    latest = dates.max()
    changes = pd.to_numeric(snapshot["change_pct"], errors="coerce")
    valid = snapshot.loc[dates.eq(latest) & ~snapshot["stale"] & np.isfinite(changes)].copy()
    values = pd.to_numeric(valid["change_pct"], errors="coerce")
    return {
        "date": latest.strftime("%Y-%m-%d") if pd.notna(latest) else None,
        "count": len(valid), "total": len(snapshot),
        "average": float(values.mean()) if len(valid) else None,
        "up": int((values > 0).sum()), "down": int((values < 0).sum()),
        "flat": int((values == 0).sum()),
        "leader": valid.loc[values.idxmax()] if len(valid) else None,
        "laggard": valid.loc[values.idxmin()] if len(valid) else None,
    }


@st.cache_data(ttl=25, show_spinner=False)
def load_watchlist_snapshot(rows: list[dict]) -> pd.DataFrame:
    return fetch_a_share_market_snapshot(rows)


def _remove_watchlist_stock(ticker: str) -> None:
    save_watchlist([item for item in load_watchlist() if item["ticker"] != ticker])
    reset_watchlist_view()


def _quote_number(value, *, signed=False, suffix="") -> str:
    if pd.isna(value) or not np.isfinite(float(value)):
        return "—"
    return (f"{float(value):+.2f}" if signed else f"{float(value):.2f}") + suffix


@st.fragment(run_every="30s")
def _render_watchlist_quotes(rows: list[dict], query: str, sort: str) -> None:
    # The timer stays alive across lunch/close; only trading sessions fetch again.
    identity = tuple(row["ticker"] for row in rows)
    previous = st.session_state.get("_watchlist_snapshot")
    manual = st.button("刷新行情", key="watchlist_refresh")
    if manual:
        load_watchlist_snapshot.clear()
    entering = st.session_state.pop("_watchlist_needs_refresh", False)
    if manual or entering or previous is None or previous[0] != identity or is_a_share_trading_session():
        try:
            with st.spinner("正在获取自选行情…"):
                snapshot = load_watchlist_snapshot(rows)
            st.session_state["_watchlist_snapshot"] = (identity, snapshot)
            st.session_state["_watchlist_refreshed"] = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%H:%M:%S")
            st.session_state.pop("_watchlist_error", None)
        except MarketSnapshotError:
            st.session_state["_watchlist_error"] = "行情刷新失败，请稍后重试。"
            snapshot = previous[1].copy() if previous and previous[0] == identity else pd.DataFrame()
            if not snapshot.empty:
                snapshot["stale"] = True
                st.session_state["_watchlist_snapshot"] = (identity, snapshot)
    else:
        snapshot = previous[1]
    if error := st.session_state.get("_watchlist_error"):
        st.warning(error)
    if snapshot.empty:
        st.info("暂无可用行情；自选列表仍可管理和进入分析。")
        snapshot = pd.DataFrame(rows).assign(price=np.nan, previous_close=np.nan,
            change_pct=np.nan, amount=np.nan, quote_time=None, trade_date=None, stale=True)

    summary = summarize_watchlist(snapshot)
    today = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d")
    is_today = summary["date"] == today and summary["count"] > 0
    st.subheader(f"{'当日表现' if is_today else '最近交易日'} · {summary['date'] or '暂无日期'}")
    if not summary["count"]:
        st.caption("暂无有效行情统计，缓存与缺失数据不计入平均涨幅和涨跌数量。")
    metrics = st.columns(4)
    metrics[0].metric("自选总数", summary["total"])
    metrics[1].metric("等权平均涨跌幅", _quote_number(summary["average"], signed=True, suffix="%"))
    metrics[2].metric("上涨 / 下跌 / 平盘", f"{summary['up']} / {summary['down']} / {summary['flat']}")
    metrics[3].metric("有效样本", f"{summary['count']} / {summary['total']}")
    leaders = st.columns(2)
    for column, label, key in zip(leaders, ["领涨", "领跌"], ["leader", "laggard"]):
        row = summary[key]
        column.caption(label + "：" + (f"{row['name'] or row['ticker']} {_quote_number(row['change_pct'], signed=True, suffix='%')}" if row is not None else "—"))
    st.caption(f"行情来源：东方财富 · 最近加载 {st.session_state.get('_watchlist_refreshed', '—')} · 交易时段每30秒更新 · 等权指标不代表持仓收益")

    display = snapshot.copy()
    # Provider names remain session-only; never overwrite user favorites during a refresh.
    names = dict(st.session_state.get("a_share_live_names", {}))
    names.update({row.ticker: row.name for row in snapshot.itertuples() if row.name})
    st.session_state["a_share_live_names"] = names
    if query.strip():
        needle = query.strip().casefold()
        display = display.loc[(display["name"].fillna("").str.casefold().str.contains(needle, regex=False)) |
                              display["ticker"].str.casefold().str.contains(needle, regex=False)]
    sorts = {"涨幅优先": ("change_pct", False), "跌幅优先": ("change_pct", True),
             "价格从高到低": ("price", False), "成交额从高到低": ("amount", False)}
    if sort in sorts:
        field, ascending = sorts[sort]
        display = display.sort_values(field, ascending=ascending, kind="stable", na_position="last")

    st.markdown("""<style>
    .watch-up {color:#e53935} .watch-down {color:#1e9d55}
    [class*="st-key-watchlist-table"] {overflow-x:auto}
    [class*="st-key-watchlist-table"] [data-testid="stHorizontalBlock"] {min-width:880px;flex-wrap:nowrap}
    [class*="st-key-watchlist-table"] [data-testid="stColumn"] {width:auto!important;min-width:0!important;flex:1 1 0!important}
    [class*="st-key-watchlist-table"] [data-testid="stColumn"]:nth-child(1) {flex-grow:2!important}
    [class*="st-key-watchlist-table"] [data-testid="stColumn"]:nth-child(5) {flex-grow:1.2!important}
    [class*="st-key-watchlist-table"] [data-testid="stColumn"]:nth-child(6) {flex-grow:1.8!important}
    [class*="st-key-watchlist-table"] [data-testid="stColumn"]:nth-child(7) {flex-grow:1.4!important}
    [class*="st-key-watchlist-table"] [data-testid="stColumn"]:nth-child(8) {flex-grow:.7!important}
    [class*="st-key-watchlist-table"] p {white-space:nowrap;margin:0}
    [class*="st-key-watchlist-table"] .stButton button {min-height:2rem;padding:.1rem .3rem}
    </style>""", unsafe_allow_html=True)
    widths = [2, 1, 1, 1, 1.2, 1.8, 1.4, .7]
    with st.container(key="watchlist-table", border=True):
        for column, label in zip(st.columns(widths), ["股票 / 代码", "最新价", "涨跌幅", "涨跌额", "成交额(亿)", "行情时间", "状态", "管理"]):
            column.markdown(f"**{label}**")
        for row in display.itertuples():
            columns = st.columns(widths, gap="small")
            if columns[0].button(row.name or row.ticker, key=f"watch-open:{row.ticker}", type="tertiary"):
                open_watchlist_stock(row.ticker)
                st.rerun(scope="app")
            columns[0].caption(row.ticker)
            color = "watch-up" if row.change_pct > 0 else "watch-down" if row.change_pct < 0 else ""
            values = [_quote_number(row.price), _quote_number(row.change_pct, signed=True, suffix="%"),
                      _quote_number(row.price - row.previous_close, signed=True), _quote_number(row.amount / 1e8)]
            for column, value in zip(columns[1:5], values):
                column.markdown(f'<span class="{color}">{html.escape(value)}</span>', unsafe_allow_html=True)
            columns[5].caption(str(row.quote_time or "—"))
            date = str(row.trade_date or "")[:10]
            status = "缺失" if pd.isna(row.price) else "缓存" if row.stale else "旧日期" if date != summary["date"] else "最新行情"
            columns[6].caption(status)
            if date and status in {"缓存", "旧日期"}:
                columns[6].caption(date)
            if columns[7].button("移除", key=f"watch-remove:{row.ticker}"):
                _remove_watchlist_stock(row.ticker)
                st.rerun(scope="app")
    if display.empty:
        st.info("没有匹配的自选股。")
    save_browser_state()


def render_watchlist_overview(universe: dict) -> None:
    st.subheader("自选池总览")
    with st.form("watchlist-overview-add", border=False):
        entry, action = st.columns([4, 1])
        entry.text_input("添加A股代码", placeholder="例如 300308 或 688525.SH", key="manual_watchlist_ticker")
        action.form_submit_button("加入自选股", on_click=_save_manual_stock, args=(universe,))
    if error := st.session_state.pop("manual_watchlist_error", None):
        st.error(error)
    search, order = st.columns([3, 2])
    query = search.text_input("名称 / 代码搜索", key="watchlist_search")
    sort = order.selectbox("排序", ["加入顺序", "涨幅优先", "跌幅优先", "价格从高到低", "成交额从高到低"], key="watchlist_sort")
    items = load_watchlist()
    if not items:
        st.info("自选池为空，输入股票代码开始关注。")
        save_browser_state()
        return
    known = {ticker: (industry, name) for industry, stocks in universe.items() for name, ticker in stocks}
    live_names = st.session_state.get("a_share_live_names", {})
    rows = [{"ticker": item["ticker"], "name": item["name"] or live_names.get(item["ticker"], known.get(item["ticker"], ("", ""))[1]),
             "industry": known.get(item["ticker"], ("未分类", ""))[0]} for item in items]
    _render_watchlist_quotes(rows, query, sort)
