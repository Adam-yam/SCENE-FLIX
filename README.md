[README.md](https://github.com/user-attachments/files/32547771/README.md)
<div align="center">
  <img src="image/logo.png" alt="SCENE-FLIX" width="420" />
  <p><strong>리센느의 영상과 소식을 한곳에서.</strong></p>
  <p>RESCENE을 위한 비공식 팬메이드 아카이브</p>
  <p><a href="https://adam-yam.github.io/SCENE-FLIX/">사이트 바로가기 ↗</a></p>
</div>

## 소개

**SCENE-FLIX**는 RESCENE(리센느)의 영상, 스케줄, 뉴스, 음원 차트를 모아볼 수 있는 웹사이트입니다. 음악방송부터 자체 콘텐츠, 라이브, 외부 출연 영상과 Shorts까지 쉽게 찾아보고, 좋아하는 영상은 즐겨찾기로 모아둘 수 있습니다.

별도 설치 없이 PC와 모바일 브라우저에서 이용할 수 있습니다.

## 주요 기능

| 기능 | 설명 |
| --- | --- |
| 영상 탐색 | 음악방송 · 자체 콘텐츠 · Live · 외부 콘텐츠를 검색하고 카테고리와 멤버별로 필터링 |
| 즐겨찾기 | 좋아하는 영상을 저장하고 재생목록으로 감상 |
| Shorts | 공식 및 관련 채널의 Shorts를 세로형 화면으로 탐색 |
| 팬튜브 | 리마인들의 팬튜브 채널 모아보기 |
| 스케줄 · 뉴스 | 리센느의 일정과 관련 기사 확인 |
| 음원 차트 | 음원 플랫폼별 순위와 변동 확인 |
| 이용 환경 | 반응형 화면, 한국어 · 일본어 · 영어, 홈 화면 추가(PWA) 지원 |

## 미리보기

<p align="center">
  <img src="https://github.com/user-attachments/assets/bf461c1f-0c57-4db2-bce7-bf2b35b305f8" alt="SCENE-FLIX PC 화면" width="800" />
</p>

<details>
  <summary>모바일 화면 보기</summary>
  <p align="center">
    <img src="https://github.com/user-attachments/assets/1e5e3918-e072-4bfe-9695-a018c6490c5d" alt="SCENE-FLIX 모바일 화면" width="280" />
  </p>
</details>

## 이용 방법

1. **[SCENE-FLIX](https://adam-yam.github.io/SCENE-FLIX/)**에 접속합니다.
2. 메뉴에서 원하는 콘텐츠를 선택하고 검색이나 필터로 영상을 찾습니다.
3. 영상을 선택해 감상하고, 다시 보고 싶은 영상은 즐겨찾기에 저장합니다.

지원하는 브라우저에서는 **홈 화면에 추가**하여 앱처럼 실행할 수 있습니다. 즐겨찾기는 현재 브라우저에 저장되므로 다른 기기와 자동으로 동기화되지 않으며, 사이트 데이터를 삭제하면 초기화될 수 있습니다.

## 개발 및 데이터 관리

HTML · CSS · JavaScript로 구성된 정적 웹사이트이며, GitHub Pages로 배포합니다. 일정, 뉴스, Shorts, 음원 차트는 Python 크롤러로 수집한 JSON 데이터를 사용합니다.

| 경로 | 역할 |
| --- | --- |
| `index.html` | 사이트 화면과 주요 기능 |
| `image/` | 로고, 아이콘, 이미지 |
| `data/` | 일정, 뉴스, Shorts, 음원 차트 데이터 |
| `crawlers/` | 데이터 수집 스크립트 |
| `.github/workflows/` | 데이터 갱신 워크플로우 |
| `manifest.json` · `service-worker.js` | PWA 설정 및 캐시 처리 |

<details>
  <summary>데이터 갱신 방법</summary>

저장소의 **Actions** 탭에서 필요한 워크플로우를 선택한 뒤 **Run workflow**로 실행합니다. 현재 워크플로우는 수동 실행(`workflow_dispatch`) 방식이며, 데이터가 변경되면 저장소에 커밋합니다.

| 워크플로우 | 갱신 대상 | 사용하는 Repository Secrets |
| --- | --- | --- |
| `chart-crawl.yml` | 음원 차트 | 없음 |
| `crawl-shorts.yml` | 공식 채널 · 안원잘부 Shorts | `YOUTUBE_API_KEY` |
| `schedule.yml` | 스케줄 · 뉴스 | `YOUTUBE_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` |

API 키는 저장소의 **Settings → Secrets and variables → Actions**에 등록합니다.

</details>

## 문의

버그 제보, 누락된 영상, 기능 제안, 콘텐츠 수정·삭제 요청은 **[sceneflix.may@gmail.com](mailto:sceneflix.may@gmail.com)**으로 보내주세요.

## 안내

SCENE-FLIX는 RESCENE과 리마인을 위해 제작된 **비공식·비영리 팬메이드 프로젝트**이며, 더뮤즈엔터테인먼트 및 RESCENE의 공식 서비스가 아닙니다.

영상, 이미지, 기사 등 각 콘텐츠의 저작권은 원저작자와 권리자에게 있습니다. 권리자의 요청이 있을 경우 관련 콘텐츠를 수정하거나 삭제할 수 있습니다.
