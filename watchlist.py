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
from services.market_data import a_share_session_state, load_a_share_trade_dates, load_intraday
from services.watchlist_data import load_watchlist_extras, load_watchlist_benchmark, load_watchlist_status
from data_fetcher import DataFetchError
from browser_state import save_browser_state, valid_native_sort
from styles import load_styles, is_light_theme


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
            saved = {"ticker": ticker, "name": str(item.get("name", "")).strip()}
            if item.get("pinned") is True:
                saved["pinned"] = True
            if isinstance(item.get("tag"), str) and item["tag"].strip():
                saved["tag"] = item["tag"].strip()[:80]
            result.append(saved)
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
    st.session_state["_watchlist_grid_revision"] = st.session_state.get("_watchlist_grid_revision", 0) + 1


def open_watchlist_stock(ticker: str) -> None:
    st.session_state["pending_a_share_watchlist_ticker"] = ticker
    st.session_state["a_share_watchlist_ticker"] = ticker
    st.session_state["watchlist_view"] = "详情"


def summarize_watchlist(snapshot: pd.DataFrame) -> dict:
    """Summarize one quote date; cached and invalid quotes never count as flat."""
    dates = pd.to_datetime(snapshot["trade_date"], errors="coerce").dt.normalize()
    latest = dates.max()
    changes = pd.to_numeric(snapshot["change_pct"], errors="coerce")
    suspended = snapshot["suspended"] if "suspended" in snapshot else pd.Series(False, index=snapshot.index)
    valid = snapshot.loc[dates.eq(latest) & ~snapshot["stale"] & ~suspended & np.isfinite(changes)].copy()
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


WATCHLIST_PREFS_PATH = WATCHLIST_PATH.with_name("watchlist-view.json")
WATCHLIST_COLUMNS = {
    "name": "股票", "ticker": "代码", "price": "最新价", "change_pct": "涨跌幅",
    "intraday": "当天分时", "amount": "成交额（亿）", "change": "涨跌额", "turnover": "换手率（%）",
    "amplitude": "振幅（%）", "previous_close": "昨收", "open": "今开", "high": "最高", "low": "最低",
    "return_5": "近5日涨跌幅", "return_20": "近20日涨跌幅", "market_cap": "总市值（亿）", "tag": "产业链标签",
}
DEFAULT_COLUMNS = ["name", "ticker", "price", "change_pct", "intraday", "amount"]
WATCHLIST_SORTS = {
    "涨幅优先": ("change_pct", False), "跌幅优先": ("change_pct", True),
    "加入顺序": ("added_order", True), "最近加入优先": ("added_order", False),
    "价格从高到低": ("price", False), "价格从低到高": ("price", True),
    "涨跌额从高到低": ("change", False), "涨跌额从低到高": ("change", True),
    "成交额从高到低": ("amount", False), "成交额从低到高": ("amount", True),
}


def load_watchlist_preferences(path=None):
    path = path or WATCHLIST_PREFS_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    columns = raw.get("columns", DEFAULT_COLUMNS) if isinstance(raw, dict) else DEFAULT_COLUMNS
    columns = [c for c in columns if isinstance(c, str) and c in WATCHLIST_COLUMNS] if isinstance(columns, list) else DEFAULT_COLUMNS
    return {"sort": raw.get("sort", "涨幅优先") if isinstance(raw, dict) and isinstance(raw.get("sort"), str) and raw["sort"] in WATCHLIST_SORTS else "涨幅优先",
            "columns": list(dict.fromkeys([*columns, "name", "price", "change_pct"])),
            "native_sort": valid_native_sort(raw.get("native_sort")) if isinstance(raw, dict) else None}


