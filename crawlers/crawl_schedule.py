#!/usr/bin/env python3

import json
import pathlib
import re
import sys
from datetime import datetime, date, timezone, timedelta
from typing import Optional

import requests

ROOT = pathlib.Path(__file__).parent.parent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
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

LABEL_MAP = {
    "방송":    "broadcast",
    "라디오":  "radio",
    "행사":    "event",
    "팬사인회": "fansign",
    "공연":    "concert",
    "공지":    "notice",
    "기념일":  "anniv",
}

SKIP_LABELS = set()

TYPE_KEYWORDS = {
    "broadcast": ["음방", "음악방송", "inkigayo", "인기가요", "뮤직뱅크", "music bank",
                  "show champion", "엠카운트다운", "mcountdown", "the show",
                  "방송", "출연", "tv", "예능", "버라이어티"],
    "radio":     ["라디오", "radio"],
    "event":     ["행사", "이벤트", "event"],
    "fansign":   ["팬사인", "fansign", "사인회", "팬이벤트", "영상통화"],
    "concert":   ["콘서트", "concert", "showcase", "쇼케이스", "팬미팅", "fanmeeting",
                  "공연", "페스티벌", "festival", "kcon"],
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

def crawl_month(year: int, month: int) -> list:
    params = build_params(year, month)
    try:
        resp = requests.get(API_BASE, headers=HEADERS, params=params, timeout=15)
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
        events.append({
            "date":   d,
            "title":  title,
            "detail": "",
            "type":   classify_type(ev),
            "source": "mnetplus",
        })

    print(f"[MnetPlus] {year}/{month:02d} → {len(events)}개", file=sys.stderr)
    return events

def main():
    print("[스케줄 크롤러 v4] 시작", file=sys.stderr)

    today  = date.today()
    months = [(today.year, today.month)]
    if today.month == 12:
        months.append((today.year + 1, 1))
    else:
        months.append((today.year, today.month + 1))

    all_events = []
    for y, m in months:
        all_events.extend(crawl_month(y, m))

    seen    = set()
    deduped = []
    for ev in sorted(all_events, key=lambda e: e["date"]):
        key = (ev["date"], ev["title"])
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    output = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events":  deduped,
    }

    out_path = ROOT / "schedule.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[스케줄 크롤러 v4] 완료 — {len(deduped)}개 저장 → {out_path}", file=sys.stderr)

if __name__ == "__main__":
    main()
