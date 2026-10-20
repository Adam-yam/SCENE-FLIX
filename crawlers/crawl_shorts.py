                      

import json
import os
import pathlib
import re
import sys
import time
from datetime import datetime, timezone

import requests
import yt_dlp
from storage import atomic_json

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
        items = data.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) or not isinstance(item.get("vid"), str) or not item.get("channel") for item in items):
            raise ValueError("Invalid stored shorts")
        return {item["vid"]: item for item in items}
    except Exception as e:
        print(f"[Shorts] 기존 파일 읽기 실패: {e}", file=sys.stderr)
        raise ValueError("Invalid existing shorts; refusing to overwrite") from e


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
            print(f"[Shorts] YouTube API request failed ({type(e).__name__})", file=sys.stderr)
    return result


def _fetch_shorts_vids(url: str) -> list[dict]:
    ydl_opts = {
        "quiet":        True,
        "no_warnings":  True,
        "extract_flat": True,
        "socket_timeout": 20,
        "retries": 2,
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
            item = dict(existing[vid])
            items.append(item)
            if not item.get("date") or not item.get("title"):
                new_items.append(item)
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
    successes = 0
    for channel_key, url in SHORTS_CHANNELS.items():
        items = crawl_shorts_channel(channel_key, url, existing)
        if items:
            successes += 1
        if not items:
            print(f"::warning::Shorts {channel_key} returned no items; keeping previous data", file=sys.stderr)
            items = [item for item in existing.values() if item.get("channel") == channel_key]
        all_items.extend(items)
        time.sleep(1)
    if not successes:
        return None
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
    if shorts_data and shorts_data["items"]:
        atomic_json(SHORTS_JSON_PATH, shorts_data)
    print(f"[완료] shorts.json 저장", file=sys.stderr)


if __name__ == "__main__":
    main()
