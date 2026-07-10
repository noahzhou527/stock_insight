"""Aggregate recent finance headlines from Yahoo, Tonghuashun, and Douyin.

The public entry point deliberately returns source-level status alongside the
items.  A broken upstream therefore degrades one column of the news page
instead of making the whole page fail.
"""

from __future__ import annotations

import calendar
import html as html_lib
import json
import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from curl_cffi import requests

try:
    import feedparser
except ImportError:  # Keep the other two sources usable before deps are installed.
    feedparser = None


UTC = timezone.utc
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

YAHOO_RSS_URL = "https://finance.yahoo.com/rss/topstories"
THS_ROLLING_URL = "https://news.10jqka.com.cn/gdkx_list/"
THS_TODAY_URL = "https://news.10jqka.com.cn/today_list/index.shtml"
DOUYIN_BILLBOARD_URL = (
    "https://www.iesdouyin.com/share/billboard/?id=0&share_app_name=douyin"
)
# This unauthenticated JSON endpoint is the data source used by the public page.
DOUYIN_BILLBOARD_DATA_URL = (
    "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/"
)

CACHE_DIR = Path(__file__).resolve().parent / "data" / "cache"
NEWS_HISTORY_PATH = CACHE_DIR / "news_history.json"
CACHE_TTL = timedelta(minutes=10)
HISTORY_RETENTION = timedelta(hours=72)

SOURCE_QUOTAS = {"Yahoo": 3, "同花顺": 4, "抖音": 3}
SOURCE_ORDER = tuple(SOURCE_QUOTAS)

_HISTORY_LOCK = threading.RLock()
_HTTP_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

# Douyin is a general-interest list.  These terms intentionally include both
# instruments/macroeconomics and widely followed listed-company topics.
_FINANCE_KEYWORDS = (
    "a股",
    "股市",
    "股票",
    "证券",
    "基金",
    "债券",
    "期货",
    "外汇",
    "汇率",
    "人民币",
    "美元",
    "港股",
    "美股",
    "沪指",
    "深成指",
    "创业板",
    "科创板",
    "上证",
    "深证",
    "纳指",
    "标普",
    "道指",
    "央行",
    "利率",
    "降息",
    "加息",
    "降准",
    "货币",
    "通胀",
    "cpi",
    "pmi",
    "gdp",
    "经济",
    "财经",
    "金融",
    "银行",
    "保险",
    "黄金",
    "白银",
    "原油",
    "油价",
    "比特币",
    "加密货币",
    "关税",
    "贸易",
    "财政",
    "消费",
    "楼市",
    "房价",
    "地产",
    "市值",
    "ipo",
    "上市",
    "退市",
    "涨停",
    "跌停",
    "收盘",
    "开盘",
    "财报",
    "营收",
    "利润",
    "融资",
    "投资",
    "企业",
    "商业",
    "就业",
    "收入",
    "税收",
    "碳达峰",
    "小米",
    "腾讯",
    "阿里",
    "京东",
    "茅台",
    "比亚迪",
    "宁德时代",
    "英伟达",
    "特斯拉",
    "苹果公司",
    "华为",
    "雷军",
    "马斯克",
)


