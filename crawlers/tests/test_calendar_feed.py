import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_feed import build_feed, collect_events, combine, publish_calendars


class CalendarTests(unittest.TestCase):
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)

    def event(self, **changes):
        return dict({"id": "1", "source": "mnetplus", "date": "2026-10-27", "time": "18:00", "title": "방송"}, **changes)

    def test_identity_updates_and_no_change(self):
        events = collect_events([self.event()])
        body, state = build_feed(events, "all", {}, self.now)
        again, next_state = build_feed(events, "all", state, self.now + timedelta(hours=1))
        self.assertEqual(body, again)
        self.assertEqual(state, next_state)
        edited = collect_events([self.event(date="2026-10-28", title="수정된 방송")])
        changed, updated = build_feed(edited, "all", state, self.now + timedelta(hours=1))
        self.assertEqual(state["aliases"], updated["aliases"])
        self.assertIn("SEQUENCE:1", changed)
        self.assertIn("DTSTART:20261028T090000Z", changed)

    def test_period_end_and_timezone(self):
        rows = [self.event(source="blip", date="2026-10-27", time="", allDay=True), self.event(source="blip", date="2026-10-28", time="", allDay=True)]
        events = collect_events(rows)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["end"], "20261029")
        full = collect_events([self.event(source="blip", time="", allDay=True, start="2026-09-29T00:00:00+09:00", end="2026-11-02T23:59:00+09:00")])[0]
        self.assertEqual((full["start"], full["end"]), ("20260929", "20261103"))
        timed = collect_events([self.event(end="2026-10-27T19:00:00+09:00", endTimeHidden=True)])[0]
        self.assertEqual(timed["end"], "")

    def test_escaping_and_utf8_folding(self):
        body, _ = build_feed(collect_events([self.event(title="한글" * 100 + ",;\\\nEND:VEVENT")]), "all", {}, self.now)
        self.assertTrue(all(len(line.encode()) <= 75 for line in body.split("\r\n")))
        self.assertEqual(body.count("\r\nEND:VEVENT\r\n"), 1)
        self.assertIn("\\,\\;", body.replace("\r\n ", ""))
        self.assertIn("\\nEND:VEVENT", body.replace("\r\n ", ""))

    def test_merge_and_split_keep_unique_ids(self):
        mnet, blip = self.event(), self.event(source="blip", id="2")
        _, state = build_feed(collect_events([mnet]), "all", {}, self.now)
        merged = combine(collect_events([mnet, blip]))
        self.assertEqual(len(merged), 1)
        _, next_state = build_feed(merged, "all", state, self.now)
        self.assertEqual(state["aliases"]["mnetplus:1"], next_state["aliases"]["blip:2"])
        blip["title"] = "다른 방송"
        body, split = build_feed(combine(collect_events([mnet, blip])), "all", next_state, self.now)
        self.assertEqual(body.count("BEGIN:VEVENT"), 2)
        self.assertNotEqual(split["aliases"]["mnetplus:1"], split["aliases"]["blip:2"])

    def test_publish_source_isolation_deletion_and_corrupt_input(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "data" / "schedule"
            folder.mkdir(parents=True)
            data = folder / "schedule_2026_h2.json"
            data.write_text(json.dumps({"events": [self.event(), self.event(source="blip", id="2", title="팬사인회")]}))
            counts = publish_calendars(directory, self.now)
            self.assertEqual(counts, {"all": 2, "mnetplus": 1, "blip": 1})
            self.assertNotIn("팬사인회", (folder / "mnetplus.ics").read_text())
            original = (folder / "all.ics").read_bytes()
            publish_calendars(directory, self.now + timedelta(hours=1))
            self.assertEqual(original, (folder / "all.ics").read_bytes())
            data.write_text('{"events":')
            with self.assertRaises(ValueError):
                publish_calendars(directory, self.now)
            self.assertEqual(original, (folder / "all.ics").read_bytes())
            data.write_text('{"events":[]}')
            self.assertEqual(publish_calendars(directory, self.now)["all"], 0)
            self.assertNotIn("BEGIN:VEVENT", (folder / "all.ics").read_text())

    def test_invalid_input_rejected(self):
        for changes in [{"date": "bad"}, {"time": "25:00"}, {"title": ""}, {"start": "2026-10-27T18:00:00"}]:
            with self.assertRaises(ValueError):
                collect_events([self.event(**changes)])


if __name__ == "__main__":
    unittest.main()
