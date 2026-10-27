import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1]))
import crawl_schedule as c


def record(**kw):
    return {"scheduleId":123,"unitId":133,"idHash":"abcd1234","title":"<테스트 일정>","typeId":1,"startTime":"2026-10-27T15:30:00Z","endTime":"2026-10-27T16:30:00Z","isAllday":False,"extField":{"key":"장소","value":"서울"},**kw}


def page(records, month=10, status='success'):
    data='1:'+json.dumps({'queries':[{'queryKey':['schedule',2026,month,133],'state':{'status':status,'data':records}}]},ensure_ascii=False)+'\n'
    at=len(data)//2
    return ''.join('<script>self.__next_f.push('+json.dumps([1,x],ensure_ascii=False)+')</script>' for x in [data[:at],data[at:]])


class BlipTests(unittest.TestCase):
    def test_hydration_kst_and_location(self):
        events=c.parse_blip_page(page([record()]),2026,10)
        self.assertEqual(len(events),1)
        ev=events[0]
        self.assertEqual((ev['date'],ev['time'],ev['title'],ev['source']),('2026-10-28','00:30','테스트 일정','blip'))
        self.assertEqual(ev['location'],'서울')
        self.assertEqual(ev['link'],'https://s.blip.kr/s/abcd1234')

    def test_inclusive_period_clipped_to_month(self):
        ev=record(startTime='2026-09-29T15:00:00Z',endTime='2026-10-02T15:00:00Z',isAllday=True)
        items=c.parse_blip_page(page([ev]),2026,10)
        self.assertEqual([x['date'] for x in items],['2026-10-01','2026-10-02','2026-10-03'])
        self.assertTrue(all(x['time']=='' for x in items))

    def test_empty_and_bad_responses(self):
        self.assertEqual(c.parse_blip_page(page([]),2026,10),[])
        for value in ['<html>Login</html>',page([],month=11),page([],status='error'),page([record(unitId=2)]),page([record(startTime='bad')]),page([record(title='<>')])]:
            with self.assertRaises(ValueError):c.parse_blip_page(value,2026,10)

    def test_duplicate_and_conflicting_id(self):
        self.assertEqual(len(c.parse_blip_page(page([record(),record()]),2026,10)),1)
        with self.assertRaises(ValueError):c.parse_blip_page(page([record(),record(title='다른 일정')]),2026,10)

    def test_year_boundary(self):
        self.assertEqual(list(c.schedule_months(date(2026,12,1),[-1,0,1,2])),[(2026,11),(2026,12),(2027,1),(2027,2)])

    def test_source_failure_and_correction(self):
        today=datetime.now(c.KST).date();prefix=today.strftime('%Y-%m')
        old=[{'id':'1','date':prefix+'-10','time':'12:00','title':'Old','source':s} for s in ['mnetplus','blip','manual']]
        def blip(y,m):return [{**old[1],'title':'Corrected'}] if (y,m)==(today.year,today.month) else None
        with patch.object(c,'crawl_schedule_month',return_value=None),patch.object(c,'crawl_blip_month',side_effect=blip),patch.object(c,'_load_half_schedule',return_value=old):result=c.run_schedule_crawler()
        events=next(iter(result.values()))
        self.assertIn(old[0],events);self.assertIn(old[2],events);self.assertNotIn(old[1],events);self.assertIn({**old[1],'title':'Corrected'},events)

    def test_confirmed_empty_only_removes_source(self):
        today=datetime.now(c.KST).date();prefix=today.strftime('%Y-%m')
        old=[{'date':prefix+'-10','title':'Old','source':s} for s in ['mnetplus','blip','manual']]
        def blip(y,m):return [] if (y,m)==(today.year,today.month) else None
        with patch.object(c,'crawl_schedule_month',return_value=None),patch.object(c,'crawl_blip_month',side_effect=blip),patch.object(c,'_load_half_schedule',return_value=old):result=c.run_schedule_crawler()
        self.assertEqual({x['source'] for x in next(iter(result.values()))},{'mnetplus','manual'})


if __name__=='__main__':unittest.main()