@dataclass(frozen=True, slots=True)
class NewsItem:
    """One link in the combined finance-news timeline."""

    title: str
    url: str
    source: str
    published_at: datetime | None
    observed_at: datetime | None

    @property
    def effective_time(self) -> datetime:
        """Timestamp used for filtering and ordering.

        Yahoo and Tonghuashun supply publication times.  Douyin does not, so
        its first locally observed time is the only honest timestamp available.
        """

        value = self.published_at or self.observed_at
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        return _aware(value)

    def to_record(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": _iso_or_none(self.published_at),
            "observed_at": _iso_or_none(self.observed_at),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "NewsItem":
        return cls(
            title=str(record["title"]).strip(),
            url=str(record["url"]).strip(),
            source=str(record["source"]).strip(),
            published_at=_parse_iso(record.get("published_at")),
            observed_at=_parse_iso(record.get("observed_at")),
        )


def fetch_recent_financial_news(
    hours: int | float = 72,
) -> tuple[list[NewsItem], dict[str, str]]:
    """Return a quota-limited news timeline and display-ready source statuses.

    At most 72 hours are retained locally.  Requests made again within ten
    minutes reuse the persisted aggregate.  Every source is fetched and caught
    independently; on failure, that source's recent history is retained.
    """

    try:
        requested_hours = float(hours)
    except (TypeError, ValueError) as error:
        raise ValueError("hours must be a positive number") from error
    if requested_hours <= 0:
        raise ValueError("hours must be a positive number")
    requested_hours = min(requested_hours, HISTORY_RETENTION.total_seconds() / 3600)

    now = datetime.now(UTC)
    with _HISTORY_LOCK:
        cache = _load_history_document()
        cached_items = _items_from_document(cache)
        last_attempt = _parse_iso(cache.get("last_attempt_at"))
        if last_attempt is not None:
            age = now - _aware(last_attempt)
            if timedelta(0) <= age < CACHE_TTL:
                selected = _select_for_display(cached_items, requested_hours, now)
                cached_at = last_attempt.astimezone(SHANGHAI_TZ).strftime("%H:%M")
                persisted = cache.get("source_status") or {}
                statuses: dict[str, str] = {}
                for source in SOURCE_ORDER:
                    previous = str(persisted.get(source, "")).strip()
                    current_count = _count_label(selected, source)
                    if previous:
                        previous, replacements = re.subn(
                            r"\d+\s*/\s*\d+\s*条", current_count, previous, count=1
                        )
                        if not replacements:
                            previous = f"{previous} · {current_count}"
                    else:
                        previous = current_count
                    statuses[source] = f"缓存 {cached_at} · {previous}"
                return selected, statuses

    live_by_source: dict[str, list[NewsItem]] = {source: [] for source in SOURCE_ORDER}
    fetch_notes: dict[str, str] = {}
    errors: dict[str, str] = {}
    retention_cutoff = now - HISTORY_RETENTION

    _clear_broken_local_proxy()
    session = requests.Session(impersonate="chrome", trust_env=False)
    try:
        fetchers = {
            "Yahoo": lambda: (_fetch_yahoo(session, now, retention_cutoff), "RSS"),
            "同花顺": lambda: _fetch_tonghuashun(session, now, retention_cutoff),
            "抖音": lambda: (_fetch_douyin(session, now), "公开热榜"),
        }
        for source in SOURCE_ORDER:
            try:
                items, note = fetchers[source]()
                live_by_source[source] = _deduplicate(items)
                fetch_notes[source] = note
            except Exception as error:  # One provider must never break the others.
                errors[source] = _brief_error(error)
    finally:
        try:
            session.close()
        except Exception:
            pass

    # Re-read under the lock so concurrent sessions do not overwrite headlines
    # observed by each other while network requests were in flight.
    with _HISTORY_LOCK:
        latest = _load_history_document()
        history = _items_from_document(latest)
        merged = _merge_with_history(history, live_by_source, now)
        selected = _select_for_display(merged, requested_hours, now)

        statuses: dict[str, str] = {}
        for source, quota in SOURCE_QUOTAS.items():
            count = sum(item.source == source for item in selected)
            if source in errors:
                mode = "缓存" if count else "不可用"
                statuses[source] = f"{mode} · {count}/{quota} 条（{errors[source]}）"
            elif live_by_source[source]:
                statuses[source] = f"{fetch_notes[source]} · {count}/{quota} 条"
            elif count:
                statuses[source] = (
                    f"历史 · {count}/{quota} 条（{fetch_notes[source]}本次无新增）"
                )
            else:
                statuses[source] = (
                    f"{fetch_notes[source]} · 0/{quota} 条（当前无符合条件内容）"
                )

        _save_history_document(
            {
                "version": 1,
                "updated_at": now.isoformat(),
                "last_attempt_at": now.isoformat(),
                "source_status": statuses,
                "items": [item.to_record() for item in merged],
            }
        )

    return selected, statuses


def _fetch_yahoo(
    session: requests.Session, now: datetime, cutoff: datetime
) -> list[NewsItem]:
    response = _get(session, YAHOO_RSS_URL)
    items = _parse_yahoo_rss(response.content, now)
    recent = _recent_items(items, cutoff)
    if not recent:
        raise ValueError("RSS 中没有最近 72 小时的内容")
    return recent


def _parse_yahoo_rss(payload: bytes | str, observed_at: datetime) -> list[NewsItem]:
    if feedparser is None:
        raise RuntimeError("缺少 feedparser 依赖")

    feed = feedparser.parse(payload)
    entries = list(getattr(feed, "entries", ()) or ())
    if not entries:
        detail = getattr(feed, "bozo_exception", None)
        raise ValueError(f"RSS 无有效条目{f': {detail}' if detail else ''}")

    result: list[NewsItem] = []
    for entry in entries:
        title = _clean_title(entry.get("title", ""))
        url = _safe_url(entry.get("link", ""))
        published = _feed_datetime(entry)
        if not title or not url or published is None:
            continue
        result.append(
            NewsItem(
                title=title,
                url=url,
                source="Yahoo",
                published_at=published,
                observed_at=observed_at,
            )
        )
    return _deduplicate(result)


def _feed_datetime(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)
        except (TypeError, ValueError, OverflowError):
            pass

    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            return _aware(parsedate_to_datetime(str(raw)))
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def _fetch_tonghuashun(
    session: requests.Session, now: datetime, cutoff: datetime
) -> tuple[list[NewsItem], str]:
    primary_error: Exception | None = None
    try:
        response = _get(session, THS_ROLLING_URL)
        primary_items = _recent_items(
            _parse_tonghuashun_html(
                _decode_response(response), THS_ROLLING_URL, now
            ),
            cutoff,
        )
        if primary_items:
            return primary_items, "7×24"
        primary_error = ValueError("7×24 页面没有近期内容")
    except Exception as error:
        primary_error = error

    try:
        response = _get(session, THS_TODAY_URL)
        fallback_items = _recent_items(
            _parse_tonghuashun_html(
                _decode_response(response), THS_TODAY_URL, now
            ),
            cutoff,
        )
        if not fallback_items:
            raise ValueError("财经要闻页面没有近期内容")
        return fallback_items, "财经要闻回退"
    except Exception as fallback_error:
        raise RuntimeError(
            f"7×24 与财经要闻均不可用：{_brief_error(primary_error)}；"
            f"{_brief_error(fallback_error)}"
        ) from fallback_error


def _parse_tonghuashun_html(
    html: str, base_url: str, observed_at: datetime
) -> list[NewsItem]:
    soup = BeautifulSoup(html, "html.parser")
    result: list[NewsItem] = []

    # Both the rolling and today's-news pages currently use this compact block.
    for block in soup.select(".arc-title"):
        anchor = block.select_one("a[href]")
        if anchor is None:
            continue
        title = _clean_title(anchor.get("title") or anchor.get_text(" ", strip=True))
        url = _safe_url(urljoin(base_url, anchor.get("href", "")))
        time_text = block.get_text(" ", strip=True)
        published = _parse_ths_datetime(time_text, url, observed_at)
        if title and url and published is not None:
            result.append(
                NewsItem(title, url, "同花顺", published, observed_at)
            )

    # A loose fallback makes fixture changes and minor upstream class renames
    # survivable without accidentally treating the global navigation as news.
    if not result:
        for anchor in soup.select("a[href]"):
            href = urljoin(base_url, anchor.get("href", ""))
            parsed_url = urlparse(href)
            if "10jqka.com.cn" not in parsed_url.netloc:
                continue
            title = _clean_title(anchor.get("title") or anchor.get_text(" ", strip=True))
            if len(title) < 6:
                continue
            parent_text = anchor.parent.get_text(" ", strip=True) if anchor.parent else title
            published = _parse_ths_datetime(parent_text, href, observed_at)
            url = _safe_url(href)
            if published is not None and url:
                result.append(
                    NewsItem(title, url, "同花顺", published, observed_at)
                )

    return _deduplicate(result)


def _parse_ths_datetime(
    text: str, url: str, reference_time: datetime
) -> datetime | None:
    reference = _aware(reference_time).astimezone(SHANGHAI_TZ)
    time_match = re.search(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text)
    if time_match is None:
        return None
    hour, minute = (int(value) for value in time_match.groups())

    url_date = re.search(r"/((?:19|20)\d{2})(\d{2})(\d{2})(?:/|[a-z])", url)
    text_date = re.search(
        r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", text
    )
    try:
        if url_date:
            year, month, day = (int(value) for value in url_date.groups())
            return datetime(year, month, day, hour, minute, tzinfo=SHANGHAI_TZ)
        if text_date:
            raw_year, raw_month, raw_day = text_date.groups()
            year = int(raw_year) if raw_year else reference.year
            candidate = datetime(
                year, int(raw_month), int(raw_day), hour, minute, tzinfo=SHANGHAI_TZ
            )
            if raw_year is None and candidate > reference + timedelta(days=1):
                candidate = candidate.replace(year=year - 1)
            return candidate
        if "今天" in text or "今日" in text:
            return reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    return None


def _fetch_douyin(session: requests.Session, observed_at: datetime) -> list[NewsItem]:
    api_error: Exception | None = None
    try:
        response = _get(
            session,
            DOUYIN_BILLBOARD_DATA_URL,
            referer=DOUYIN_BILLBOARD_URL,
        )
        payload = response.json()
        return _parse_douyin_payload(payload, observed_at)
    except Exception as error:
        api_error = error

    # Some deployments expose the rendered list directly in the public HTML.
    try:
        response = _get(session, DOUYIN_BILLBOARD_URL)
        items = _parse_douyin_html(_decode_response(response), observed_at)
        if not items:
            raise ValueError("公开页面中没有可解析的财经热点")
        return items
    except Exception as page_error:
        raise RuntimeError(
            f"公开热榜不可用：{_brief_error(api_error)}；{_brief_error(page_error)}"
        ) from page_error


def _parse_douyin_payload(
    payload: dict[str, Any] | str, observed_at: datetime
) -> list[NewsItem]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("热榜响应不是 JSON 对象")
    if payload.get("status_code") not in (None, 0):
        raise ValueError(f"热榜状态码 {payload.get('status_code')}")

    rows = payload.get("word_list")
    if rows is None and isinstance(payload.get("data"), dict):
        rows = payload["data"].get("word_list")
    if not isinstance(rows, list):
        raise ValueError("热榜响应缺少 word_list")

    result: list[NewsItem] = []
    for row in rows:
        if isinstance(row, str):
            title = _clean_title(row)
        elif isinstance(row, dict):
            title = _clean_title(
                row.get("word") or row.get("sentence") or row.get("title") or ""
            )
        else:
            continue
        if not title or not _is_financial_title(title):
            continue
        result.append(
            NewsItem(
                title=title,
                url=f"https://www.douyin.com/search/{quote(title, safe='')}",
                source="抖音",
                published_at=None,
                observed_at=observed_at,
            )
        )
    return _deduplicate(result)


def _parse_douyin_html(html: str, observed_at: datetime) -> list[NewsItem]:
    # First handle pages that embed the public endpoint's JSON structure.
    decoder = json.JSONDecoder()
    for match in re.finditer(r'["\']word_list["\']\s*:\s*', html):
        try:
            rows, _ = decoder.raw_decode(html[match.end() :])
            return _parse_douyin_payload({"word_list": rows}, observed_at)
        except (json.JSONDecodeError, ValueError):
            continue

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, str]] = []
    for anchor in soup.select("a[href]"):
        title = _clean_title(anchor.get("title") or anchor.get_text(" ", strip=True))
        if _is_financial_title(title):
            candidates.append((title, urljoin(DOUYIN_BILLBOARD_URL, anchor["href"])))

    # Text-only server-rendered variants often expose rank/title/heat on three
    # consecutive lines.  Extract the title immediately after each rank.
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    for index, line in enumerate(lines[:-1]):
        if re.fullmatch(r"\d{1,3}[.、]?", line):
            title = _clean_title(lines[index + 1])
            if _is_financial_title(title):
                candidates.append(
                    (title, f"https://www.douyin.com/search/{quote(title, safe='')}")
                )

    return _deduplicate(
        NewsItem(
            title=title,
            url=_safe_url(url)
            or f"https://www.douyin.com/search/{quote(title, safe='')}",
            source="抖音",
            published_at=None,
            observed_at=observed_at,
        )
        for title, url in candidates
    )


