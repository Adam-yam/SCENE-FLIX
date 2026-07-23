# 멜론/지니/바이브/벅스 실시간 차트에서 리센느 곡만 뽑아서 data/charts/chart.json에 저장
# 각 플랫폼 API는 비공식이라 언제든 깨질 수 있음 -> 하나 실패해도 나머지는 정상 진행되게 처리

import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))

ARTIST_KEYWORDS = ["rescene", "리센느"]

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "charts", "chart.json")

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; SM-G991N) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
}


def is_rescene(artist_name: str) -> bool:
    if not artist_name:
        return False
    lowered = artist_name.lower()
    return any(k in lowered for k in ARTIST_KEYWORDS)


def normalize_title(title: str) -> str:
    # 플랫폼마다 제목 표기가 조금씩 달라서 매칭용으로 공백/괄호 등을 정리
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"[^\w가-힣]+", "", t)
    return t.strip()


def safe_url_decode(value):
    if value is None:
        return ""
    try:
        return urllib.parse.unquote(str(value))
    except Exception:
        return str(value)


def fetch_melon():
    url = "https://m2.melon.com/m6/chart/ent/songChartList.json"
    headers = {**COMMON_HEADERS, "Referer": "https://www.melon.com/"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        song_list = data.get("response", {}).get("SONGLIST", [])
    except Exception as e:
        print(f"[melon] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in song_list:
        artist_list = item.get("ARTISTLIST") or []
        artist_name = safe_url_decode(
            artist_list[0].get("ARTISTNAME") if artist_list else "Unknown"
        )
        if not is_rescene(artist_name):
            continue
        results.append({
            "songName": safe_url_decode(item.get("SONGNAME")),
            "artistName": artist_name,
            "albumImageUrl": safe_url_decode(item.get("ALBUMIMGPATH")),
            "rank": int(item.get("CURRANK")) if item.get("CURRANK") is not None else None,
            "previousRank": int(item.get("PASTRANK")) if item.get("PASTRANK") else None,
        })
    return results


def fetch_genie():
    url = "https://app.genie.co.kr/chart/j_RealTimeRankSongList.json?pg=1&pgsize=100"
    headers = {**COMMON_HEADERS, "Referer": "https://www.genie.co.kr/"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        items = data.get("DataSet", {}).get("DATA", [])
    except Exception as e:
        print(f"[genie] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for item in items:
        artist_name = safe_url_decode(item.get("ARTIST_NAME"))
        if not is_rescene(artist_name):
            continue
        results.append({
            "songName": safe_url_decode(item.get("SONG_NAME")),
            "artistName": artist_name,
            "albumImageUrl": safe_url_decode(item.get("ALBUM_IMG_PATH")),
            "rank": int(item.get("RANK_NO")) if item.get("RANK_NO") is not None else None,
            "previousRank": int(item.get("PRE_RANK_NO")) if item.get("PRE_RANK_NO") else None,
        })
    return results


def fetch_vibe():
    url = "https://apis.naver.com/vibeWeb/musicapiweb/vibe/v1/chart/track/total?start=1&display=100"
    headers = {**COMMON_HEADERS, "Referer": "https://vibe.naver.com/"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        tracks = data.get("response", {}).get("result", {}).get("chart", {}).get("items", {}).get("tracks", [])
    except Exception as e:
        print(f"[vibe] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for track in tracks:
        artists = track.get("artists") or []
        artist_name = ", ".join(a.get("artistName", "") for a in artists)
        if not is_rescene(artist_name):
            continue
        rank_info = track.get("rank", {}) or {}
        current_rank = rank_info.get("currentRank")
        variation = rank_info.get("rankVariation")
        previous_rank = (current_rank - variation) if (current_rank is not None and variation is not None) else None
        album = track.get("album", {}) or {}
        results.append({
            "songName": track.get("trackTitle", ""),
            "artistName": artist_name,
            "albumImageUrl": album.get("imageUrl", ""),
            "rank": current_rank,
            "previousRank": previous_rank,
        })
    return results


def fetch_bugs():
    url = "https://m.bugs.co.kr/api/getChartTrack"
    headers = {
        **COMMON_HEADERS,
        "Referer": "https://music.bugs.co.kr/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    form_data = {
        "meta_type": "track",
        "period_tp": "realtime",
        "svc_type": "20151",
        "size": "100",
    }
    try:
        r = requests.post(url, headers=headers, data=form_data, timeout=10)
        r.raise_for_status()
        data = r.json()
        tracks = data.get("list", [])
    except Exception as e:
        print(f"[bugs] fetch failed: {e}", file=sys.stderr)
        return []

    results = []
    for track in tracks:
        artists = track.get("artists") or []
        artist_name = ", ".join(a.get("artist_nm", "") for a in artists)
        if not is_rescene(artist_name):
            continue
        rank_info = track.get("list_attr", {}) or {}
        album = track.get("album", {}) or {}
        image = album.get("image", {}) or {}
        image_path = image.get("path", "")
        results.append({
            "songName": track.get("track_title", ""),
            "artistName": artist_name,
            "albumImageUrl": f"https://image.bugsm.co.kr/album/images/350{image_path}" if image_path else "",
            "rank": rank_info.get("rank"),
            "previousRank": rank_info.get("rank_last"),
        })
    return results


PLATFORM_FETCHERS = {
    "melon": fetch_melon,
    "genie": fetch_genie,
    "vibe": fetch_vibe,
    "bugs": fetch_bugs,
}


def merge_platform_results(platform_results: dict) -> list:
    # 곡 제목 기준으로 플랫폼별 결과를 하나로 합침
    # 앨범 이미지는 먼저 찾은 플랫폼 것부터 사용 (melon > genie > vibe > bugs)
    order = ["melon", "genie", "vibe", "bugs"]
    merged = {}

    for platform in order:
        for entry in platform_results.get(platform, []):
            key = normalize_title(entry["songName"])
            if not key:
                continue
            if key not in merged:
                merged[key] = {
                    "songName": entry["songName"],
                    "artistName": entry["artistName"],
                    "albumImageUrl": entry.get("albumImageUrl", ""),
                    "ranks": {},
                }
            if not merged[key].get("albumImageUrl") and entry.get("albumImageUrl"):
                merged[key]["albumImageUrl"] = entry["albumImageUrl"]
            merged[key]["ranks"][platform] = {
                "rank": entry.get("rank"),
                "previousRank": entry.get("previousRank"),
            }

    songs = list(merged.values())

    # 차트에 걸린 플랫폼이 많은 곡 우선, 그다음 최고 순위가 높은 곡 우선
    def sort_key(song):
        ranks = [v["rank"] for v in song["ranks"].values() if v.get("rank") is not None]
        return (-len(ranks), min(ranks) if ranks else 9999)

    songs.sort(key=sort_key)
    return songs


def main():
    platform_results = {}
    for name, fetcher in PLATFORM_FETCHERS.items():
        try:
            platform_results[name] = fetcher()
            print(f"[{name}] {len(platform_results[name])} RESCENE track(s) found")
        except Exception as e:
            print(f"[{name}] unexpected error: {e}", file=sys.stderr)
            platform_results[name] = []

    songs = merge_platform_results(platform_results)

    output = {
        "updatedAt": datetime.now(KST).isoformat(),
        "platforms": list(PLATFORM_FETCHERS.keys()),
        "songs": songs,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(songs)} song(s) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
