import asyncio
import html
import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, date, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import aiohttp
import requests
from storage import atomic_json
from calendar_feed import publish_calendars

KST = timezone(timedelta(hours=9))

ROOT = pathlib.Path(__file__).parent.parent

COMMON_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

SCHED_HEADERS = {
    "User-Agent": COMMON_UA,
    "Accept": "application/json",
    "Referer": "https://artist.mnetplus.world/",
}

API_BASE = "https://artist.mnetplus.world/svc/stg/rescene-official/space/api/v1/calendar"


def build_params(year: int, month: int) -> dict:
    start_kst = datetime(year, month, 1, 0, 0, 0)
    start_utc = start_kst - timedelta(hours=9)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    end_kst = datetime(last_day.year, last_day.month, last_day.day, 23, 59, 59)
    end_utc = end_kst - timedelta(hours=9)
    return {
        "startAt":          start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "startAtForAllDay": f"{year}-{month:02d}-01",
        "endAt":            end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endAtForAllDay":   f"{last_day.year}-{last_day.month:02d}-{last_day.day:02d}",
    }


def event_datetime(ev):
    raw = ev.get("startAt", "")
    if not raw:
        raise ValueError("Missing event timestamp")
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST)


def extract_date(ev):
    if ev.get("allDay"):
        return date.fromisoformat(str(ev.get("startAtAllDay", ""))[:10]).isoformat()
    return event_datetime(ev).date().isoformat()


def extract_time(ev):
    return "" if ev.get("allDay") else event_datetime(ev).strftime("%H:%M")


LABEL_MAP = {
    "공연":    "concert",
    "팬사인회": "fansign",
    "음방":    "broadcast",
    "방송":    "broadcast",
    "예능":    "broadcast",
    "라디오":  "radio",
    "행사":    "event",
    "기념일":  "anniv",
    "공지":    "notice",
}

TYPE_KEYWORDS = {
    "broadcast": ["음방", "음악방송", "inkigayo", "인기가요", "뮤직뱅크", "music bank",
                  "show champion", "엠카운트다운", "mcountdown", "the show",
                  "방송", "출연", "인터뷰", "interview", "예능", "버라이어티", "variety", "웹예능"],
    "radio":     ["라디오", "radio"],
    "concert":   ["콘서트", "concert", "showcase", "쇼케이스", "팬미팅", "fanmeeting",
                  "공연", "페스티벌", "festival", "kcon"],
    "fansign":   ["팬사인", "fansign", "사인회", "팬이벤트", "영상통화"],
    "event":     ["행사", "이벤트", "event"],
    "notice":    ["공지", "안내", "notice"],
}


def classify_type(ev: dict) -> str:
    label_name = (ev.get("label") or {}).get("name", "")
    if label_name in LABEL_MAP:
        return LABEL_MAP[label_name]
    tl = ev.get("title", "").lower()
    for t, kws in TYPE_KEYWORDS.items():
        if any(k in tl for k in kws):
            return t
    return "notice"


def crawl_schedule_month(year: int, month: int) -> list:
    params = build_params(year, month)
    try:
        resp = requests.get(API_BASE, headers=SCHED_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[MnetPlus] {year}/{month:02d} API 오류: {e}", file=sys.stderr)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return None
    events = []
    for ev in data.get("events", []):
        try:
            d = extract_date(ev)
        except (ValueError, TypeError, AttributeError):
            return None
        title = ev.get("title", "").strip()
        if not d or not title:
            return None
        label_name = (ev.get("label") or {}).get("name", "")
        if label_name == "기념일":
            continue
        events.append({
            "id": str(ev.get("id", "")),
            "date":   d,
            "time":   extract_time(ev),
            "title":  title,
            "detail": "",
            "type":   classify_type(ev),
            "source": "mnetplus",
        })
    print(f"[MnetPlus] {year}/{month:02d} → {len(events)}개", file=sys.stderr)
    return events


BLIP_URL = "https://blip.kr/artists/RESCENE/schedule"
BLIP_UNIT_ID = 133


def parse_blip_page(page, year, month):
    chunks = []
    for script in re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.S | re.I):
        match = re.fullmatch(r"\s*self\.__next_f\.push\((.*)\)\s*;?\s*", script, re.S)
        if not match:
            continue
        value = json.loads(match.group(1))
        if isinstance(value, list) and len(value) == 2 and value[0] == 1 and isinstance(value[1], str):
            chunks.append(value[1])
    matches = []

    def visit(value):
        if isinstance(value, dict):
            if value.get("queryKey") == ["schedule", year, month, BLIP_UNIT_ID]:
                state = value.get("state", {})
                if state.get("status") != "success" or not isinstance(state.get("data"), list):
                    raise ValueError("Invalid blip schedule query")
                matches.append(state["data"])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for line in "".join(chunks).splitlines():
        if ":" not in line:
            continue
        try:
            value = json.loads(line.split(":", 1)[1])
        except json.JSONDecodeError:
            continue
        visit(value)
    if not matches or any(value != matches[0] for value in matches[1:]):
        raise ValueError("Missing or inconsistent blip schedule query")
    return normalize_blip_events(matches[0], year, month)


