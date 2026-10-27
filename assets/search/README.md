# 검색

Fuse.js 7.5.0과 es-hangul 2.4.0의 getChoseong을 포함한 자체 호스팅 번들입니다. 각 라이선스는 이 폴더에 포함되어 있습니다.

index.html과 search-v1.min.js를 함께 배포합니다. 평소 영상 목록을 수정할 때는 기존처럼 index.html만 수정하면 됩니다. 사용자에게 업데이트 알림을 보내거나 페이지를 새로고침하지 않습니다.

일반 영상과 쇼츠 검색은 정확한 일치, 초성 일치, 오타 유사도 순서로 표시하며 같은 점수에서는 기존 정렬을 유지합니다. 시리즈는 선택한 정렬, 일정은 날짜 순서를 유지합니다. 공백으로 나눈 단어는 모두 일치해야 합니다. 1~2글자, 숫자 포함 단어, 초성만으로 된 검색에는 오타 보정을 적용하지 않습니다. 일반 영상의 날짜 검색은 기존 규칙을 사용합니다. 한글과 영문 이름 사이의 자동 번역이나 별칭 추정은 하지 않습니다.

빌드 도구는 배포나 사이트 이용에 필요하지 않습니다. 번들을 다시 만들 때만 별도 작업 폴더에서 실행합니다.

```sh
npm install --save-exact fuse.js@7.5.0 es-hangul@2.4.0 esbuild@0.28.2
npx esbuild search.source.js --bundle --minify --format=iife --target=es2020 --legal-comments=none --outfile=search-v1.min.js
```

동작을 변경해 재배포할 때는 번들 파일 이름의 버전과 index.html의 경로를 함께 변경합니다.

```sh
node tests/site.test.cjs
node tests/search.test.cjs
```
