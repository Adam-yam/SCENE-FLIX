import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

KST = timezone(timedelta(hours=9))
SOURCES = {"all": "전체", "mnetplus": "Mnet Plus", "blip": "blip"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:32]


def escape(value):
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value))
    return value.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold(line):
    lines, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > 75:
            lines.append(current)
            current, size = " ", 1
        current += char
        size += width
    return "\r\n".join(lines + [current])


def stamp(value):
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_text(path, content):
    data = content.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".calendar-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def collect_events(items):
    groups = defaultdict(list)
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Invalid schedule entry")
        source = item.get("source")
        if source not in ("mnetplus", "blip"):
            continue
        date.fromisoformat(item["date"])
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            raise ValueError("Invalid schedule title")
        time = item.get("time") or ""
        if time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
            raise ValueError("Invalid schedule time")
        ident = str(item.get("id") or "legacy-" + digest([item["date"], time, item["title"]]))
        groups[source + ":" + ident].append(item)
    events = []
    for identity, rows in sorted(groups.items()):
        rows.sort(key=lambda r: (r["date"], r.get("time") or ""))
        row = rows[0]
        first, last = date.fromisoformat(row["date"]), date.fromisoformat(rows[-1]["date"])
        raw_start = next((r["start"] for r in rows if r.get("start")), None)
        raw_end = next((r["end"] for r in rows if r.get("end")), None)
        start_dt = datetime.fromisoformat(raw_start.replace("Z", "+00:00")) if raw_start else None
        end_dt = datetime.fromisoformat(raw_end.replace("Z", "+00:00")) if raw_end else None
        if any(d is not None and d.tzinfo is None for d in (start_dt, end_dt)):
            raise ValueError("Calendar times must include a timezone")
        if start_dt:
            first = start_dt.astimezone(KST).date()
        if end_dt:
            last = end_dt.astimezone(KST).date()
        if last < first or (start_dt and end_dt and end_dt < start_dt):
            raise ValueError("Invalid schedule period")
        all_day = bool(row.get("allDay", not row.get("time")))
        if all_day:
            start, end = first.strftime("%Y%m%d"), (last + timedelta(days=1)).strftime("%Y%m%d")
        else:
            if not start_dt:
                start_dt = datetime.fromisoformat(first.isoformat() + "T" + (row.get("time") or "00:00")).replace(tzinfo=KST)
            start = stamp(start_dt)
            end = stamp(end_dt) if end_dt and end_dt > start_dt and not row.get("endTimeHidden") else ""
        link = str(row.get("link") or "")
        parsed = urlsplit(link)
        if parsed.scheme not in ("https", "http") or not parsed.netloc or any(c in link for c in "\r\n"):
            link = ""
        events.append({"identities": [identity], "sources": [row["source"]], "start": start, "end": end, "allDay": all_day, "title": row["title"].strip(), "detail": str(row.get("detail") or ""), "location": str(row.get("location") or ""), "link": link})
    return events


def combine(events):
    groups = {}
    for event in events:
        key = (event["start"], event["end"], event["allDay"], re.sub(r"[\s<>〈〉《》]", "", event["title"]).casefold())
        if key not in groups:
            groups[key] = dict(event, identities=list(event["identities"]), sources=list(event["sources"]))
        else:
            merged = groups[key]
            merged["identities"] += event["identities"]
            merged["sources"] = sorted(set(merged["sources"] + event["sources"]))
            for field in ("detail", "location", "link"):
                merged[field] = merged[field] or event[field]
    return list(groups.values())


def build_feed(events, feed, previous, now):
    aliases = dict(previous.get("aliases", {}))
    records = dict(previous.get("records", {}))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SCENE-FLIX//Schedule//KO", "CALSCALE:GREGORIAN", "X-WR-CALNAME:" + escape("SCENE-FLIX · " + SOURCES[feed]), "X-WR-TIMEZONE:Asia/Seoul"]
    used = set()
    for event in sorted(events, key=lambda e: (e["start"], e["identities"])):
        uid = next((aliases[i] for i in event["identities"] if i in aliases and aliases[i] not in used), None)
        if not uid:
            uid = digest([feed, event["identities"]]) + "@scene-flix"
            if uid in used:
                uid = digest([feed, event]) + "@scene-flix"
        used.add(uid)
        for identity in event["identities"]:
            aliases[identity] = uid
        fingerprint = digest({k: v for k, v in event.items() if k != "identities"})
        old = records.get(uid)
        revision = old if old and old["fingerprint"] == fingerprint else {"fingerprint": fingerprint, "sequence": old["sequence"] + 1 if old else 0, "modified": stamp(now)}
        records[uid] = revision
        lines += ["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + revision["modified"], "LAST-MODIFIED:" + revision["modified"], "SEQUENCE:" + str(revision["sequence"]), "DTSTART" + (";VALUE=DATE:" if event["allDay"] else ":") + event["start"]]
        if event["end"]:
            lines.append("DTEND" + (";VALUE=DATE:" if event["allDay"] else ":") + event["end"])
        description = "\n".join(filter(None, [event["detail"], "출처: " + " · ".join(SOURCES[s] for s in event["sources"]), event["link"]]))
        lines += ["SUMMARY:" + escape(event["title"]), "DESCRIPTION:" + escape(description)]
        if event["location"]:
            lines.append("LOCATION:" + escape(event["location"]))
        if event["link"]:
            lines.append("URL:" + event["link"])
        lines += ["STATUS:CONFIRMED", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(map(fold, lines)) + "\r\n", {"aliases": aliases, "records": records}


def publish_calendars(root, now=None):
    folder = Path(root) / "data" / "schedule"
    files = sorted(folder.glob("schedule_????_h[12].json"))
    if not files:
        raise ValueError("No schedule data; refusing to publish empty calendars")
    items = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise ValueError("Invalid schedule file: " + path.name)
        items.extend(data["events"])
    events = collect_events(items)
    state_path = folder / "calendar-state.json"
    previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    now = now or datetime.now(timezone.utc)
    state, feeds = {}, {}
    for source in SOURCES:
        selected = combine(events) if source == "all" else [e for e in events if e["sources"] == [source]]
        feeds[source], state[source] = build_feed(selected, source, previous.get(source, {}), now)
    write_text(state_path, json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    for source, content in feeds.items():
        write_text(folder / (source + ".ics"), content)
    return {source: body.count("BEGIN:VEVENT") for source, body in feeds.items()}


if __name__ == "__main__":
    print(publish_calendars(Path(__file__).resolve().parent.parent))
