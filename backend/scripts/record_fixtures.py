"""Record golden-sample upstream responses into backend/tests/fixtures/.

Run from repo root:  .venv\\Scripts\\python -m backend.scripts.record_fixtures [name ...]

Each sample is saved as raw bytes (no re-encoding, so GBK pages stay GBK) plus an
entry in manifest.json recording the request, HTTP status and capture time.
Request parameters mirror the legacy Streamlit modules so the ported parsers can be
checked against the same payloads (docs/plan-b-draft.md P0 / §9).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests
from curl_cffi.const import CurlHttpVersion

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
THIS_YEAR = datetime.now().year

THS_LINE = "https://d.10jqka.com.cn/v6/line/hs_{code}/01/{year}.js"
THS_TIME = "https://d.10jqka.com.cn/v6/time/hs_{code}/last.js"
EM_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_TRENDS = "https://push2.eastmoney.com/api/qt/stock/trends2/get"
EM_ULIST = "https://push2.eastmoney.com/api/qt/ulist.np/get"
EM_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_FUNDAMENTALS = "https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"


def _ths_headers(code: str, referer: str = "stockpage") -> dict:
    ref = f"https://stockpage.10jqka.com.cn/{code}/" if referer == "stockpage" else f"https://basic.10jqka.com.cn/{code}/"
    return {"User-Agent": "Mozilla/5.0", "Referer": ref}


# push2/push2his 在本机 HTTP/2 下会出现 TLS 握手失败（curl 35），用 HTTP/1.1 + Connection: close 稳定可用
EM_HEADERS = {"Referer": "https://quote.eastmoney.com/", "Connection": "close"}
EM_KLINE_FIELDS = {"fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58"}
EM_TRENDS_FIELDS = {
    "fields1": "f1,f2,f3,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f17",
    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
}
YAHOO_FUNDAMENTAL_TYPES = (
    "annualTotalRevenue,annualGrossProfit,annualOperatingIncome,annualNetIncome,annualBasicEPS,"
    "quarterlyTotalRevenue,quarterlyGrossProfit,quarterlyOperatingIncome,quarterlyNetIncome,quarterlyBasicEPS"
)

# name -> (filename, url, params, headers)
SAMPLES: dict[str, tuple[str, str, dict | None, dict | None]] = {
    # 同花顺
    "ths_daily_300308": (f"ths/daily_300308_{THIS_YEAR}.js", THS_LINE.format(code="300308", year=THIS_YEAR), None, _ths_headers("300308")),
    "ths_daily_920190": (f"ths/daily_920190_{THIS_YEAR}.js", THS_LINE.format(code="920190", year=THIS_YEAR), None, _ths_headers("920190")),
    "ths_intraday_300308": ("ths/intraday_300308.js", THS_TIME.format(code="300308"), None, _ths_headers("300308")),
    "ths_intraday_920190": ("ths/intraday_920190.js", THS_TIME.format(code="920190"), None, _ths_headers("920190")),
    "ths_index_daily_1A0001": (f"ths/index_daily_1A0001_{THIS_YEAR}.js", THS_LINE.format(code="1A0001", year=THIS_YEAR), None, _ths_headers("1A0001")),
    "ths_f10_desktop_300308": ("ths/f10_desktop_300308.html", "https://basic.10jqka.com.cn/300308/", None, _ths_headers("300308", "basic")),
    "ths_f10_mobile_300308": ("ths/f10_mobile_company_300308.html", "https://basic.10jqka.com.cn/mobile/300308/company.html", None, _ths_headers("300308", "basic")),
    "ths_finance_300308": ("ths/finance_300308.html", "https://basic.10jqka.com.cn/300308/finance.html", None, _ths_headers("300308", "basic")),
    "ths_cash_300308": (
        "ths/cash_300308.json",
        "https://basic.10jqka.com.cn/api/stock/finance/300308_cash.json",
        None,
        {"User-Agent": "Mozilla/5.0", "Referer": "https://basic.10jqka.com.cn/300308/finance.html"},
    ),
    # 东方财富
    "em_kline_300308": ("eastmoney/kline_0.300308.json", EM_KLINE,
                        {"secid": "0.300308", "klt": "101", "fqt": "1", "lmt": "120", "end": "20500101", **EM_KLINE_FIELDS}, EM_HEADERS),
    "em_kline_920190": ("eastmoney/kline_0.920190.json", EM_KLINE,
                        {"secid": "0.920190", "klt": "101", "fqt": "1", "lmt": "120", "end": "20500101", **EM_KLINE_FIELDS}, EM_HEADERS),
    "em_kline_index_000001": ("eastmoney/kline_1.000001.json", EM_KLINE,
                              {"secid": "1.000001", "klt": "101", "fqt": "1", "lmt": "120", "end": "20500101", **EM_KLINE_FIELDS}, EM_HEADERS),
    "em_trends_300308": ("eastmoney/trends_0.300308.json", EM_TRENDS,
                         {"secid": "0.300308", "ndays": "1", "iscr": "0", "iscca": "0", **EM_TRENDS_FIELDS}, EM_HEADERS),
    "em_ulist_snapshot": ("eastmoney/ulist_snapshot.json", EM_ULIST,
                          {"fltt": "2", "invt": "2", "fields": "f12,f14,f2,f18,f3,f6,f20,f115,f124,f297",
                           "secids": "0.300308,1.600519,0.000001,0.920190,1.688525"}, EM_HEADERS),
    "em_clist_breadth": ("eastmoney/clist_breadth_page1.json", EM_CLIST,
                         {"pn": 1, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": "f3",
                          "fs": "m:0+t:6,m:0+t:80", "fields": "f12,f3"}, EM_HEADERS),
    # Yahoo（直接录 chart / fundamentals JSON，新 Provider 将直接解析，不再经由 yfinance）
    "yahoo_daily_AAPL": ("yahoo/chart_daily_AAPL.json", YAHOO_CHART.format(symbol="AAPL"), {"range": "6mo", "interval": "1d"}, None),
    "yahoo_daily_005930.KS": ("yahoo/chart_daily_005930.KS.json", YAHOO_CHART.format(symbol="005930.KS"), {"range": "6mo", "interval": "1d"}, None),
    # 与旧代码一致：period=5d, interval=5m, 不含盘前盘后
    "yahoo_intraday_AAPL": ("yahoo/chart_5m_AAPL.json", YAHOO_CHART.format(symbol="AAPL"), {"range": "5d", "interval": "5m", "includePrePost": "false"}, None),
    "yahoo_intraday_005930.KS": ("yahoo/chart_5m_005930.KS.json", YAHOO_CHART.format(symbol="005930.KS"), {"range": "5d", "interval": "5m", "includePrePost": "false"}, None),
    "yahoo_fx_KRW": ("yahoo/chart_KRW=X.json", YAHOO_CHART.format(symbol="KRW=X"), {"range": "5d", "interval": "1d"}, None),
    "yahoo_fundamentals_AAPL": ("yahoo/fundamentals_AAPL.json", YAHOO_FUNDAMENTALS.format(symbol="AAPL"),
                                {"symbol": "AAPL", "type": YAHOO_FUNDAMENTAL_TYPES, "period1": "1577836800", "period2": "1924992000"}, None),
    # Stooq：2026-11-11 起 /q/d/l/ 返回 JS 工作量证明的人机校验页，不再直接给 CSV。
    # 不绕过校验，因此不录制；Stooq 回退在 P1 视为不可用（见 docs/plan-b-draft.md §4.1 备注）。
}


def _clear_broken_local_proxy() -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value = os.environ.get(name)
        if value:
            parsed = urlparse(value if "://" in value else f"http://{value}")
            if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
                os.environ.pop(name, None)


def record(names: list[str]) -> int:
    _clear_broken_local_proxy()
    manifest_path = FIXTURES / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    session = requests.Session(impersonate="chrome", trust_env=False)
    failures = 0
    for name in names:
        filename, url, params, headers = SAMPLES[name]
        try:
            extra = {"http_version": CurlHttpVersion.V1_1} if "eastmoney.com" in url else {}
            response = session.get(url, params=params, headers=headers, timeout=20, **extra)
            body = response.content
            ok = response.status_code == 200 and len(body) > 0
            if ok and b"/__verify" in body:
                print(f"FAIL {name}: upstream returned a bot-verification page (not recorded)")
                failures += 1
                continue
        except Exception as error:  # noqa: BLE001 - report and continue
            print(f"FAIL {name}: {type(error).__name__}: {error}")
            failures += 1
            continue
        if not ok:
            print(f"FAIL {name}: HTTP {response.status_code}, {len(body)} bytes")
            failures += 1
            continue
        path = FIXTURES / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        manifest[name] = {
            "file": filename,
            "url": url,
            "params": params,
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "bytes": len(body),
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        print(f"ok   {name}: {len(body)} bytes -> {filename}")
        time.sleep(0.3)
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return failures


if __name__ == "__main__":
    selected = sys.argv[1:] or list(SAMPLES)
    unknown = [name for name in selected if name not in SAMPLES]
    if unknown:
        sys.exit(f"unknown sample(s): {', '.join(unknown)}")
    sys.exit(1 if record(selected) else 0)