def _merge_with_history(
    history: Iterable[NewsItem],
    live_by_source: dict[str, list[NewsItem]],
    now: datetime,
) -> list[NewsItem]:
    cutoff = now - HISTORY_RETENTION
    merged: dict[tuple[str, str], NewsItem] = {}

    for item in _recent_items(history, cutoff):
        if item.source in SOURCE_QUOTAS:
            merged[(item.source, _title_key(item.title))] = item

    for source in SOURCE_ORDER:
        for item in live_by_source.get(source, ()):  # Preserve Douyin list order.
            key = (source, _title_key(item.title))
            previous = merged.get(key)
            if previous is None:
                merged[key] = item
                continue

            observed_candidates = [
                stamp for stamp in (previous.observed_at, item.observed_at) if stamp
            ]
            first_observed = (
                min(observed_candidates, key=_aware) if observed_candidates else None
            )
            merged[key] = NewsItem(
                title=item.title,
                url=item.url or previous.url,
                source=source,
                published_at=item.published_at or previous.published_at,
                observed_at=first_observed,
            )

    return sorted(merged.values(), key=lambda item: item.effective_time, reverse=True)


def _select_for_display(
    items: Iterable[NewsItem], hours: float, now: datetime
) -> list[NewsItem]:
    cutoff = now - timedelta(hours=hours)
    per_source: list[NewsItem] = []
    for source, quota in SOURCE_QUOTAS.items():
        source_items = _deduplicate(
            item
            for item in items
            if item.source == source and item.effective_time >= cutoff
        )
        source_items.sort(key=lambda item: item.effective_time, reverse=True)
        per_source.extend(source_items[:quota])

    # Cross-source duplicate headlines are removed after applying source quotas,
    # matching the product rule that each provider is first capped independently.
    result: list[NewsItem] = []
    seen_titles: set[str] = set()
    for item in sorted(per_source, key=lambda item: item.effective_time, reverse=True):
        key = _title_key(item.title)
        if not key or key in seen_titles:
            continue
        seen_titles.add(key)
        result.append(item)
    return result


