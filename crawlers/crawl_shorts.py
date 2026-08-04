#!/usr/bin/env python3

import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timezone

import requests
import yt_dlp

ROOT = pathlib.Path(__file__).parent.parent

COMMON_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

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

    shorts_data = run_shorts_crawler()
    with open(ROOT / "data" / "shorts.json", "w", encoding="utf-8") as f:
        json.dump(shorts_data, f, ensure_ascii=False, indent=2)
    print(f"[완료] shorts.json 저장", file=sys.stderr)


if __name__ == "__main__":
    main()
