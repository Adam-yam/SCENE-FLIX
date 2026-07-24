# 멜론/지니/바이브/벅스 실시간 차트에서 리센느 곡만 뽑아서 data/charts/chart.json에 저장
# 각 플랫폼 API는 비공식이라 언제든 깨질 수 있음 -> 하나 실패해도 나머지는 정상 진행되게 처리

import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from io import StringIO

import pandas as pd
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
    headers = {
        **COMMON_HEADERS,
        "Referer": "https://vibe.naver.com/",
        "Origin": "https://vibe.naver.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"[vibe] status={r.status_code}", file=sys.stderr)
        r.raise_for_status()
        if not r.text.strip():
            print("[vibe] empty response body (likely blocked)", file=sys.stderr)
            return []
        data = r.json()
        tracks = data.get("response", {}).get("result", {}).get("chart", {}).get("items", {}).get("tracks", [])
        print(f"[vibe] parsed track count={len(tracks)}", file=sys.stderr)
        if not tracks:
            print(f"[vibe] response body={json.dumps(data)[:1000]}", file=sys.stderr)
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
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


# charts.youtube.com은 GitHub Actions IP를 차단해서(캡차/차단 페이지 응답)
# 직접 크롤링이 불안정함 -> 스포티파이와 같은 방식으로, kworb.net이 정리해두는
# 한국 유튜브 주간 차트 표를 대신 가져다 씀
def fetch_youtube_music():
    url = "https://kworb.net/youtube/insights/kr.html"
    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()
        tables = pd.read_html(StringIO(r.text))
        df = tables[0]
    except Exception as e:
        print(f"[youtube_music] fetch failed: {e}", file=sys.stderr)
        return []

    pos_col, change_col, title_col = df.columns[0], df.columns[1], df.columns[2]

    results = []
    for _, row in df.iterrows():
        cell = str(row[title_col])
        if not is_rescene(cell):
            continue
        parts = cell.split(" - ", 1)
        if len(parts) != 2:
            continue
        artist_name = parts[0].strip()
        song_name = parts[1].strip()
        try:
            rank = int(row[pos_col])
        except (ValueError, TypeError):
            continue
        results.append({
            "songName": song_name,
            "artistName": artist_name,
            "albumImageUrl": "",
            "rank": rank,
            "previousRank": parse_previous_rank(rank, str(row[change_col])),
        })
    return results


# 스포티파이는 공식 API에 차트 엔드포인트가 없어서, kworb.net이 매일 정리해두는
# 한국 데일리 차트 표를 가져다 씀. 앨범 이미지가 없으니 다른 플랫폼에서 같은 곡이
# 잡히면 그쪽 이미지를 병합 단계에서 대신 채워 넣게 됨
def parse_previous_rank(rank, change):
    change = (change or "").strip()
    if change in ("", "=", "nan"):
        return rank
    if change in ("RE", "NEW"):
        return None
    try:
        return rank - int(change)
    except ValueError:
        return None


def fetch_spotify():
    url = "https://kworb.net/spotify/country/kr_daily.html"
    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=10)
        r.raise_for_status()
        tables = pd.read_html(StringIO(r.text))
        df = tables[0]
    except Exception as e:
        print(f"[spotify] fetch failed: {e}", file=sys.stderr)
        return []

    pos_col, change_col, title_col = df.columns[0], df.columns[1], df.columns[2]

    results = []
    for _, row in df.iterrows():
        cell = str(row[title_col])
        if not is_rescene(cell):
            continue
        parts = cell.split(" - ", 1)
        if len(parts) != 2:
            continue
        artist_name = parts[0].strip()
        song_name = re.sub(r"\s*\(w/.*?\)\s*$", "", parts[1]).strip()
        try:
            rank = int(row[pos_col])
        except (ValueError, TypeError):
            continue
        results.append({
            "songName": song_name,
            "artistName": artist_name,
            "albumImageUrl": "",
            "rank": rank,
            "previousRank": parse_previous_rank(rank, str(row[change_col])),
        })
    return results


PLATFORM_FETCHERS = {
    "melon": fetch_melon,
    "genie": fetch_genie,
    "vibe": fetch_vibe,
    "bugs": fetch_bugs,
    "youtube_music": fetch_youtube_music,
    "spotify": fetch_spotify,
}


def merge_platform_results(platform_results: dict) -> list:
    # 곡 제목 기준으로 플랫폼별 결과를 하나로 합침
    # 앨범 이미지는 먼저 찾은 플랫폼 것부터 사용 (melon > genie > vibe > bugs)
    order = ["melon", "genie", "vibe", "bugs", "youtube_music", "spotify"]
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


# 바이브/스포티파이/유튜브뮤직(kworb)처럼 앨범 이미지를 안 주는 플랫폼에만 걸린
# 곡은 표지가 비어있을 수 있음 -> 병합이 끝난 뒤 iTunes를 먼저 찾아보고,
# 거기에 없으면 Deezer로 한 번 더 찾아서 채움 (둘 다 API 키 불필요)
def fetch_album_image_itunes(artist_name, song_name):
    try:
        params = {"term": f"{artist_name} {song_name}", "entity": "song", "limit": 1}
        r = requests.get("https://itunes.apple.com/search", params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            artwork = results[0].get("artworkUrl100", "")
            return artwork.replace("100x100bb", "600x600bb") if artwork else ""
    except Exception as e:
        print(f"[album_image] itunes lookup failed for {artist_name} - {song_name}: {e}", file=sys.stderr)
    return ""


def fetch_album_image_deezer(artist_name, song_name):
    try:
        params = {"q": f"{artist_name} {song_name}"}
        r = requests.get("https://api.deezer.com/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        if data:
            album = data[0].get("album", {}) or {}
            return album.get("cover_xl") or album.get("cover_big") or ""
    except Exception as e:
        print(f"[album_image] deezer lookup failed for {artist_name} - {song_name}: {e}", file=sys.stderr)
    return ""


def fill_missing_album_images(songs):
    for song in songs:
        if song.get("albumImageUrl"):
            continue
        image = fetch_album_image_itunes(song["artistName"], song["songName"])
        if not image:
            image = fetch_album_image_deezer(song["artistName"], song["songName"])
        if image:
            song["albumImageUrl"] = image
        else:
            print(f"[album_image] no cover found for {song['artistName']} - {song['songName']}", file=sys.stderr)
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
    songs = fill_missing_album_images(songs)

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