def _deduplicate(items: Iterable[NewsItem]) -> list[NewsItem]:
    result: list[NewsItem] = []
    seen: set[str] = set()
    for item in items:
        key = _title_key(item.title)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _recent_items(items: Iterable[NewsItem], cutoff: datetime) -> list[NewsItem]:
    aware_cutoff = _aware(cutoff)
    return [item for item in items if item.effective_time >= aware_cutoff]


def _items_from_document(document: dict[str, Any]) -> list[NewsItem]:
    result: list[NewsItem] = []
    for record in document.get("items", ()):
        if not isinstance(record, dict):
            continue
        try:
            item = NewsItem.from_record(record)
        except (KeyError, TypeError, ValueError):
            continue
        if item.source in SOURCE_QUOTAS and item.title and item.url:
            result.append(item)
    return result


def _load_history_document() -> dict[str, Any]:
    if not NEWS_HISTORY_PATH.exists():
        return {}
    try:
        value = json.loads(NEWS_HISTORY_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _save_history_document(document: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = NEWS_HISTORY_PATH.with_name(
        f".{NEWS_HISTORY_PATH.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, NEWS_HISTORY_PATH)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _get(
    session: requests.Session, url: str, referer: str | None = None
) -> requests.Response:
    headers = dict(_HTTP_HEADERS)
    if referer:
        headers["Referer"] = referer
    response = session.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return response


def _decode_response(response: requests.Response) -> str:
    content = response.content
    content_type = response.headers.get("content-type", "")
    match = re.search(r"charset\s*=\s*[\"']?([\w.-]+)", content_type, re.I)
    if match is None:
        match = re.search(br"charset\s*=\s*[\"']?([\w.-]+)", content[:4096], re.I)
        encoding = match.group(1).decode("ascii", "ignore") if match else None
    else:
        encoding = match.group(1)
    if encoding and encoding.lower().replace("-", "") in {"gbk", "gb2312"}:
        encoding = "gb18030"

    for candidate in (encoding, "utf-8", "gb18030"):
        if not candidate:
            continue
        try:
            return content.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def _clear_broken_local_proxy() -> None:
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        value = os.environ.get(name)
        if not value:
            continue
        parsed = urlparse(value if "://" in value else f"http://{value}")
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
            os.environ.pop(name, None)


def _is_financial_title(title: str) -> bool:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    return bool(normalized) and any(word in normalized for word in _FINANCE_KEYWORDS)


def _clean_title(value: Any) -> str:
    text = BeautifulSoup(html_lib.unescape(str(value or "")), "html.parser").get_text(
        " ", strip=True
    )
    return re.sub(r"\s+", " ", text).strip()


def _title_key(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    return re.sub(r"[^\w\u3400-\u9fff]+", "", normalized, flags=re.UNICODE)


def _safe_url(value: Any) -> str:
    url = html_lib.unescape(str(value or "")).strip()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.scheme.lower() == "http" and parsed.hostname and parsed.hostname.endswith(
        ".10jqka.com.cn"
    ):
        url = "https://" + url[len("http://") :]
    return url


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _aware(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError):
        return None


def _iso_or_none(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def _brief_error(error: Exception | None) -> str:
    if error is None:
        return "未知错误"
    message = re.sub(r"\s+", " ", str(error)).strip() or type(error).__name__
    return message[:96] + ("…" if len(message) > 96 else "")


def _count_label(items: Iterable[NewsItem], source: str) -> str:
    quota = SOURCE_QUOTAS[source]
    count = sum(item.source == source for item in items)
    return f"{count}/{quota} 条"


__all__ = [
    "NewsItem",
    "SOURCE_QUOTAS",
    "fetch_recent_financial_news",
]
