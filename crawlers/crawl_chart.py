import json
import hashlib
import math
import os
import re
import sys
import tempfile
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from io import StringIO

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

KST = timezone(timedelta(hours=9))

ARTIST_KEYWORDS = ["rescene", "리센느"]

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "charts", "chart.json")

COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; SM-G991N) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
}


SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=2, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(("GET", "POST")), respect_retry_after_header=False,
)))
APPLE_MUSIC_URL = "https://rss.applemarketingtools.com/api/v2/kr/music/most-played/100/songs.json"
APPLE_SOURCE_UPDATED = None
SOURCE_META = {}
MAX_AGE_HOURS = {"melon": 6, "bugs": 6, "vibe": 48, "apple_music": 72,
                 "spotify": 72, "youtube_music": 240}


def signed_integer(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def explicit_new(value):
    if value is True or str(value).strip().upper() in {"Y", "TRUE", "NEW"}:
        return True
    if value is False or str(value).strip().upper() in {"N", "FALSE", "SAME", "NONE", "UP", "DOWN"}:
        return False
    return None


def validate_chart(items, size, ranks, ids):
    require_items(items)
    if len(items) != size or sorted(positive_rank(v) or 0 for v in ranks) != list(range(1, size + 1)):
        raise ValueError(f"Incomplete or invalid chart: expected ranks 1..{size}")
    if any(v is None or str(v) == "" for v in ids) or len(set(map(str, ids))) != size:
        raise ValueError("Missing or duplicate chart identifiers")


def timestamp_ms(value):
    number = signed_integer(value)
    if number is None:
        raise ValueError("Missing chart timestamp")
    return datetime.fromtimestamp(number / 1000, KST)


def set_source(platform, url, label, *, moment=None, period=None, rows=None):
    metadata = {"source": url, "chartLabel": label, "sourceKind": "third_party" if "kworb.net" in url else "first_party"}
    if moment is not None:
        if moment.tzinfo is None:
            raise ValueError("Chart timestamp must have a timezone")
        metadata["sourceUpdatedAt"] = moment.isoformat()
    if period:
        metadata["sourcePeriod"] = str(period)
    if rows is not None:
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        metadata["sourceRevision"] = hashlib.sha256(payload.encode()).hexdigest()
    SOURCE_META[platform] = metadata


def parse_source_date(value):
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        moment = parsedate_to_datetime(value)
    if moment.tzinfo is None:
        raise ValueError("Chart timestamp is missing timezone")
    return moment


def source_freshness(platform, metadata, now):
    value = metadata.get("sourceUpdatedAt")
    if not value:
        return "unknown"
    moment = parse_source_date(value)
    age = (now - moment).total_seconds() / 3600
    if age < -1:
        raise ValueError("Chart timestamp is in the future")
    return "outdated" if age > MAX_AGE_HOURS.get(platform, 72) else "current"



def positive_rank(value):
    number = signed_integer(value)
    return number if number is not None and number > 0 else None


def require_items(items):
    if not isinstance(items, list) or not items or not all(isinstance(x, dict) for x in items):
        raise ValueError("Chart response has no valid track list")
    return items


def request_json(url, *, headers=None, data=None):
    method = "POST" if data is not None else "GET"
    response = SESSION.request(method, url, headers=headers or COMMON_HEADERS, data=data, timeout=10)
    response.raise_for_status()
    return response.json()


def is_rescene(artist_name: str) -> bool:
    if not artist_name:
        return False
    lowered = artist_name.lower()
    return any(k in lowered for k in ARTIST_KEYWORDS)


def normalize_title(title: str) -> str:
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
    data = request_json(url, headers=headers)
    song_list = data.get("response", {}).get("SONGLIST", [])
    validate_chart(song_list, 100, [x.get("CURRANK") for x in song_list], [x.get("SONGID") for x in song_list])
    meta = data["response"]
    moment = datetime.strptime(meta["RANKDAY"] + " " + meta["RANKHOUR"], "%Y.%m.%d %H:%M").replace(tzinfo=KST)
    set_source("melon", url, "TOP100", moment=moment)
    results = []
    for item in song_list:
        artist_list = item.get("ARTISTLIST") or []
        artist_name = ", ".join(safe_url_decode(a.get("ARTISTNAME")) for a in artist_list)
        if not is_rescene(artist_name):
            continue
        results.append({
            "songName": safe_url_decode(item.get("SONGNAME")),
            "artistName": artist_name,
            "albumImageUrl": safe_url_decode(item.get("ALBUMIMGPATH")),
            "rank": int(item.get("CURRANK")) if item.get("CURRANK") is not None else None,
            "previousRank": positive_rank(item.get("PASTRANK")),
            "isNew": explicit_new(item.get("RANKTYPE")),
        })
    return results


def fetch_genie():
    url = "https://app.genie.co.kr/chart/j_RealTimeRankSongList.json?pg=1&pgsize=100"
    headers = {**COMMON_HEADERS, "Referer": "https://www.genie.co.kr/"}
    data = request_json(url, headers=headers)
    second_url = url.replace("pg=1&", "pg=2&")
    second = request_json(second_url, headers=headers)
    if data.get("PageInfo", {}).get("ChartTime") != second.get("PageInfo", {}).get("ChartTime"):
        raise ValueError("Genie pages belong to different chart hours")
    items = require_items(data.get("DataSet", {}).get("DATA", [])) + require_items(second.get("DataSet", {}).get("DATA", []))
    validate_chart(items, 200, [x.get("RANK_NO") for x in items], [x.get("SONG_ID") for x in items])
    set_source("genie", url, "실시간 TOP200", period=data.get("PageInfo", {}).get("ChartTime"))
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
            "previousRank": positive_rank(item.get("PRE_RANK_NO")),
            "isNew": None,
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
    data = request_json(url, headers=headers)
    tracks = data.get("response", {}).get("result", {}).get("chart", {}).get("items", {}).get("tracks", [])
    validate_chart(tracks, 100, [(x.get("rank") or {}).get("currentRank") for x in tracks], [x.get("trackId") for x in tracks])
    chart = data["response"]["result"]["chart"]
    set_source("vibe", url, chart.get("title", "오늘 Top 100"), moment=timestamp_ms(chart.get("date")), period=chart.get("chartDate"))
    results = []
    for track in tracks:
        artists = track.get("artists") or []
        artist_name = ", ".join(a.get("artistName", "") for a in artists)
        if not is_rescene(artist_name):
            continue
        rank_info = track.get("rank", {}) or {}
        current_rank = positive_rank(rank_info.get("currentRank"))
        variation = signed_integer(rank_info.get("rankVariation"))
        is_new = explicit_new(rank_info.get("isNew"))
        previous_rank = positive_rank(current_rank + variation) if current_rank and variation is not None and is_new is not True else None
        album = track.get("album", {}) or {}
        results.append({
            "songName": track.get("trackTitle", ""),
            "artistName": artist_name,
            "albumImageUrl": album.get("imageUrl", ""),
            "rank": current_rank,
            "previousRank": previous_rank,
            "isNew": is_new,
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
    data = request_json(url, headers=headers, data=form_data)
    tracks = data.get("list", [])
    validate_chart(tracks, 100, [(x.get("list_attr") or {}).get("rank") for x in tracks], [x.get("track_id") for x in tracks])
    set_source("bugs", url, "실시간 TOP100", moment=timestamp_ms(data.get("info", {}).get("start_dt")))
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
            "previousRank": positive_rank(rank_info.get("rank_last")),
            "isNew": explicit_new(rank_info.get("rank_code")),
        })
    return results


def fetch_flo():
    url = "https://api.music-flo.com/display/v1/browser/chart/1/list?mixYn=N"
    headers = {
        "User-Agent": "okhttp/4.9.2",
        "x-gm-app-name": "FLO",
        "x-gm-app-version": "",
    }
    data = request_json(url, headers=headers)
    tracks = data.get("data", {}).get("trackList", [])
    validate_chart(tracks, 100, list(range(1, len(tracks) + 1)), [x.get("id") for x in tracks])
    set_source("flo", url, "24시간 집계 TOP100", period=data["data"].get("basedOnUpdate"))
    results = []
    for index, item in enumerate(tracks):
        artist_name = (item.get("representationArtist") or {}).get("name", "")
        if not is_rescene(artist_name):
            continue
        rank = index + 1
        rank_info = item.get("rank") or {}
        is_new = explicit_new(rank_info.get("newYn"))
        rank_badge = signed_integer(rank_info.get("rankBadge"))
        try:
            previous_rank = positive_rank(rank_badge + rank) if rank_badge is not None and is_new is not True else None
        except (ValueError, TypeError):
            previous_rank = None
        img_list = (item.get("album") or {}).get("imgList") or []
        image_url = img_list[0].get("url", "") if img_list else ""
        if image_url:
            image_url = re.sub(r"/dims/resize/(\d+)x(\d+)", "/dims/resize/600x600", image_url)
        results.append({
            "songName": item.get("name", ""),
            "artistName": artist_name,
            "albumImageUrl": image_url,
            "rank": rank,
            "previousRank": previous_rank,
            "isNew": is_new,
        })
    return results
def fetch_youtube_music():
    return fetch_kworb("https://kworb.net/youtube/insights/kr.html")


def parse_previous_rank(rank, change):
    change = (change or "").strip()
    if change == "=":
        return rank
    if change in ("", "nan", "RE", "NEW"):
        return None
    try:
        return rank + int(change)
    except ValueError:
        return None


def fetch_kworb(url):
    response = SESSION.get(url, headers=COMMON_HEADERS, timeout=10)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    table = next((t for t in tables if len(t.columns) >= 3 and
                  str(t.columns[0]).strip().lower() in ("pos", "position")), None)
    if table is None or table.empty:
        raise ValueError("Chart table not found")
    is_youtube = "/youtube/" in url
    platform = "youtube_music" if is_youtube else "spotify"
    expected = 100 if is_youtube else 200
    positions = [positive_rank(v) for v in table.iloc[:, 0]]
    if len(positions) != expected or sorted(v or 0 for v in positions) != list(range(1, expected + 1)):
        raise ValueError("Incomplete Kworb chart")
    pattern = r"Week ending (\d{4}/\d{2}/\d{2})" if is_youtube else r"Spotify Daily Chart - South Korea - (\d{4}/\d{2}/\d{2})"
    match = re.search(pattern, response.text)
    if not match:
        raise ValueError("Kworb chart date not found")
    moment = datetime.strptime(match[1], "%Y/%m/%d").replace(tzinfo=timezone.utc)
    set_source(platform, url, "한국 주간 인기곡" if is_youtube else "한국 일간 TOP200",
               moment=moment, period=match[1])
    SOURCE_META[platform]["sourceDatePrecision"] = "date"
    SOURCE_META[platform]["verification"] = "not_compared_with_official"
    results = []
    for row in table.itertuples(index=False, name=None):
        parts = str(row[2]).split(" - ", 1)
        if len(parts) != 2 or not is_rescene(parts[0]):
            continue
        rank = positive_rank(row[0])
        if rank is None:
            continue
        results.append({
            "songName": re.sub(r"\s*\(w/.*?\)\s*$", "", parts[1]).strip(),
            "artistName": parts[0].strip(), "albumImageUrl": "", "rank": rank,
            "previousRank": positive_rank(parse_previous_rank(rank, str(row[1]))),
            "isNew": str(row[1]).strip().upper() == "NEW",
            "isReentry": str(row[1]).strip().upper() == "RE",
        })
    return results


def fetch_spotify():
    return fetch_kworb("https://kworb.net/spotify/country/kr_daily.html")


def fetch_apple_music():
    global APPLE_SOURCE_UPDATED
    response = SESSION.get(APPLE_MUSIC_URL, headers=COMMON_HEADERS, timeout=15)
    response.raise_for_status()
    feed = response.json().get("feed", {})
    items = require_items(feed.get("results"))
    if feed.get("country", "").lower() != "kr" or len(items) != 100:
        raise ValueError("Expected the complete Apple Music Korea top 100 feed")
    if any(not item.get("name") or not item.get("artistName") or not item.get("id") for item in items):
        raise ValueError("Incomplete Apple Music chart entry")
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("Duplicate Apple Music chart IDs")
    APPLE_SOURCE_UPDATED = feed.get("updated")
    moment = parsedate_to_datetime(APPLE_SOURCE_UPDATED)
    set_source("apple_music", APPLE_MUSIC_URL, "한국 인기곡 TOP100", moment=moment,
               rows=[str(item["id"]) for item in items])
    return [{
        "songName": item["name"], "artistName": item["artistName"],
        "albumImageUrl": item.get("artworkUrl100", ""),
        "rank": rank, "previousRank": None, "isNew": None,
    } for rank, item in enumerate(items, 1) if is_rescene(item["artistName"])]


PLATFORM_FETCHERS = {
    "melon": fetch_melon,
    "genie": fetch_genie,
    "vibe": fetch_vibe,
    "bugs": fetch_bugs,
    "flo": fetch_flo,
    "youtube_music": fetch_youtube_music,
    "spotify": fetch_spotify,
    "apple_music": fetch_apple_music,
}


def merge_platform_results(platform_results: dict) -> list:
    order = PLATFORM_FETCHERS
    merged = {}

    for platform in order:
        for entry in platform_results.get(platform, []):
            rank = positive_rank(entry.get("rank"))
            if rank is None:
                continue
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
            existing = merged[key]["ranks"].get(platform)
            if existing is None or rank < existing["rank"]:
                merged[key]["ranks"][platform] = {
                    "rank": rank,
                    "previousRank": positive_rank(entry.get("previousRank")),
                    "isNew": entry.get("isNew"),
                    "isReentry": entry.get("isReentry", False),
                }

    songs = list(merged.values())

    def sort_key(song):
        ranks = [v["rank"] for v in song["ranks"].values() if v.get("rank") is not None]
        return (-len(ranks), min(ranks) if ranks else 9999)

    songs.sort(key=sort_key)
    return songs


def fetch_album_image_itunes(artist_name, song_name):
    try:
        params = {"term": f"{artist_name} {song_name}", "entity": "song", "limit": 5}
        r = SESSION.get("https://itunes.apple.com/search", params=params, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        for item in results:
            if is_rescene(item.get("artistName", "")) and normalize_title(item.get("trackName", "")) == normalize_title(song_name):
                artwork = item.get("artworkUrl100", "")
                return artwork.replace("100x100bb", "600x600bb") if artwork else ""
    except Exception as e:
        print(f"[album_image] itunes lookup failed for {artist_name} - {song_name}: {e}", file=sys.stderr)
    return ""


def fetch_album_image_deezer(artist_name, song_name):
    try:
        params = {"q": f"{artist_name} {song_name}"}
        r = SESSION.get("https://api.deezer.com/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        for item in data:
            if is_rescene((item.get("artist") or {}).get("name", "")) and normalize_title(item.get("title", "")) == normalize_title(song_name):
                album = item.get("album") or {}
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


def load_previous():
    if not os.path.exists(OUTPUT_PATH):
        return {}
    with open(OUTPUT_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("songs"), list):
        raise ValueError("Invalid existing chart.json; refusing to overwrite")
    return data


def previous_entries(previous, platform):
    return [dict(songName=song["songName"], artistName=song["artistName"],
                 albumImageUrl=song.get("albumImageUrl", ""), **song["ranks"][platform])
            for song in previous.get("songs", []) if platform in song.get("ranks", {})]


def apple_previous_ranks(entries, previous):
    old = {normalize_title(e["songName"]): e for e in previous_entries(previous, "apple_music")}
    old_status = previous.get("platformStatus", {}).get("apple_music", {})
    revision = SOURCE_META.get("apple_music", {}).get("sourceRevision")
    same_feed = bool(revision and old_status.get("sourceRevision") == revision)
    has_baseline = bool(old_status.get("sourceRevision"))
    for entry in entries:
        prior = old.get(normalize_title(entry["songName"]))
        entry["previousRank"] = (prior.get("previousRank") if same_feed else prior.get("rank")) if prior else None
        entry["isNew"] = prior.get("isNew") if same_feed and prior else (False if prior else True if has_baseline and not same_feed else None)


def atomic_write(output):
    directory = os.path.dirname(os.path.abspath(OUTPUT_PATH))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=directory, prefix=".chart-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(output, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, OUTPUT_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    previous = load_previous()
    clock = datetime.now(KST)
    now = clock.isoformat()
    SOURCE_META.clear()
    results, statuses = {}, {}
    success_count = 0
    for name, fetcher in PLATFORM_FETCHERS.items():
        old_status = previous.get("platformStatus", {}).get(name, {})
        try:
            entries = fetcher()
            metadata = SOURCE_META.get(name, {})
            freshness = source_freshness(name, metadata, clock)
            old_date, new_date = old_status.get("sourceUpdatedAt"), metadata.get("sourceUpdatedAt")
            if old_date and new_date and parse_source_date(new_date) < parse_source_date(old_date):
                raise ValueError("Source chart date went backwards")
            if name == "apple_music":
                apple_previous_ranks(entries, previous)
                metadata["previousRankBasis"] = "previous_distinct_successful_snapshot"
            results[name] = entries
            statuses[name] = {**metadata, "status": "stale" if freshness == "outdated" else "ok",
                              "freshness": freshness, "lastSuccessAt": now, "lastAttemptAt": now,
                              "reason": "source_outdated" if freshness == "outdated" else None}
            success_count += 1
            print(f"[{name}] {len(entries)} RESCENE track(s) found")
        except Exception as error:
            results[name] = previous_entries(previous, name)
            had_previous = bool(results[name] or old_status.get("lastSuccessAt") or
                                (not old_status and name in previous.get("platforms", [])))
            statuses[name] = {**old_status, "status": "stale" if had_previous else "unavailable",
                              "lastSuccessAt": old_status.get("lastSuccessAt", previous.get("updatedAt") if had_previous else None),
                              "lastAttemptAt": now, "reason": "fetch_failed"}
            print(f"[{name}] failed; keeping previous data: {error}", file=sys.stderr)
    if not success_count:
        print("All chart requests failed; chart.json unchanged", file=sys.stderr)
        return 1
    songs = merge_platform_results(results)
    covers = {normalize_title(s["songName"]): s.get("albumImageUrl", "") for s in previous.get("songs", [])}
    for song in songs:
        if not song.get("albumImageUrl"):
            song["albumImageUrl"] = covers.get(normalize_title(song["songName"]), "")
    fill_missing_album_images(songs)
    atomic_write({"updatedAt": now, "platforms": list(PLATFORM_FETCHERS),
                  "platformStatus": statuses, "songs": songs})
    print(f"Saved {len(songs)} song(s) to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
