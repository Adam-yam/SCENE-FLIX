<div align="center">
  <img src="image/Logo.png" alt="SCENE-FLIX" width="560" />

  <br />

  <strong>RESCENE의 영상, 일정, 뉴스, 음원 차트를 한곳에서.</strong>

  <br /><br />

  <a href="https://adam-yam.github.io/SCENE-FLIX/">
    <img src="https://img.shields.io/badge/SCENE--FLIX-바로가기-111111?style=for-the-badge" alt="SCENE-FLIX 바로가기" />
  </a>
  <img src="https://img.shields.io/badge/Platform-Web-222222?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Web" />
  <img src="https://img.shields.io/badge/PWA-Supported-222222?style=for-the-badge&logo=pwa&logoColor=white" alt="PWA" />

  <br /><br />

  <sub>RESCENE(리센느)를 위한 비공식 팬메이드 아카이브</sub>
</div>

---

## 🎬 SCENE-FLIX

**SCENE-FLIX**는 걸그룹 **RESCENE(리센느)**의 다양한 영상과 관련 정보를 한곳에서 편리하게 볼 수 있도록 만든 팬메이드 웹 아카이브입니다.

음악방송 무대부터 자체 콘텐츠, 라이브, 외부 출연 영상, Shorts까지 카테고리별로 모아볼 수 있으며, **스케줄 · 뉴스 · 음원 차트**도 함께 확인할 수 있습니다.

> 별도의 설치 없이 웹에서 바로 이용할 수 있습니다.

### 🌐 바로가기