def save_watchlist_preferences(sort, columns, path=None, native_sort=None):
    path = path or WATCHLIST_PREFS_PATH
    value = {"sort": sort if sort in WATCHLIST_SORTS else "涨幅优先", "columns": [c for c in columns if c in WATCHLIST_COLUMNS], "native_sort": valid_native_sort(native_sort)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        json.dump(value, file, ensure_ascii=False)
        temporary = Path(file.name)
    temporary.replace(path)


def _quote_number(value, *, signed=False, suffix=""):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return "—"
    return (f"{value:+.2f}" if signed and value > 0 else f"{value:.2f}") + suffix


def _change_color(value):
    value = pd.to_numeric(value, errors="coerce")
    return "watch-flat" if pd.isna(value) or value == 0 else "watch-up" if value > 0 else "watch-down"


def _direction_number(value):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return "—"
    return ("▲ " if value > 0 else "▼ " if value < 0 else "• ") + f"{value:+.2f}%"


def _quote_status(row, latest_date, now, trading):
    if getattr(row, "suspended", False):
        return "停牌"
    if pd.isna(row.price):
        return "数据缺失"
    if row.stale:
        return "缓存数据"
    if str(row.trade_date or "")[:10] != latest_date:
        return "旧日期"
    timestamp = pd.to_datetime(row.quote_time, errors="coerce")
    if trading:
        if pd.isna(timestamp):
            return "数据延迟"
        timestamp = timestamp.tz_localize("Asia/Shanghai") if timestamp.tzinfo is None else timestamp.tz_convert("Asia/Shanghai")
        if timestamp.date() != now.date() or (now - timestamp).total_seconds() > 300:
            return "数据延迟"
    return ""


def intraday_values(frame, day, previous_close):
    """Valid numeric minutes only: native chart columns reject null samples."""
    result = [None] * 241
    if frame is None or frame.empty or "Price" not in frame:
        return []
    times = pd.to_datetime(frame.index, errors="coerce")
    if times.tz is not None:
        times = times.tz_convert("Asia/Shanghai").tz_localize(None)
    prices = pd.to_numeric(frame["Price"], errors="coerce")
    reference = pd.to_numeric(previous_close, errors="coerce")
    for timestamp, price in zip(times, prices):
        if pd.isna(timestamp) or timestamp.date() != pd.Timestamp(day).date() or not np.isfinite(price) or price <= 0:
            continue
        minute = timestamp.hour * 60 + timestamp.minute
        slot = minute - 570 if 570 <= minute <= 690 else minute - 660 if 780 <= minute <= 900 else None
        if slot is not None:
            result[slot] = float((price / reference - 1) * 100) if pd.notna(reference) and reference > 0 else float(price)
    return [value for value in result if value is not None]


def build_watchlist_table(snapshot, items, curves, extras, now, trading, query="", sort="涨幅优先", native_sort=None):
    frame = snapshot.copy()
    metadata = {item["ticker"]: item for item in items}
    frame["added_order"] = frame["ticker"].map({item["ticker"]: i for i, item in enumerate(items)})
    frame["pinned"] = frame["ticker"].map(lambda t: metadata.get(t, {}).get("pinned", False))
    frame["tag"] = frame["ticker"].map(lambda t: metadata.get(t, {}).get("tag", ""))
    frame["name"] = frame.apply(lambda r: ("★ " if r["pinned"] else "") + str(r["name"] or r["ticker"]), axis=1)
    frame["change"] = pd.to_numeric(frame["price"], errors="coerce") - pd.to_numeric(frame["previous_close"], errors="coerce")
    latest = summarize_watchlist(snapshot)["date"]
    frame["note"] = [_quote_status(row, latest, now, trading) for row in snapshot.itertuples()]
    frame["intraday"] = [intraday_values(curves.get(row.ticker), now.date(), row.previous_close) for row in snapshot.itertuples()]
    for field in ["open", "high", "low", "turnover", "amplitude", "return_5", "return_20"]:
        frame[field] = frame["ticker"].map(lambda t: extras.get(t, {}).get(field, np.nan))
    for count in (5, 20):
        bases = frame["ticker"].map(lambda t: extras.get(t, {}).get(f"base_{count}", np.nan))
        frame[f"return_{count}"] = (pd.to_numeric(frame["price"], errors="coerce") / bases - 1) * 100
    frame["note"] = [" · ".join(filter(None, [note, extras.get(ticker, {}).get("note", "")])) for ticker, note in zip(frame["ticker"], frame["note"])]
    for field in ("amount", "market_cap"):
        frame[field] = pd.to_numeric(frame.get(field, pd.Series(np.nan, index=frame.index)), errors="coerce") / 1e8
    if query:
        needle = query.casefold()
        frame = frame.loc[frame["name"].str.casefold().str.contains(needle, regex=False) | frame["ticker"].str.casefold().str.contains(needle, regex=False)]
    field, ascending = WATCHLIST_SORTS.get(sort, WATCHLIST_SORTS["涨幅优先"])
    if valid_native_sort(native_sort):
        field, ascending = native_sort["field"], native_sort["ascending"]
    return frame.sort_values(["pinned", field], ascending=[False, ascending], kind="stable", na_position="last").reset_index(drop=True)


def _style_watchlist(frame):
    up, down = ("#c93636", "#15803d") if is_light_theme() else ("#ff7a85", "#53d49a")
    def tones(row):
        change = pd.to_numeric(row["change_pct"], errors="coerce")
        tone = up if pd.notna(change) and change > 0 else down if pd.notna(change) and change < 0 else ""
        return [f'color: {up if row[col] > 0 else down}' if col in {"return_5", "return_20"} and pd.notna(row[col]) and row[col] != 0 else
                f"color: {tone}" if col in {"price", "change_pct", "change"} and tone else
                "color: #b45309; font-weight: bold" if col == "note" and row[col] else "" for col in row.index]
    return frame.style.apply(tones, axis=1).format({"change_pct": _direction_number, "return_5": _direction_number, "return_20": _direction_number}, na_rep="—")


def _column_config():
    config = {c: st.column_config.TextColumn(label, width="medium") for c, label in WATCHLIST_COLUMNS.items()}
    for field in ("price", "change", "amount", "market_cap", "previous_close", "open", "high", "low", "turnover", "amplitude"):
        config[field] = st.column_config.NumberColumn(WATCHLIST_COLUMNS[field], format="%.2f", alignment="right")
    for field in ("change_pct", "return_5", "return_20"):
        # Styler supplies directional glyphs while the underlying values stay numeric for sorting.
        config[field] = st.column_config.NumberColumn(WATCHLIST_COLUMNS[field], alignment="right")
    config["name"] = st.column_config.TextColumn("股票", pinned=True, width="medium")
    config["ticker"] = st.column_config.TextColumn("代码", width="small")
    config["intraday"] = st.column_config.LineChartColumn("当天分时", width="medium", color="auto-inverse", help="当日分钟价格相对昨收；横轴压缩午休，空白表示尚无数据；折线红升绿降")
    config["note"] = st.column_config.TextColumn("异常提示", width="medium")
    for field in ("industry", "quote_time", "trade_date", "stale", "pe_ttm", "pinned", "added_order"):
        config[field] = None
    return config


def delete_watchlist_items(items, tickers):
    removed = [(i, dict(item)) for i, item in enumerate(items) if item["ticker"] in tickers]
    return [item for item in items if item["ticker"] not in tickers], removed


def restore_watchlist_items(items, removed):
    result = [dict(item) for item in items]
    for index, item in removed:
        if not any(current["ticker"] == item["ticker"] for current in result):
            result.insert(min(index, len(result)), item)
    return result


def _render_watchlist_management():
    with st.popover("管理自选", width="stretch"):
        items = load_watchlist()
        if not items:
            st.caption("先添加自选股，再管理置顶、标签与删除。")
            return
        editing = pd.DataFrame([{ "selected": False, "name": item["name"] or item["ticker"], "ticker": item["ticker"],
                                  "pinned": item.get("pinned", False), "tag": item.get("tag", "")} for item in items])
        revised = st.data_editor(editing, hide_index=True, width="stretch", key=f"watchlist-editor:{st.session_state.get('_watchlist_grid_revision', 0)}",
            disabled=["name", "ticker"], column_config={"selected": st.column_config.CheckboxColumn("选择", width="small"),
                "name": "股票", "ticker": "代码", "pinned": st.column_config.CheckboxColumn("置顶"),
                "tag": st.column_config.TextColumn("产业链标签", max_chars=80)}, num_rows="fixed")
        save, remove = st.columns(2)
        if save.button("保存置顶与标签", width="stretch"):
            updates = revised.set_index("ticker").to_dict("index")
            current = load_watchlist()
            for item in current:
                update = updates.get(item["ticker"])
                if update:
                    item.update(pinned=bool(update["pinned"]), tag=str(update["tag"] or "").strip()[:80])
            save_watchlist(current)
            st.toast("置顶与标签已保存")
            st.rerun(scope="fragment")
        selected = set(revised.loc[revised["selected"], "ticker"])
        if remove.button("删除所选", type="primary", disabled=not selected, width="stretch"):
            remaining, removed = delete_watchlist_items(load_watchlist(), selected)
            save_watchlist(remaining)
            st.session_state["_watchlist_undo"] = removed
            st.session_state["_watchlist_grid_revision"] = st.session_state.get("_watchlist_grid_revision", 0) + 1
            st.toast(f"已删除 {len(removed)} 只自选股，可撤销")
            st.rerun(scope="fragment")


def _watchlist_rows(items, universe):
    known = {ticker: (industry, name) for industry, stocks in universe.items() for name, ticker in stocks}
    names = st.session_state.get("a_share_live_names", {})
    return [{"ticker": item["ticker"], "name": item["name"] or names.get(item["ticker"], known.get(item["ticker"], ("", ""))[1]),
             "industry": known.get(item["ticker"], ("未分类", ""))[0]} for item in items]


def _render_watchlist_quotes(rows, universe):
    # Re-read local membership so fragment-only deletion/undo never uses stale row positions.
    items = load_watchlist()
    rows = _watchlist_rows(items, universe)
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    session = a_share_session_state(now)
    trading = session["trading"]
    automatic = st.session_state.get("watchlist_auto_refresh", False)
    identity = tuple(row["ticker"] for row in rows)
    previous = st.session_state.get("_watchlist_snapshot")
    with st.container(key="watchlist-toolbar"):
        title, action = st.columns([6, 1], vertical_alignment="center")
        heading = title.empty()
        manual = action.button("重试取数" if st.session_state.get("_watchlist_error") else "刷新行情", key="watchlist_refresh", width="stretch")
    if manual:
        load_watchlist_snapshot.clear()
        load_watchlist_extras.clear()
        load_watchlist_benchmark.clear()
        load_watchlist_status.clear()
        if not session["calendar_ok"]:
            load_a_share_trade_dates.clear()
    entering = st.session_state.pop("_watchlist_needs_refresh", False)
    due = automatic and trading and now.timestamp() - st.session_state.get("_watchlist_checked_at", 0) >= 60
    refresh = bool(rows) and (manual or entering or previous is None or previous[0] != identity or due)
    if refresh:
        st.session_state["_watchlist_checked_at"] = now.timestamp()
        heading.markdown("### 自选行情 · 正在取数…")
        try:
            with st.spinner("正在获取自选行情…"):
                snapshot = load_watchlist_snapshot(rows)
                st.session_state["_watchlist_snapshot"] = (identity, snapshot)
                st.session_state["_watchlist_refreshed"] = now.strftime("%H:%M:%S")
                st.session_state.pop("_watchlist_error", None)
        except MarketSnapshotError as error:
            st.session_state["_watchlist_error"] = f"取数失败：{error}"
            snapshot = previous[1].copy() if previous else pd.DataFrame()
            if not snapshot.empty:
                snapshot = snapshot.loc[snapshot["ticker"].isin(identity)].copy()
                snapshot["stale"] = True
                st.session_state["_watchlist_snapshot"] = (identity, snapshot)
    else:
        snapshot = previous[1].copy() if previous and rows else pd.DataFrame()
    if snapshot.empty or set(identity) - set(snapshot.get("ticker", [])):
        missing = set(identity) - set(snapshot.get("ticker", []))
        blanks = pd.DataFrame([row for row in rows if row["ticker"] in missing]).assign(price=np.nan, previous_close=np.nan,
            change_pct=np.nan, amount=np.nan, quote_time=None, trade_date=None, stale=True)
        snapshot = pd.concat([snapshot, blanks], ignore_index=True)
    if rows and (refresh or st.session_state.get("_watchlist_status_identity") != identity):
        st.session_state["_watchlist_trade_status"] = load_watchlist_status(identity)
        st.session_state["_watchlist_status_identity"] = identity
    trade_status = st.session_state.get("_watchlist_trade_status", {})
    snapshot["suspended"] = snapshot.get("ticker", pd.Series(dtype=str)).map(lambda t: "停牌" in trade_status.get("statuses", {}).get(t, ""))
    summary = summarize_watchlist(snapshot) if not snapshot.empty else {"date": None, "count": 0, "total": 0, "average": None, "up": 0, "down": 0, "flat": 0, "leader": None, "laggard": None}
    statuses = [_quote_status(row, summary["date"], now, trading) for row in snapshot.itertuples()]
    delayed = any(statuses)
    error = st.session_state.get("_watchlist_error")
    times = pd.to_datetime(snapshot.get("quote_time", pd.Series(dtype=str)), errors="coerce").dropna()
    quote_time = times.max().strftime("%H:%M") if len(times) else "—"
    mode = "自动刷新 · 每60秒" if automatic and trading else "自动刷新已暂停" if automatic else "手动刷新"
    status = "取数失败 · 保留上次行情" if error else "部分个股停牌 / 行情异常" if delayed else "行情已更新"
    heading.markdown(f'### 自选行情\n<span class="watch-meta">{html.escape(session["label"])} · {mode} · 最近交易日 {summary["date"] or "—"} · 行情 {quote_time} · {status}</span>', unsafe_allow_html=True)
    if error:
        st.warning(error + "。点击“重试取数”重试；账号权限或 token 问题请检查 iFinD 配置。")
    elif delayed:
        st.warning("部分个股停牌，或行情延迟、过期、缺失；原数据已保留，详情见行内提示。")
    if trade_status.get("error"):
        st.caption(trade_status["error"])
    if not session["calendar_ok"]:
        st.info(session["label"])
    if undo := st.session_state.get("_watchlist_undo"):
        if st.button(f"撤销删除（{len(undo)}只）", key="watchlist_undo"):
            save_watchlist(restore_watchlist_items(load_watchlist(), undo))
            st.session_state.pop("_watchlist_undo", None)
            st.session_state["_watchlist_grid_revision"] = st.session_state.get("_watchlist_grid_revision", 0) + 1
            st.toast("已恢复自选股")
            st.rerun(scope="fragment")
    _render_watchlist_management()
    if not rows:
        st.info("自选池还是空的。在上方搜索股票名称或输入 A 股代码，点击“加入自选”开始关注。")
        return
    columns = list(dict.fromkeys([*st.session_state.get("watchlist_columns", DEFAULT_COLUMNS), "name", "price", "change_pct"]))
    compact = st.session_state.get("_viewport_width", 1280) < 720
    visible = [c for c in columns if not compact or c not in {"intraday", "amount"}]
    if compact:
        visible = list(dict.fromkeys(["name", "price", "change_pct", *visible]))
    needs_curves = "intraday" in visible
    curves = st.session_state.get("_watchlist_intraday", {})
    if needs_curves and (refresh or st.session_state.get("_watchlist_curve_identity") != identity):
        for row in snapshot.itertuples():
            if str(row.trade_date or "")[:10] != str(now.date()) or row.stale:
                continue
            try:
                curves[row.ticker] = load_intraday(row.ticker, "CN")
            except DataFetchError:
                # Retain this day's last valid curve; old dates are filtered by intraday_values.
                pass
        st.session_state["_watchlist_intraday"] = curves
        st.session_state["_watchlist_curve_identity"] = identity
    extras_fields = tuple(sorted(set(visible) & {"turnover", "amplitude", "open", "high", "low", "return_5", "return_20"}))
    extras_key = (identity, summary["date"], extras_fields)
    if extras_fields and (refresh or st.session_state.get("_watchlist_extras_key") != extras_key):
        with st.spinner("正在获取选中列…"):
            st.session_state["_watchlist_extras"] = load_watchlist_extras(identity, summary["date"] or str(now.date()), extras_fields)
        st.session_state["_watchlist_extras_key"] = extras_key
    extras = st.session_state.get("_watchlist_extras", {}) if extras_fields else {}
    if refresh or "_watchlist_benchmark" not in st.session_state:
        st.session_state["_watchlist_benchmark"] = load_watchlist_benchmark(summary["date"] or str(now.date()))
    benchmark = st.session_state.get("_watchlist_benchmark", {})
    excess = summary["average"] - benchmark["change_pct"] if summary["average"] is not None and benchmark.get("change_pct") is not None and benchmark.get("date") == summary["date"] else None
    with st.container(key="watchlist-stats"):
        count, average, up, down, flat = st.columns([1, 1.6, 1, 1, 1], gap="small")
        count.metric("自选总数", summary["total"])
        if summary["count"] != summary["total"]:
            count.caption(f"有效 {summary['count']} / {summary['total']} · 有缺失")
        average.metric("等权平均涨跌幅", _quote_number(summary["average"], signed=True, suffix="%"),
                       delta=f"{excess:+.2f} 个百分点 vs 沪深300" if excess is not None else None, delta_color="inverse")
        if excess is None:
            average.caption("沪深300 同日基准暂不可用")
        for column, label, value, tone in [(up, "上涨", summary["up"], "up"), (down, "下跌", summary["down"], "down"), (flat, "平盘", summary["flat"], "flat")]:
            with column, st.container(key=f"watchlist-{tone}-metric"):
                st.metric(label, value)
    leaders = []
    for label, key in [("领涨", "leader"), ("领跌", "laggard")]:
        leader = summary[key]
        if leader is not None:
            leaders.append(f'<span class="watch-leader {_change_color(leader["change_pct"])}">{label} · {html.escape(leader["name"] or leader["ticker"])} {_direction_number(leader["change_pct"])}</span>')
    st.markdown('<div class="watch-leaders">' + ''.join(leaders) + '</div>', unsafe_allow_html=True)
    selected = st.session_state.get("watchlist_lookup") or ""
    try:
        query = normalize_ticker(selected) if selected else ""
    except ValueError:
        query = selected
    native_sort = st.session_state.get("watchlist_native_sort")
    table = build_watchlist_table(snapshot, items, curves, extras, now, trading, query, st.session_state.get("watchlist_sort", "涨幅优先"), native_sort)
    if table["note"].any():
        visible = [*visible, "note"]
    active_sort = f'{WATCHLIST_COLUMNS.get(native_sort["field"], native_sort["field"])} {"升序" if native_sort["ascending"] else "降序"}' if valid_native_sort(native_sort) else st.session_state.get("watchlist_sort", "涨幅优先")
    st.caption(f"当前排序：{active_sort} · 点选一行进入个股分析；表头可排序，工具栏可调整列宽与显隐。")
    if query:
        st.caption(f"筛选显示 {len(table)} / {len(rows)} 只")
    if table.empty:
        st.info("自选中没有匹配项。可点击上方“加入自选”，或清空搜索查看全部。")
    else:
        config = _column_config()
        if compact:
            config["name"] = st.column_config.TextColumn("股票", width=105, pinned=True)
            config["price"] = st.column_config.NumberColumn("最新价", width=80, format="%.2f", alignment="right")
            config["change_pct"] = st.column_config.NumberColumn("涨跌幅", width=100, alignment="right")
        config.update({field: None for field in WATCHLIST_COLUMNS if field not in visible})
        rendered = table.loc[:, visible]
        event = st.dataframe(_style_watchlist(rendered), column_order=visible, column_config=config, hide_index=True,
            width="stretch", height=min(560, 40 + len(table) * 38), row_height=38,
            key=f"watchlist-grid:{st.session_state.get('_watchlist_grid_revision', 0)}", on_select="rerun", selection_mode="single-row")
        if event.selection.rows:
            ticker = table.iloc[event.selection.rows[0]]["ticker"]
            open_watchlist_stock(ticker)
            st.session_state["_watchlist_grid_revision"] = st.session_state.get("_watchlist_grid_revision", 0) + 1
            st.rerun(scope="app")
    names = dict(st.session_state.get("a_share_live_names", {}))
    names.update({row.ticker: row.name for row in snapshot.itertuples() if row.name})
    st.session_state["a_share_live_names"] = names
    st.markdown(f'<div class="watch-footer">来源：{html.escape(snapshot.attrs.get("source", "同花顺 iFinD"))} · {"行情延迟或部分缺失" if delayed or error else "接口最新可用行情，非逐笔推送"} · 等权指标不代表持仓收益，仅供研究参考。</div>', unsafe_allow_html=True)
    st.session_state["_watchlist_column_labels"] = {label: field for field, label in WATCHLIST_COLUMNS.items()}
    save_browser_state(fragment=True)
    save_watchlist_preferences(st.session_state.get("watchlist_sort", "涨幅优先"), columns,
                              native_sort=st.session_state.get("watchlist_native_sort"))


def _reset_native_sort():
    st.session_state["watchlist_native_sort"] = None
    st.session_state["_watchlist_grid_revision"] = st.session_state.get("_watchlist_grid_revision", 0) + 1


def render_watchlist_overview(universe):
    load_styles("watchlist.css")
    preferences = load_watchlist_preferences()
    st.session_state.setdefault("watchlist_sort", preferences["sort"])
    st.session_state.setdefault("watchlist_columns", preferences["columns"])
    st.session_state.setdefault("watchlist_native_sort", preferences["native_sort"])
    if st.session_state["watchlist_sort"] not in WATCHLIST_SORTS:
        st.session_state["watchlist_sort"] = "涨幅优先"
    items = load_watchlist()
    known = {ticker: name for stocks in universe.values() for name, ticker in stocks}
    known.update({item["ticker"]: item["name"] or known.get(item["ticker"], item["ticker"]) for item in items})
    options = [f"{name} ({ticker})" for ticker, name in known.items()]
    with st.container(key="watchlist-page"):
        with st.container(key="watchlist-controls"):
            lookup, add, settings = st.columns([5, 1, 1.2], vertical_alignment="center")
            selected = lookup.selectbox("搜索或添加股票", options, index=None, accept_new_options=True,
                placeholder="搜索名称 / 代码，或输入新的 A 股代码", key="watchlist_lookup", label_visibility="collapsed")
            try:
                ticker = normalize_ticker(selected) if selected else None
            except ValueError:
                ticker = None
            saved = any(item["ticker"] == ticker for item in items)
            if add.button("已在自选" if saved else "加入自选", disabled=not ticker or saved, width="stretch"):
                save_watchlist(add_watchlist_item(items, ticker, known.get(ticker, "")))
                st.session_state["_watchlist_needs_refresh"] = True
                st.toast("已加入自选")
                items = load_watchlist()
            with settings.popover("列设置", width="stretch"):
                st.multiselect("显示列", list(WATCHLIST_COLUMNS), key="watchlist_columns", format_func=WATCHLIST_COLUMNS.get,
                    help="名称、最新价和涨跌幅始终保留；窄屏默认隐藏分时与成交额。近5/20日为不复权交易日收益。")
                st.selectbox("保存默认排序", list(WATCHLIST_SORTS), key="watchlist_sort", on_change=_reset_native_sort,
                    help="排序与列设置保存到本地；上次表头排序会在重新打开页面时恢复。")
        st.toggle("自动刷新（仅交易时段，每60秒）", value=False, key="watchlist_auto_refresh")
        save_watchlist_preferences(st.session_state["watchlist_sort"], st.session_state["watchlist_columns"], native_sort=st.session_state.get("watchlist_native_sort"))
        rows = _watchlist_rows(items, universe)
        st.fragment(run_every="60s" if st.session_state["watchlist_auto_refresh"] else None)(_render_watchlist_quotes)(rows, universe)
