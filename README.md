# 지원콕 — 소상공인 지원사업 검색

가게를 운영 중인 사장님이 동네·업종·필요한 지원을 고르면, 지금 접수 중인 정부·지자체 지원사업을 추려 보여주는 페이지.
공고 수집은 [djfksjd/sole-search](https://github.com/djfksjd/sole-search) (MIT)의 크롤러를 그대로 쓴다.

- 주소: https://tools.gomstem.io/jiwonkok (곰툴스 허브가 https://gomstem.github.io/jiwonkok/ 를 이어 준다)
- 레포: https://github.com/GoMStem/jiwonkok (GitHub Pages 무료 사용을 위해 공개 레포)
- 미리보기(Claude Artifact, 비공개): https://claude.ai/artifact/SN1nHzXycgNsfVmoYL82Bu

## 매일 자동 업데이트

`.github/workflows/daily.yml` 이 매일 07:00(KST)에 공고를 새로 모아 GitHub Pages 에 배포한다.
main 에 push 해도 한 번 돈다. 수동 실행: GitHub → Actions → daily → Run workflow.
수집 건수가 모자라면(소상공인24 1,000건·기업마당 800건 미만, 한 번 재시도 후) 실패로 끝나고 전날 페이지가 그대로 남는다.
실패하면 GitHub 이 이메일로 알려준다.

## 구조

- `src/page.html` — 페이지 원본. 수정은 여기서 한다. `/*__DATA__*/null` 자리에 공고 데이터가 들어간다
- `build.py` — 공고 정리 + `page.html` 생성
- `src/og.html` → `static/og.png` — 카카오톡 공유 미리보기 이미지(1200×630). `og.html`을 고친 뒤 아래 명령으로 다시 찍는다
  `chrome --headless=new --hide-scrollbars --force-device-scale-factor=1 --window-size=1200,630 --virtual-time-budget=8000 --screenshot=static/og.png src/og.html`
  카카오톡은 미리보기를 캐시하므로, 바꾼 뒤에는 카카오 개발자 사이트의 공유 디버거에서 캐시를 지운다
- `src/web-head.html` — 웹 배포용 `<head>` 추가분 (charset, viewport, 공유 미리보기)
- `page.html` — Artifact 미리보기용 결과물 / `dist/index.html` — 웹 배포용 결과물. 둘 다 직접 고치지 않는다
- `data/raw/*.jsonl` — 크롤러가 받은 원본 / `data/programs.json` — 정리된 공고
- `vendor/sole-search/` — 크롤러 (git clone, 레포에는 올리지 않는다. 워크플로가 고정 커밋으로 받는다)

## 공고 새로 받기

```
python build.py --crawl
```

2~3분 걸린다. 소상공인24(약 1,800건)와 기업마당(약 1,500건)을 받아서 정리한다:
두 곳에 같이 올라온 공고 합치기, 마감 공고·운영기관 모집·개인 대출(학자금·주택 등) 빼기,
제목·기관에서 지역(시도·시군구)·지원 종류·대상(소상공인/중소기업) 분류.

## 왜 브라우저에서 바로 검색하지 않나

소상공인24·기업마당은 다른 사이트의 브라우저 요청(CORS)을 받지 않고, 소상공인24는 공식 공개 API도 아니다.
그래서 서버(또는 내 PC)에서 모아 둔 공고를 페이지에 넣고, 검색·필터는 브라우저에서 한다.

## 분류의 한계

- 제목과 기관 이름만 본다. 업력·매출·직원 수 자격은 판정하지 않는다 (페이지에도 그렇게 적었다)
- 소상공인24 공고는 지역 정보가 비어 있어 제목에서 찾는다. 제목에 지역이 없으면 '전국'으로 보인다

## 다음 할 일

