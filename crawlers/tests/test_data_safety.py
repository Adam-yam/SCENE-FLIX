import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import crawl_schedule as schedule
import crawl_shorts as shorts
from storage import atomic_json


class DataSafetyTests(unittest.TestCase):
    def test_korean_date_rollover(self):
        event = {'startAt': '2026-10-18T16:30:00Z', 'allDay': False}
        self.assertEqual(schedule.extract_date(event), '2026-10-19')
        self.assertEqual(schedule.extract_time(event), '01:30')

    def test_offset_and_midnight(self):
        event = {'startAt': '2026-10-19T00:00:00+09:00', 'allDay': False}
        self.assertEqual(schedule.extract_date(event), '2026-10-19')
        self.assertEqual(schedule.extract_time(event), '00:00')

    def test_all_day(self):
        event = {'allDay': True, 'startAtAllDay': '2026-10-19'}
        self.assertEqual(schedule.extract_date(event), '2026-10-19')
        self.assertEqual(schedule.extract_time(event), '')

    def schedule_result(self, first, second=None):
        today = datetime.now(schedule.KST)
        prefix = today.strftime('%Y-%m')
        old = {'date': prefix + '-10', 'title': 'Event', 'time': '12:00', 'source': 'mnetplus'}
        manual = {**old, 'title': 'Manual', 'source': 'manual'}
        with patch.object(schedule, 'crawl_schedule_month', side_effect=[first(prefix), second]), patch.object(schedule, '_load_half_schedule', return_value=[old, manual]):
            result = schedule.run_schedule_crawler()
        return result, old, manual

    def test_corrected_event_replaces_old(self):
        result, old, manual = self.schedule_result(lambda p: [{'date': p+'-10', 'title': 'Event', 'time': '15:00', 'source': 'mnetplus'}])
        items = next(iter(result.values()))
        self.assertEqual([e['time'] for e in items if e['title']=='Event'], ['15:00'])
        self.assertIn(manual, items)

    def test_confirmed_empty_removes_only_official_month(self):
        result, old, manual = self.schedule_result(lambda p: [])
        self.assertEqual(next(iter(result.values())), [manual])

    def test_failed_month_does_not_replace(self):
        result, _, _ = self.schedule_result(lambda p: None)
        self.assertEqual(result, {})

    def test_news_missing_credentials_keeps_file(self):
        with patch.object(schedule, 'NAVER_CLIENT_ID', ''):
            self.assertIsNone(schedule.run_news_crawler())

    def test_news_partial_failure_is_not_published(self):
        with patch.object(schedule, 'NAVER_CLIENT_ID', 'present'), patch.object(schedule, 'NAVER_CLIENT_SECRET', 'present'), patch.object(schedule, 'crawl_naver_api', side_effect=[[{'title':'Existing'}], None]), patch.object(schedule.time, 'sleep'):
            self.assertIsNone(schedule.run_news_crawler())

    def test_shorts_channel_failure_preserves_previous(self):
        old = {'vid': 'abcdefghijk', 'channel': 'official', 'date': '2026.10.01', 'title': 'Old'}
        new = {'vid': 'lmnopqrstuv', 'channel': 'woni', 'date': '2026.10.02', 'title': 'New'}
        with patch.object(shorts, '_load_existing_shorts', return_value={old['vid']:old}), patch.object(shorts, 'crawl_shorts_channel', side_effect=[[], [new]]), patch.object(shorts.time, 'sleep'):
            self.assertEqual(shorts.run_shorts_crawler()['items'], [new, old])

    def test_all_shorts_sources_fail_no_replacement(self):
        with patch.object(shorts, '_load_existing_shorts', return_value={}), patch.object(shorts, 'crawl_shorts_channel', return_value=[]), patch.object(shorts.time, 'sleep'):
            self.assertIsNone(shorts.run_shorts_crawler())

    def test_missing_short_date_retried(self):
        old = {'vid': 'abcdefghijk', 'channel': 'official', 'date': '', 'title': 'Old'}
        with patch.object(shorts, '_fetch_shorts_vids', return_value=[{'id':old['vid']}]), patch.object(shorts, '_fetch_publish_dates', return_value={old['vid']:{'date':'2026.10.19','title':'New'}}) as fetch:
            items = shorts.crawl_shorts_channel('official', 'unused', {old['vid']:old})
            self.assertEqual(items[0]['date'], '2026.10.19')
            self.assertEqual(old['date'], '')
            fetch.assert_called_once()

    def test_atomic_write_failure_preserves_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'data.json'
            path.write_text('{"old":true}')
            with patch('storage.os.replace', side_effect=OSError('blocked')):
                with self.assertRaises(OSError): atomic_json(path, {'new':True})
            self.assertEqual(json.loads(path.read_text()), {'old':True})
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_manifest_matches_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root/'data/schedule';path.mkdir(parents=True)
            (path/'schedule_2026_h1.json').write_text('{"events":[]}')
            with patch.object(schedule, 'ROOT', root), patch.object(schedule, 'run_schedule_crawler', return_value={}), patch.object(schedule, 'run_news_crawler', return_value=None):
                schedule.main()
            self.assertEqual(json.loads((path/'manifest.json').read_text())['files'], ['schedule_2026_h1.json'])
            self.assertFalse((root/'data/news.json').exists())

if __name__ == '__main__':
    unittest.main()