def normalize_blip_events(records, year, month):
    first = date(year, month, 1)
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    events = {}
    for record in records:
        if not isinstance(record, dict) or record.get("unitId") != BLIP_UNIT_ID:
            raise ValueError("Invalid blip artist")
        ident, title = record.get("scheduleId"), record.get("title")
        if type(ident) is not int or ident <= 0 or not isinstance(title, str) or not title.strip():
            raise ValueError("Invalid blip event")
        start = datetime.fromisoformat(str(record.get("startTime", "")).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(record.get("endTime") or record.get("startTime", "")).replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError("Invalid blip event time")
        start, end = start.astimezone(KST), end.astimezone(KST)
        allday = record.get("isAllday")
        if not isinstance(allday, bool):
            raise ValueError("Invalid blip all-day value")
        title = title.strip()
        if title.startswith("<") and title.endswith(">"):
            title = title[1:-1].strip()
        if not title:
            raise ValueError("Empty blip title")
        field = record.get("extField") or {}
        location = str(field.get("value") or "") if isinstance(field, dict) and field.get("key") == "장소" else ""
        id_hash = record.get("idHash", "")
        link = "https://s.blip.kr/s/" + id_hash if isinstance(id_hash, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", id_hash) else BLIP_URL + "?unitId=133"
        period = f"{start:%Y.%m.%d} – {end:%Y.%m.%d}" if start.date() != end.date() else ""
        kind = classify_type({"title": title})
        if kind == "notice":
            kind = {1: "broadcast", 2: "anniv", 4: "event", 5: "event"}.get(record.get("typeId"), "notice")
        day = max(first, start.date())
        while day <= min(last, end.date()):
            event = {
                "id": str(ident), "date": day.isoformat(),
                "time": start.strftime("%H:%M") if not allday and day == start.date() else "",
                "title": title, "detail": " · ".join(filter(None, [period, location])),
                "type": kind, "source": "blip", "link": link,
                "location": location, "allDay": allday,
                "start": start.isoformat(), "end": end.isoformat(),
                "endTimeHidden": bool(record.get("isEndTimeHidden")),
            }
            key = (event["id"], event["date"])
            if key in events and events[key] != event:
                raise ValueError("Conflicting blip event ID")
            events[key] = event
            day += timedelta(days=1)
    return list(events.values())


def crawl_blip_month(year, month):
    try:
        response = requests.get(BLIP_URL, params={"unitId": BLIP_UNIT_ID, "year": year, "month": month},
                                headers={"User-Agent": COMMON_UA, "Accept": "text/html"}, timeout=25)
        response.raise_for_status()
        if len(response.content) > 8 * 1024 * 1024:
            raise ValueError("Oversized blip page")
        events = parse_blip_page(response.text, year, month)
        print(f"[blip] {year}/{month:02d} → {len(events)}개 날짜별 일정", file=sys.stderr)
        return events
    except (requests.RequestException, ValueError, TypeError, KeyError, OverflowError) as error:
        print(f"[blip] {year}/{month:02d} 수집 실패 ({type(error).__name__})", file=sys.stderr)
        return None


def schedule_months(today, offsets):
    for offset in offsets:
        year, month = divmod(today.year * 12 + today.month - 1 + offset, 12)
        yield year, month + 1


def half_key(date_str: str) -> tuple[int, int]:

    year  = int(date_str[0:4])
    month = int(date_str[5:7])
    half  = 1 if month <= 6 else 2
    return year, half


def schedule_json_path(year: int, half: int) -> pathlib.Path:
    return ROOT / "data" / "schedule" / f"schedule_{year}_h{half}.json"


def _load_half_schedule(year: int, half: int) -> list:
    path = schedule_json_path(year, half)
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events")
        if not isinstance(events, list) or any(not isinstance(ev, dict) or not isinstance(ev.get("date"), str) or not isinstance(ev.get("title"), str) for ev in events):
            raise ValueError("Invalid stored schedules")
        return events
    except Exception as e:
        print(f"[스케줄] {path.name} 읽기 실패: {e}", file=sys.stderr)
        raise ValueError("Invalid existing schedule; refusing to overwrite") from e


def run_schedule_crawler():
    today = datetime.now(KST).date()
    result = {}
    sources = [("mnetplus", crawl_schedule_month, [0, 1]), ("blip", crawl_blip_month, [-1, 0, 1, 2])]
    for source, crawler, offsets in sources:
        for year, month in schedule_months(today, offsets):
            events = crawler(year, month)
            if events is None:
                print(f"::warning::{source} {year}-{month:02d} failed; keeping previous data", file=sys.stderr)
                continue
            prefix = f"{year}-{month:02d}"
            hk = (year, 1 if month <= 6 else 2)
            existing = result.get(hk)
            if existing is None:
                existing = _load_half_schedule(*hk)
            kept = [ev for ev in existing if not (ev.get("source") == source and ev.get("date", "").startswith(prefix))]
            seen = set()
            merged = []
            for ev in kept + [ev for ev in events if ev["date"].startswith(prefix)]:
                key = (ev.get("source", ""), ev.get("id") or "", ev["date"], ev.get("time", ""), ev["title"])
                if key not in seen:
                    seen.add(key)
                    merged.append(ev)
            result[hk] = sorted(merged, key=lambda ev: (ev["date"], ev.get("time", ""), ev.get("source", ""), ev["title"]))
    return result


NAVER_CLIENT_ID     = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

NAVER_HEADERS = {
    "X-Naver-Client-Id":     NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    "User-Agent": COMMON_UA,
}

FETCH_HEADERS = {
    "User-Agent": COMMON_UA,
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://search.naver.com/",
}

TITLE_KEYWORDS = ["리센느", "rescene"]
SEARCH_QUERIES = ["리센느", "RESCENE"]
DISPLAY        = 40
MAX_ARTICLES   = 25
THUMB_TIMEOUT  = 12
THUMB_CONCUR   = 6


def parse_pub_date(raw: str) -> str:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(KST).strftime("%Y.%m.%d")
    except Exception:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return datetime.now(timezone.utc).strftime("%Y.%m.%d")


def clean_text(t: str) -> str:
    t = html.unescape(t)
    t = re.sub(r"<[^>]+>", "", t)
    return t.strip()


def title_matches(title: str) -> bool:
    tl = title.lower()
    return any(kw.lower() in tl for kw in TITLE_KEYWORDS)


def crawl_naver_api(query: str) -> list[dict]:
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {"query": query, "display": DISPLAY, "start": 1, "sort": "date"}
    articles = []
    skipped  = 0
    try:
        resp = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ValueError("Invalid news response")
        for item in data["items"]:
            title        = clean_text(item.get("title", ""))
            naver_link   = item.get("link", "")
            originallink = item.get("originallink", "")
            pub_date     = parse_pub_date(item.get("pubDate", ""))
            description  = clean_text(item.get("description", ""))
            source_m     = re.search(r"https?://(?:www\.)?([^/]+)", originallink)
            source       = source_m.group(1) if source_m else "네이버뉴스"
            if not title_matches(title):
                skipped += 1
                continue
            if title and naver_link:
                articles.append({
                    "title":       title,
                    "url":         naver_link,
                    "date":        pub_date,
                    "source":      source,
                    "description": description,
                    "thumbnail":   None,
                })
        print(f"[Naver] '{query}' → {len(articles)}개 / 제목 불일치 {skipped}개 제외", file=sys.stderr)
    except Exception as e:
        print(f"[Naver] request failed ({type(e).__name__})", file=sys.stderr)
        return None
    return articles


def merge_articles(lists: list[list[dict]], max_count: int = MAX_ARTICLES) -> list[dict]:
    seen_titles: set[str] = set()
    seen_urls:   set[str] = set()
    merged = []
    for article_list in lists:
        for a in article_list:
            title_key = re.sub(r"\s+", "", a["title"].lower())[:40]
            url_key   = a["url"].split("?")[0]
            if title_key in seen_titles or url_key in seen_urls:
                continue
            seen_titles.add(title_key)
            seen_urls.add(url_key)
            merged.append(a)
    merged.sort(key=lambda x: x.get("date", ""), reverse=True)
    return merged[:max_count]


async def fetch_og_image(session: aiohttp.ClientSession, article: dict, sem: asyncio.Semaphore):
    if article.get("thumbnail"):
        return
    url = article.get("url", "")
    if not url:
        return
    async with sem:
        try:
            async with session.get(
                url, headers=FETCH_HEADERS,
                timeout=aiohttp.ClientTimeout(total=THUMB_TIMEOUT),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return
                if "html" not in resp.headers.get("Content-Type", ""):
                    return
                text = ""
                async for chunk in resp.content.iter_chunked(8192):
                    text += chunk.decode("utf-8", errors="ignore")
                    if len(text) > 131072:
                        break
                    if "og:image" in text or "twitter:image" in text:
                        break
                patterns = [
                    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
                ]
                for pat in patterns:
                    m = re.search(pat, text, re.IGNORECASE)
                    if m:
                        img = m.group(1).strip()
                        if img.startswith("http"):
                            article["thumbnail"] = img
                            print(f"  [OK] {article['title'][:30]}…", file=sys.stderr)
                            return
        except Exception:
            pass
    print(f"  [없음] {article['title'][:30]}…", file=sys.stderr)


async def enrich_thumbnails(articles: list[dict]):
    need = [a for a in articles if not a.get("thumbnail")]
    if not need:
        return
    print(f"[썸네일] {len(need)}개 수집 중...", file=sys.stderr)
    sem  = asyncio.Semaphore(THUMB_CONCUR)
    conn = aiohttp.TCPConnector(limit=THUMB_CONCUR)
    async with aiohttp.ClientSession(connector=conn) as session:
        await asyncio.gather(*[fetch_og_image(session, a, sem) for a in need])
    filled = sum(1 for a in need if a.get("thumbnail"))
    print(f"[썸네일] {filled}/{len(need)}개 성공", file=sys.stderr)


def run_news_crawler() -> dict:
    print("[뉴스] 시작", file=sys.stderr)
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("[뉴스] NAVER 환경변수 없음 — 건너뜀", file=sys.stderr)
        return None
    all_articles = []
    for q in SEARCH_QUERIES:
        batch = crawl_naver_api(q)
        if batch is None:
            print("::warning::News fetch failed; keeping previous data", file=sys.stderr)
            return None
        all_articles += batch
        time.sleep(0.3)
    if not all_articles:
        print("::warning::No matching news; keeping previous data", file=sys.stderr)
        return None
    articles = merge_articles([all_articles])
    asyncio.run(enrich_thumbnails(articles))
    for a in articles:
        if not a.get("thumbnail"):
            a["thumbnail"] = None
    result = {
        "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "articles": articles,
    }
    filled = sum(1 for a in articles if a.get("thumbnail"))
    print(f"[뉴스] 완료 — {len(articles)}개 / 썸네일 {filled}개", file=sys.stderr)
    return result


def main():
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "schedule").mkdir(exist_ok=True)

    schedule_by_half = run_schedule_crawler()
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for (year, half), events in schedule_by_half.items():
        path = schedule_json_path(year, half)
        if path.exists() and json.loads(path.read_text(encoding="utf-8")).get("events") == events:
            continue
        atomic_json(path, {"updated": updated_at, "events": events})
        print(f"[완료] {path.name} 저장", file=sys.stderr)

    paths = sorted((ROOT / "data" / "schedule").glob("schedule_????_h[12].json"))
    atomic_json(ROOT / "data" / "schedule" / "manifest.json", {"files": [p.name for p in paths]})
    publish_calendars(ROOT)
    news_data = run_news_crawler()
    if news_data is not None:
        atomic_json(ROOT / "data" / "news.json", news_data)
        print("[완료] news.json 저장", file=sys.stderr)


if __name__ == "__main__":
    main()
