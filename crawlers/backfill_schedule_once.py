#!/usr/bin/env python3
"""
1회성 전체 스케줄 백필 스크립트.

MnetPlus 캘린더 API에서 그룹 데뷔 시점(2024-03)부터 현재+1개월까지
전 기간을 크롤링해서 data/schedule/ 폴더의 반기별 JSON 파일에 병합 저장한다.

crawl_schedule.py와 같은 디렉토리에 두고 한 번 실행한 뒤, 이 파일은 지워도 된다.
(결과로 생성/갱신된 data/schedule/*.json 파일은 그대로 남는다.)

    python3 backfill_schedule_once.py
"""

import json
import sys
from datetime import date, datetime, timezone

from crawl_schedule import (
    crawl_schedule_month,
    half_key,
    schedule_json_path,
    _load_half_schedule,
)

START_YEAR  = 2024
START_MONTH = 3  # RESCENE 데뷔월(2024-03)


def month_range(start_year: int, start_month: int, end_year: int, end_month: int):
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def main():
    today = date.today()
    if today.month == 12:
        end_year, end_month = today.year + 1, 1
    else:
        end_year, end_month = today.year, today.month + 1

    print(f"[백필] {START_YEAR}-{START_MONTH:02d} ~ {end_year}-{end_month:02d} 전체 크롤링 시작", file=sys.stderr)

    all_events = []
    for y, m in month_range(START_YEAR, START_MONTH, end_year, end_month):
        all_events.extend(crawl_schedule_month(y, m))

    by_half: dict[tuple[int, int], list] = {}
    for ev in all_events:
        by_half.setdefault(half_key(ev["date"]), []).append(ev)

    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for hk in sorted(by_half.keys()):
        year, half = hk
        merged = _load_half_schedule(year, half)
        merged.extend(by_half[hk])
        seen    = set()
        deduped = []
        for ev in sorted(merged, key=lambda e: e["date"]):
            key = (ev["date"], ev["title"])
            if key not in seen:
                seen.add(key)
                deduped.append(ev)
        path = schedule_json_path(year, half)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"updated": updated_at, "events": deduped}, f, ensure_ascii=False, indent=2)
        print(f"[백필] {path.name} → {len(deduped)}개", file=sys.stderr)

    print("[백필] 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
