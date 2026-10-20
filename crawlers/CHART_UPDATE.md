# 차트 업데이트

## 반영 사항

- VIBE의 상승·하락값으로 이전 순위를 계산하는 방향 수정. 신규 진입 플래그도 반영.
- 지니 1·2페이지를 합쳐 실제 1~200위 수집. 페이지 집계 시간이 다르거나 순위가 중복·누락되면 실패 처리.
- 멜론·벅스·VIBE·FLO·Apple Music은 100개, YouTube는 100개, Spotify는 200개 전체 차트를 검증한 뒤 대상 가수 곡 추출.
- Apple Music 공식 한국 most-played RSS 사용. 전체 곡 ID 순서의 해시로 동일 차트를 식별. 최초 관측은 NEW로 표시하지 않음. 이전 순위는 직전의 서로 다른 성공 수집 차트와 비교하며 공식 전일 등락을 뜻하지 않음.
- NEW는 출처의 명시적 신규 진입 또는 Apple의 이전 관측 차트와 비교해 진입이 확인된 경우에만 표시. Kworb 재진입은 RE로 표시. 이전 순위가 없다는 이유만으로 신규 진입으로 표시하지 않음.
- 출처 URL, 집계 기준, 원본 시각/기간, 수집 상태를 JSON에 기록. 날짜 역행·미래 시각·불완전 응답을 검증.
- 일부 플랫폼 실패 시 기존 순위 유지. 정상 수집 결과 대상 곡이 0개면 해당 플랫폼의 이전 순위 제거. 전체 실패 시 파일을 보존하고 종료 코드 1 반환.
- 재시도, 타임아웃, 앨범 이미지 캐시 재사용, 이미지 검색 결과의 가수·제목 검증, 원자적 파일 저장.
- index.html의 제목 15px(좁은 화면 13px), BETA 제거, Spotify 표기 유지. Apple Music 포함 8개 플랫폼과 좁은 화면 4×2 배치. 출처·집계 기준을 순위 툴팁에 표시. YouTube·Spotify의 Kworb 출처는 차트 안내에도 표시.

## 플랫폼별 출처

| 플랫폼 | 수집 출처 | 범위 |
|---|---|---|
| 멜론 | m2.melon.com/m6/chart/ent/songChartList.json | TOP100 |
| 지니 | app.genie.co.kr/chart/j_RealTimeRankSongList.json, pg=1·2 | 실시간 TOP200 |
| VIBE | apis.naver.com/vibeWeb/musicapiweb/vibe/v1/chart/track/total | 오늘 Top100 |
| 벅스 | m.bugs.co.kr/api/getChartTrack, realtime | 실시간 TOP100 |
| FLO | api.music-flo.com/display/v1/browser/chart/1/list?mixYn=N | 24시간 집계 TOP100 |
| YouTube Music | https://kworb.net/youtube/insights/kr.html | 한국 주간 인기곡100 |
| Spotify | https://kworb.net/spotify/country/kr_daily.html | 한국 일간200 |
| Apple Music | https://rss.applemarketingtools.com/api/v2/kr/music/most-played/100/songs.json | 한국 인기곡100 |

국내 5개 플랫폼은 공식 도메인이지만 공개 지원이 보장되는 API는 아닙니다. Apple은 공식 RSS입니다. YouTube·Spotify 공식 차트 페이지의 공개 HTML에는 순위 데이터가 없어 자동 대조를 검증하지 못했습니다. 두 플랫폼은 Kworb를 유지하고 `verification: not_compared_with_official`로 기록합니다. 공식 검증을 완료한 데이터로 간주하지 않습니다.

원본 날짜가 없는 지니·FLO는 제공된 시간/기간만 보존하고 freshness를 unknown으로 기록합니다. current는 설정한 허용 기간 이내라는 뜻이며 최신 공식 차트와 대조했다는 뜻이 아닙니다. 허용 기간은 멜론·벅스 6시간, VIBE 48시간, Apple·Spotify 72시간, YouTube 주간 차트 240시간입니다. 초과하면 stale로 표시합니다. 모든 요청이 실패해 파일을 보존한 경우에는 실패 상태도 새로 저장되지 않으므로 Actions 실패와 기존 수집 시각을 확인해야 합니다.

## 적용 및 실행

수정 대상: `index.html`, `crawlers/crawl_chart.py`, `.github/workflows/chart-crawl.yml`, `data/charts/chart.json`. 문서와 `crawlers/tests/test_crawl_chart.py`도 함께 보관하는 것을 권장합니다.

```sh
pip install requests pandas lxml
python -m unittest discover -s crawlers/tests -v
python crawlers/crawl_chart.py
```

workflow는 기존처럼 수동 실행입니다. 자동 실행 일정은 추가하지 않았습니다. JSON 기존 구조는 유지하며 platformStatus 및 순위별 isNew/isReentry를 추가했습니다.

## 검증 결과

- 크롤러 자동 테스트 16개 통과: 순위 검증, 중복·누락, VIBE 등락, 지니 두 페이지 일관성, Apple 첫 관측·동일 차트, 날짜 유효성, 전체 실패 보존, 부분 실패와 정상 0건 구분, Kworb 파싱, 이미지 오매칭, 손상된 기존 JSON 보호.
- 2026-10-17 11:25 KST 실제 수집에서 8개 플랫폼 모두 성공. 추출 곡 수: 멜론5 / 지니5 / VIBE3 / 벅스5 / FLO5 / YouTube7 / Spotify5 / Apple5. 합친 결과 7곡을 chart.json에 반영.
- 프런트엔드 Node VM 검사: 실제 JSON, 8개 플랫폼, 정상·미연동·실패·이전 정보, HTML 이스케이프, 한·영·일, NEW/RE/이전 순위 불명 구분, 기존 로더·초기 탭 유지 통과.
- 브라우저 실화면 및 GitHub Actions 실행은 이 환경에서 검증하지 못했습니다. 외부 서비스 변경이나 장애까지 무오류를 보장하지는 않습니다.
