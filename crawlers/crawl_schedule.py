#!/usr/bin/env python3

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
import yt_dlp

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


def extract_date(ev: dict) -> Optional[str]:
    if ev.get("allDay"):
        raw = ev.get("startAtAllDay", "")
    else:
        raw = ev.get("startAt", ev.get("startAtAllDay", ""))
    if not raw:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(raw))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def extract_time(ev: dict) -> str:
    """allDay가 아닌 경우 startAt(UTC)을 KST로 변환해 'HH:MM' 반환. 없으면 빈 문자열."""
    if ev.get("allDay"):
        return ""
    raw = ev.get("startAt", "")
    if not raw:
        return ""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", str(raw))
    if not m:
        return ""
    try:
        dt_utc = datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), tzinfo=timezone.utc,
        )
        dt_kst = dt_utc + timedelta(hours=9)
        # 자정(00:00)은 실질적으로 시간 정보가 없는 종일 일정으로 취급
        if dt_kst.hour == 0 and dt_kst.minute == 0:
            return ""
        return dt_kst.strftime("%H:%M")
    except Exception:
        return ""


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
            "time":   extract_time(ev),
            "title":  title,
            "detail": "",
            "type":   classify_type(ev),
            "source": "mnetplus",
        })
    print(f"[MnetPlus] {year}/{month:02d} → {len(events)}개", file=sys.stderr)
    return events


def run_schedule_crawler() -> dict:
    print("[스케줄] 시작", file=sys.stderr)
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
    print(f"[스케줄] 완료 — {len(deduped)}개", file=sys.stderr)
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
DISPLAY        = 20
MAX_ARTICLES   = 20
THUMB_TIMEOUT  = 12
THUMB_CONCUR   = 6


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
        for item in data.get("items", []):
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
        print(f"[Naver] '{query}' 오류: {e}", file=sys.stderr)
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
                allow_redirects=True, ssl=False,
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
    conn = aiohttp.TCPConnector(limit=THUMB_CONCUR, ssl=False)
    async with aiohttp.ClientSession(connector=conn) as session:
        await asyncio.gather(*[fetch_og_image(session, a, sem) for a in need])
    filled = sum(1 for a in need if a.get("thumbnail"))
    print(f"[썸네일] {filled}/{len(need)}개 성공", file=sys.stderr)


def run_news_crawler() -> dict:
    print("[뉴스] 시작", file=sys.stderr)
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("[뉴스] NAVER 환경변수 없음 — 건너뜀", file=sys.stderr)
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
    print(f"[뉴스] 완료 — {len(articles)}개 / 썸네일 {filled}개", file=sys.stderr)
    return result


SHORTS_CHANNELS = {
    "official": "https://www.youtube.com/@RESCENE_official/shorts",
    "woni":     "https://www.youtube.com/@helloiamwoninicetomeetyou/shorts",
}

SHORTS_JSON_PATH = ROOT / "data" / "shorts.json"
YOUTUBE_API_KEY  = os.environ.get("YOUTUBE_API_KEY", "")


def _load_existing_shorts() -> dict[str, dict]:
    if not SHORTS_JSON_PATH.exists():
        return {}
    try:
        with open(SHORTS_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {item["vid"]: item for item in data.get("items", [])}
    except Exception as e:
        print(f"[Shorts] 기존 파일 읽기 실패: {e}", file=sys.stderr)
        return {}


def _fetch_publish_dates(vids: list[str]) -> dict[str, dict]:
    if not YOUTUBE_API_KEY or not vids:
        print("[Shorts] YOUTUBE_API_KEY 없음 — 날짜 조회 건너뜀", file=sys.stderr)
        return {}
    result = {}
    for i in range(0, len(vids), 50):
        batch = vids[i:i + 50]
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part":   "snippet",
                    "id":     ",".join(batch),
                    "key":    YOUTUBE_API_KEY,
                    "fields": "items(id,snippet/publishedAt,snippet/title,snippet/defaultAudioLanguage)",
                    "hl":     "ko",
                },
                timeout=15,
            )
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                vid     = item.get("id", "")
                snippet = item.get("snippet", {})
                pub     = snippet.get("publishedAt", "")
                title   = snippet.get("title", "")
                if vid:
                    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", pub)
                    result[vid] = {
                        "date":  f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else "",
                        "title": title,
                    }
            print(f"[Shorts] API 배치 {i//50 + 1} → {len(result)}개 수집", file=sys.stderr)
        except Exception as e:
            print(f"[Shorts] YouTube API 배치 조회 실패: {e}", file=sys.stderr)
    return result


def _fetch_shorts_vids(url: str) -> list[dict]:
    ydl_opts = {
        "quiet":        True,
        "no_warnings":  True,
        "extract_flat": True,
        "extractor_args": {"youtubetab": {"skip": ["authcheck"]}},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("entries", []) if info else []
    except Exception as e:
        print(f"[Shorts] yt-dlp 실패: {e}", file=sys.stderr)
        return []


def crawl_shorts_channel(channel_key: str, url: str, existing: dict[str, dict]) -> list[dict]:
    print(f"[Shorts] {channel_key} 크롤링 시작...", file=sys.stderr)

    entries = _fetch_shorts_vids(url)
    if not entries:
        return []

    items     = []
    new_items = []

    for entry in entries:
        vid = entry.get("id", "")
        if not vid:
            continue
        if vid in existing:
            items.append(existing[vid])
            continue
        item = {
            "vid":     vid,
            "channel": channel_key,
            "date":    "",
            "title":   entry.get("title", "").strip(),
        }
        items.append(item)
        new_items.append(item)

    if new_items:
        print(f"[Shorts] {channel_key} 신규 {len(new_items)}개 날짜/제목 조회...", file=sys.stderr)
        meta_map = _fetch_publish_dates([i["vid"] for i in new_items])
        filled = 0
        for item in new_items:
            meta = meta_map.get(item["vid"])
            if meta:
                item["date"]  = meta["date"]
                item["title"] = meta["title"] or item["title"]
                filled += 1
        print(f"[Shorts] {channel_key} 날짜/제목 {filled}/{len(new_items)}개 완료", file=sys.stderr)

    print(f"[Shorts] {channel_key} 완료 — 전체 {len(items)}개 / 신규 {len(new_items)}개", file=sys.stderr)
    return items


def run_shorts_crawler() -> dict:
    print("[Shorts] 시작", file=sys.stderr)
    existing = _load_existing_shorts()
    all_items = []
    for channel_key, url in SHORTS_CHANNELS.items():
        items = crawl_shorts_channel(channel_key, url, existing)
        all_items.extend(items)
        time.sleep(1)
    all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
    result = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items":   all_items,
    }
    print(f"[Shorts] 완료 — 총 {len(all_items)}개", file=sys.stderr)
    return result


def main():
    (ROOT / "data").mkdir(exist_ok=True)

    schedule_data = run_schedule_crawler()
    with open(ROOT / "data" / "schedule.json", "w", encoding="utf-8") as f:
        json.dump(schedule_data, f, ensure_ascii=False, indent=2)
    print(f"[완료] schedule.json 저장", file=sys.stderr)

    news_data = run_news_crawler()
    with open(ROOT / "data" / "news.json", "w", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False, indent=2)
    print(f"[완료] news.json 저장", file=sys.stderr)

    shorts_data = run_shorts_crawler()
    with open(ROOT / "data" / "shorts.json", "w", encoding="utf-8") as f:
        json.dump(shorts_data, f, ensure_ascii=False, indent=2)
    print(f"[완료] shorts.json 저장", file=sys.stderr)


if __name__ == "__main__":
    main()
