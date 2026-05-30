#!/usr/bin/env python3
"""
통합 크롤러 — 스케줄(schedule.json) + 뉴스(news.json) 동시 생성
"""

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

ROOT = pathlib.Path(__file__).parent.parent

# ───────────────────────────── 공통 헤더 ──────────────────────────────────

COMMON_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ═══════════════════════════════════════════════════════════════════════════
#  1. 스케줄 크롤러 (MnetPlus)
# ═══════════════════════════════════════════════════════════════════════════

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


def extract_date(ev: dict) -> Optional[str]:
    if ev.get("allDay"):
        raw = ev.get("startAtAllDay", "")
    else:
        raw = ev.get("startAt", ev.get("startAtAllDay", ""))
    if not raw:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(raw))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


# index.html의 SCHED_TYPE_COLOR / CSS 클래스명과 반드시 일치해야 함
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
        return []

    events = []
    for ev in data.get("events", []):
        d     = extract_date(ev)
        title = ev.get("title", "").strip()
        if not d or not title:
            continue
        label_name = (ev.get("label") or {}).get("name", "")
        if label_name == "기념일":
            continue
        events.append({
            "date":   d,
            "title":  title,
            "detail": "",
            "type":   classify_type(ev),
            "source": "mnetplus",
        })

    print(f"[MnetPlus] {year}/{month:02d} → {len(events)}개", file=sys.stderr)
    return events


def run_schedule_crawler() -> dict:
    print("[스케줄 크롤러 v4] 시작", file=sys.stderr)

    today  = date.today()
    months = [(today.year, today.month)]
    if today.month == 12:
        months.append((today.year + 1, 1))
    else:
        months.append((today.year, today.month + 1))

    all_events = []
    for y, m in months:
        all_events.extend(crawl_schedule_month(y, m))

    seen    = set()
    deduped = []
    for ev in sorted(all_events, key=lambda e: e["date"]):
        key = (ev["date"], ev["title"])
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    result = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events":  deduped,
    }
    print(f"[스케줄 크롤러 v4] 완료 — {len(deduped)}개", file=sys.stderr)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  2. 뉴스 크롤러 (Naver API)
# ═══════════════════════════════════════════════════════════════════════════

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
}

SEARCH_QUERIES = ["리센느", "RESCENE"]
DISPLAY        = 20
MAX_ARTICLES   = 20
THUMB_TIMEOUT  = 6
THUMB_CONCUR   = 8


def parse_pub_date(raw: str) -> str:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc).strftime("%Y.%m.%d")
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


def crawl_naver_api(query: str) -> list[dict]:
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {
        "query":   query,
        "display": DISPLAY,
        "start":   1,
        "sort":    "date",
    }
    articles = []
    try:
        resp = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("items", []):
            title       = clean_text(item.get("title", ""))
            link        = item.get("originallink") or item.get("link", "")
            pub_date    = parse_pub_date(item.get("pubDate", ""))
            description = clean_text(item.get("description", ""))
            source_m    = re.search(r"https?://(?:www\.)?([^/]+)", link)
            source      = source_m.group(1) if source_m else "네이버뉴스"

            if title and link:
                articles.append({
                    "title":       title,
                    "url":         link,
                    "date":        pub_date,
                    "source":      source,
                    "description": description,
                    "thumbnail":   None,
                })

        print(f"[Naver API] '{query}' → {len(articles)}개", file=sys.stderr)
    except Exception as e:
        print(f"[Naver API] '{query}' 오류: {e}", file=sys.stderr)

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


async def fetch_og_image(
    session: aiohttp.ClientSession,
    article: dict,
    sem: asyncio.Semaphore,
):
    if article.get("thumbnail"):
        return

    async with sem:
        try:
            async with session.get(
                article["url"],
                headers=FETCH_HEADERS,
                timeout=aiohttp.ClientTimeout(total=THUMB_TIMEOUT),
                allow_redirects=True,
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return
                if "html" not in resp.headers.get("Content-Type", ""):
                    return
                chunk = await resp.content.read(8192)
                text  = chunk.decode("utf-8", errors="ignore")

                m = re.search(
                    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                    text, re.IGNORECASE,
                ) or re.search(
                    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                    text, re.IGNORECASE,
                )
                if m:
                    img = m.group(1).strip()
                    if img.startswith("http"):
                        article["thumbnail"] = img
                        print(f"  [og] {article['title'][:28]}… OK", file=sys.stderr)
        except Exception:
            pass


async def enrich_thumbnails(articles: list[dict]):
    need = [a for a in articles if not a.get("thumbnail")]
    if not need:
        return
    print(f"[썸네일] og:image 수집 — {len(need)}개", file=sys.stderr)
    sem  = asyncio.Semaphore(THUMB_CONCUR)
    conn = aiohttp.TCPConnector(limit=THUMB_CONCUR, ssl=False)
    async with aiohttp.ClientSession(connector=conn) as session:
        await asyncio.gather(*[fetch_og_image(session, a, sem) for a in need])
    filled = sum(1 for a in need if a.get("thumbnail"))
    print(f"[썸네일] {filled}/{len(need)}개 성공", file=sys.stderr)


def run_news_crawler() -> dict:
    print("[뉴스 크롤러 v3] 시작", file=sys.stderr)

    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("[뉴스 크롤러] NAVER_CLIENT_ID / SECRET 환경변수 없음 — 건너뜀", file=sys.stderr)
        return {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "articles": []}

    all_articles = []
    for q in SEARCH_QUERIES:
        all_articles += crawl_naver_api(q)
        time.sleep(0.3)

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
    print(
        f"[뉴스 크롤러 v3] 완료 — {len(articles)}개 / 썸네일 {filled}개",
        file=sys.stderr,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  3. 메인 — 두 크롤러 실행 후 각각 저장
# ═══════════════════════════════════════════════════════════════════════════

def main():
    # ── 스케줄 ──────────────────────────────────────────────────────────────
    schedule_data = run_schedule_crawler()
    sched_path = ROOT / "schedule.json"
    with open(sched_path, "w", encoding="utf-8") as f:
        json.dump(schedule_data, f, ensure_ascii=False, indent=2)
    print(f"[완료] schedule.json → {sched_path}", file=sys.stderr)

    # ── 뉴스 ────────────────────────────────────────────────────────────────
    news_data = run_news_crawler()
    news_path = ROOT / "news.json"
    with open(news_path, "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)
    print(f"[완료] news.json → {news_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
