"""Ticker parsing for search and watchlist (ported from watchlist.normalize_ticker, extended to US/KR)."""
from __future__ import annotations

import re

from ..providers.base import Instrument

_A_SHARE = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")
_KR = re.compile(r"^(\d{6})[._-]?(KS|KQ)$")
_US = re.compile(r"^\^?[A-Z][A-Z0-9]{0,5}(?:[.\-][A-Z0-9]{1,2})?$")


class TickerFormatError(ValueError):
    pass


def _clean(value: str) -> str:
    return re.sub(r"\s+", "", str(value).upper()).replace("。", ".").replace("．", ".")


def normalize_a_share(ticker: str) -> str:
    """``300308`` / ``SZ300308`` / ``300308sz`` / ``中际旭创(300308)`` → ``300308.SZ``."""
    value = _clean(ticker)
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
    if not _A_SHARE.fullmatch(value):
        raise TickerFormatError("A股代码格式不正确，例如：300308 或 300308.SZ。")
    return value


def parse_any(ticker: str) -> Instrument:
    """Resolve any supported code form to an (unverified) instrument."""
    value = _clean(ticker)
    if not value:
        raise TickerFormatError("请输入股票代码。")
    if m := _KR.fullmatch(value):
        return Instrument("KR", f"{m.group(1)}.{m.group(2)}")
    try:
        return Instrument("CN", normalize_a_share(value))
    except TickerFormatError:
        pass
    if _US.fullmatch(value) and not value.isdigit():
        return Instrument("US", value)
    raise TickerFormatError("无法识别的代码，例如：300308、300308.SZ、AAPL、005930.KS。")
