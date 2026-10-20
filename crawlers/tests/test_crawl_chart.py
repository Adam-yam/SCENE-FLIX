import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('crawl_chart', Path(__file__).parents[1] / 'crawl_chart.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def entry(rank=5):
    return dict(songName='Love Attack', artistName='RESCENE', albumImageUrl='https://example.com/a.jpg', rank=rank, previousRank=8)


def previous():
    return dict(updatedAt='2026-10-16T10:00:00+09:00', platforms=['melon', 'apple_music'], songs=c.merge_platform_results({'melon': [entry()], 'apple_music': [entry(7)]}))


class ChartTests(unittest.TestCase):
    def setUp(self):
        c.SOURCE_META.clear()

    def test_freshness(self):
        now = c.datetime(2026, 10, 17, 12, tzinfo=c.KST)
        self.assertEqual(c.source_freshness('melon', {}, now), 'unknown')
        self.assertEqual(c.source_freshness('melon', {'sourceUpdatedAt': now.isoformat()}, now), 'current')
        self.assertEqual(c.source_freshness('melon', {'sourceUpdatedAt': (now-c.timedelta(hours=7)).isoformat()}, now), 'outdated')
        with self.assertRaises(ValueError):
            c.source_freshness('melon', {'sourceUpdatedAt': (now+c.timedelta(hours=2)).isoformat()}, now)
        self.assertIsNotNone(c.parse_source_date('Sat, 17 Oct 2026 01:00:00 GMT').tzinfo)

    def test_incomplete_and_duplicate_charts_rejected(self):
        for ranks, ids in [([1, 1], ['a', 'b']), ([1, 2], ['a', 'a']), ([1], ['a'])]:
            with self.assertRaises(ValueError):
                c.validate_chart([{}]*len(ranks), 2, ranks, ids)

    def test_vibe_variation_and_new(self):
        tracks = [dict(trackId=i, trackTitle=f'Song {i}', artists=[{'artistName': 'RESCENE'}], rank={'currentRank': i, 'rankVariation': 7, 'isNew': False}) for i in range(1, 101)]
        tracks[1]['rank']['rankVariation'] = -1
        tracks[2]['rank']['isNew'] = True
        data = {'response': {'result': {'chart': {'date': 1792188000000, 'items': {'tracks': tracks}}}}}
        with patch.object(c, 'request_json', return_value=data):
            result = c.fetch_vibe()
        self.assertEqual(result[0]['previousRank'], 8)
        self.assertEqual(result[1]['previousRank'], 1)
        self.assertIsNone(result[2]['previousRank'])
        self.assertTrue(result[2]['isNew'])

    def test_genie_full_200_and_mixed_hours(self):
        pages = [{'PageInfo': {'ChartTime': '11:00'}, 'DataSet': {'DATA': [dict(RANK_NO=i, SONG_ID=i, SONG_NAME=f'Song {i}', ARTIST_NAME='RESCENE', PRE_RANK_NO=i) for i in range(start, start+100)]}} for start in (1, 101)]
        with patch.object(c, 'request_json', side_effect=pages):
            self.assertEqual(c.fetch_genie()[-1]['rank'], 200)
        pages[1]['PageInfo']['ChartTime'] = '12:00'
        with patch.object(c, 'request_json', side_effect=pages):
            with self.assertRaises(ValueError): c.fetch_genie()

    def test_apple_first_observation_is_not_new(self):
        rows = [entry()]
        c.SOURCE_META['apple_music'] = {'sourceRevision': 'new'}
        c.apple_previous_ranks(rows, {})
        self.assertIsNone(rows[0]['isNew'])
        c.apple_previous_ranks(rows, {'platformStatus': {'apple_music': {'sourceRevision': 'old'}}, 'songs': []})
        self.assertTrue(rows[0]['isNew'])

    def test_kworb_incomplete_rejected(self):
        response = Mock(text='<table><tr><th>Pos</th><th>Chg</th><th>Song</th></tr><tr><td>1</td><td>NEW</td><td>RESCENE - Pinball</td></tr></table>')
        with patch.object(c.SESSION, 'get', return_value=response):
            with self.assertRaises(ValueError): c.fetch_spotify()

    def test_positive_rank(self):
        for v in [None, '', 0, -2, True, 'new', '2.5']:
            self.assertIsNone(c.positive_rank(v))
        self.assertEqual(c.positive_rank('23'), 23)

    def test_merge_best_duplicate(self):
        songs = c.merge_platform_results({'melon': [entry(8), entry(3)], 'apple_music': [entry(12)]})
        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0]['ranks']['melon']['rank'], 3)
        self.assertIn('apple_music', songs[0]['ranks'])

    def test_apple_full_positions(self):
        items = [dict(id=str(i), name='Love Attack' if i == 41 else f'Song {i}', artistName='RESCENE' if i == 41 else 'Other') for i in range(100)]
        response = Mock()
        response.json.return_value = {'feed': {'country': 'kr', 'updated': 'Sat, 17 Oct 2026 01:00:00 GMT', 'results': items}}
        with patch.object(c.SESSION, 'get', return_value=response):
            self.assertEqual(c.fetch_apple_music()[0]['rank'], 42)
            self.assertIn('sourceRevision', c.SOURCE_META['apple_music'])

    def test_apple_invalid_feed(self):
        response = Mock()
        response.json.return_value = {'feed': {'country': 'kr', 'results': []}}
        with patch.object(c.SESSION, 'get', return_value=response):
            with self.assertRaises(ValueError): c.fetch_apple_music()

    def test_apple_comparison(self):
        c.SOURCE_META['apple_music'] = {'sourceRevision': 'new'}
        old = previous(); items = [entry(4)]
        c.apple_previous_ranks(items, old)
        self.assertEqual(items[0]['previousRank'], 7)
        old['platformStatus'] = {'apple_music': {'sourceRevision': 'new'}}
        c.apple_previous_ranks(items, old)
        self.assertEqual(items[0]['previousRank'], 8)

    def test_all_failed_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'chart.json'; raw = json.dumps(previous()); path.write_text(raw)
            with patch.object(c, 'OUTPUT_PATH', str(path)), patch.object(c, 'PLATFORM_FETCHERS', {'melon': Mock(side_effect=RuntimeError('offline'))}):
                self.assertEqual(c.main(), 1)
                self.assertEqual(path.read_text(), raw)

    def test_success_empty_drops_old_failure_keeps_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'chart.json'; path.write_text(json.dumps(previous()))
            with patch.object(c, 'OUTPUT_PATH', str(path)), patch.object(c, 'PLATFORM_FETCHERS', {'melon': Mock(side_effect=RuntimeError('offline')), 'apple_music': lambda: []}):
                self.assertEqual(c.main(), 0)
            result = json.loads(path.read_text())
            self.assertEqual(result['platformStatus']['melon']['status'], 'stale')
            self.assertEqual(result['songs'][0]['ranks']['melon']['rank'], 5)
            self.assertNotIn('apple_music', result['songs'][0]['ranks'])

    def test_kworb_artist_not_song_name(self):
        rows = ''.join(f'<tr><td>{i}</td><td>-3</td><td>{"RESCENE - Pinball" if i == 12 else "Other - RESCENE tribute"}</td></tr>' for i in range(1, 201))
        response = Mock(text='Spotify Daily Chart - South Korea - 2026/10/15<table><tr><th>Pos</th><th>Chg</th><th>Song</th></tr>' + rows + '</table>')
        with patch.object(c.SESSION, 'get', return_value=response):
            rows = c.fetch_kworb('https://example.com')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['previousRank'], 9)

    def test_unmatched_cover_ignored(self):
        response = Mock()
        response.json.return_value = {'results': [{'artistName': 'Other', 'trackName': 'Love Attack', 'artworkUrl100': 'wrong'}]}
        with patch.object(c.SESSION, 'get', return_value=response):
            self.assertEqual(c.fetch_album_image_itunes('RESCENE', 'Love Attack'), '')

    def test_corrupt_previous_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'chart.json'; path.write_text('{broken')
            with patch.object(c, 'OUTPUT_PATH', str(path)):
                with self.assertRaises(json.JSONDecodeError): c.main()
            self.assertEqual(path.read_text(), '{broken')


if __name__ == '__main__':
    unittest.main()