**[SCENE-FLIX 열기 →](https://adam-yam.github.io/SCENE-FLIX/)**

---

## ✨ 주요 기능

| 기능 | 설명 |
| --- | --- |
| 🎥 **영상 아카이브** | 음악방송, 자체 콘텐츠, Live, 외부 콘텐츠 등을 한곳에서 탐색 |
| 🔎 **검색 및 필터** | 카테고리, 멤버, 영상 유형 등을 기준으로 원하는 콘텐츠 탐색 |
| ⭐ **즐겨찾기** | 마음에 드는 영상을 저장하고 즐겨찾기 목록으로 관리 |
| ▶️ **재생목록 재생** | 즐겨찾기한 영상을 연속 재생 목록으로 활용 |
| 📱 **Shorts** | 공식 채널 및 여러 채널의 Shorts를 세로형 UI로 탐색 |
| 📅 **스케줄** | RESCENE 관련 일정을 캘린더와 목록 형태로 확인 |
| 📰 **뉴스** | 관련 최신 뉴스 데이터를 카드 형태로 확인 |
| 📊 **음원 차트** | 여러 음원 플랫폼의 순위와 변동 정보를 한눈에 확인 |
| 🌏 **다국어 지원** | 한국어 · 일본어 · 영어 UI 지원 |
| 📱 **반응형 UI** | PC, 태블릿, 모바일 화면에 맞춰 자동 최적화 |
| 💾 **PWA 지원** | 지원 환경에서 홈 화면에 추가하여 앱처럼 사용 가능 |

---

## 🗂️ 콘텐츠 구성

SCENE-FLIX에서는 콘텐츠를 다음과 같이 구분해 제공합니다.

- **음악방송** — M Countdown, Music Bank 등 무대 영상
- **자체 콘텐츠** — RESCENE 공식 채널의 자체 제작 영상
- **Live** — 라이브 방송 및 관련 영상
- **외부 콘텐츠** — 외부 채널 출연, 인터뷰, 협업 콘텐츠 등
- **Shorts** — 공식 및 관련 채널의 세로형 Shorts 영상
- **스케줄** — RESCENE 관련 일정
- **뉴스** — 관련 기사 및 소식
- **차트** — 음원 플랫폼별 순위 정보

---

## 📸 Preview

### Desktop

<div align="center">
  <img src="https://github.com/user-attachments/assets/bf461c1f-0c57-4db2-bce7-bf2b35b305f8" alt="SCENE-FLIX Desktop" width="820" />
</div>

<br />

### Mobile

<div align="center">
  <img src="https://github.com/user-attachments/assets/1e5e3918-e072-4bfe-9695-a018c6490c5d" alt="SCENE-FLIX Mobile" width="280" />
</div>

---

## 🚀 사용 방법

1. **[SCENE-FLIX](https://adam-yam.github.io/SCENE-FLIX/)**에 접속합니다.
2. 상단 또는 하단 메뉴에서 원하는 카테고리를 선택합니다.
3. 검색과 필터를 이용해 원하는 콘텐츠를 찾습니다.
4. 영상을 선택하면 해당 콘텐츠를 바로 시청할 수 있습니다.
5. 자주 보는 영상은 **즐겨찾기**에 저장해 다시 빠르게 찾을 수 있습니다.

### 모바일에서 앱처럼 사용하기

SCENE-FLIX는 PWA를 지원합니다. 브라우저가 지원하는 경우 **홈 화면에 추가**하여 일반 앱과 비슷하게 실행할 수 있습니다.

---

## 📊 데이터 관리

사이트에서 사용하는 일정, 뉴스, Shorts, 음원 차트 데이터는 `data/` 디렉터리의 JSON 파일을 기반으로 표시됩니다.

Python 크롤러와 GitHub Actions 워크플로우를 통해 필요한 데이터를 갱신할 수 있습니다.

| Workflow | 역할 |
| --- | --- |
| `chart-crawl.yml` | 음원 플랫폼 차트 데이터 갱신 |
| `crawl-shorts.yml` | 공식 및 관련 채널 Shorts 데이터 갱신 |
| `schedule.yml` | 스케줄 및 뉴스 데이터 갱신 |

> 현재 저장소의 워크플로우는 `workflow_dispatch` 방식으로 구성되어 있어 GitHub Actions에서 수동 실행할 수 있습니다.

### 사용되는 외부 API / Secrets

일부 데이터 수집 기능에는 다음 GitHub Secrets가 필요할 수 있습니다.

```text
YOUTUBE_API_KEY
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
```

---

## 🛠️ Tech Stack

<div align="center">

![HTML5](https://img.shields.io/badge/HTML5-202020?style=flat-square&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-202020?style=flat-square&logo=css&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-202020?style=flat-square&logo=javascript&logoColor=white)
![Python](https://img.shields.io/badge/Python-202020?style=flat-square&logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-202020?style=flat-square&logo=githubactions&logoColor=white)
![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-202020?style=flat-square&logo=github&logoColor=white)

</div>

- **Frontend** — HTML, CSS, Vanilla JavaScript
- **Data** — JSON
- **Crawler** — Python
- **Automation** — GitHub Actions
- **Hosting** — GitHub Pages
- **PWA** — Web App Manifest, Service Worker

---

## 📁 프로젝트 구조

```text
SCENE-FLIX/
├── index.html
├── manifest.json
├── service-worker.js
│
├── image/
│   ├── Logo.png
│   ├── favicon.png
│   ├── icon-192.png
│   ├── icon-512.png
│   └── ...
│
├── data/
│   ├── charts/
│   │   └── chart.json
│   ├── schedule/
│   ├── news.json
│   ├── shorts.json
│   └── *-shorts.json
│
├── crawlers/
│   ├── crawl_chart.py
│   ├── crawl_schedule.py
│   ├── crawl_shorts.py
│   └── requirements.txt
│
└── .github/
    └── workflows/
        ├── chart-crawl.yml
        ├── crawl-shorts.yml
        └── schedule.yml
```

---

## 💬 문의 및 피드백

버그 제보, 누락된 영상, 콘텐츠 수정·삭제 요청, 기능 제안 등은 아래 이메일로 전달해주세요.

📧 **sceneflix.may@gmail.com**

---

## ⚠️ 안내

SCENE-FLIX는 **RESCENE을 응원하기 위해 제작된 비공식 팬메이드 프로젝트**이며, 더뮤즈엔터테인먼트 및 RESCENE의 공식 서비스가 아닙니다.

본 프로젝트는 비영리 목적으로 운영되며 광고를 목적으로 하지 않습니다. 사이트에서 연결하거나 소개하는 영상, 이미지, 기사 및 기타 콘텐츠의 저작권은 각 원저작자와 권리자에게 있습니다.

권리자의 요청이 있을 경우 관련 콘텐츠는 수정 또는 삭제될 수 있습니다.

---

<div align="center">
  <strong>SCENE-FLIX</strong><br />
  <sub>Made for RESCENE · Fan-made & Non-commercial</sub>
</div>
