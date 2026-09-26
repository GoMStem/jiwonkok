"""지원콕 데이터 빌드.

1) (--crawl) sole-search 크롤러로 소상공인24·기업마당 모집 공고를 data/raw/에 새로 받는다.
2) 받은 공고를 정리한다: 중복 제거, 마감된 공고 제외, 지역·지원 종류·대상 분류.
3) data/programs.json 을 쓰고, src/page.html 의 /*__DATA__*/ 자리에 넣어 page.html 을 만든다.

사용법:
  python build.py           # data/raw 에 있는 것으로 다시 만들기
  python build.py --crawl   # 새로 수집한 뒤 만들기 (2~3분)
"""
import html
import os
import json
import re
import subprocess
import sys
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
KST = timezone(timedelta(hours=9))
# 이보다 적게 모이면 수집이 잘못된 것으로 보고 페이지를 새로 만들지 않는다 (2026-09 기준 약 1,800 / 1,500건)
MIN_ROWS = {"sbiz.jsonl": 1000, "bizinfo.jsonl": 800}
SCRIPTS = ROOT / "vendor" / "sole-search" / "skills" / "sole-search" / "scripts"

# ── 지역 ────────────────────────────────────────────────────────────
PROVINCES = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기",
             "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
PROVINCE_WORDS = [
    ("서울특별시", "서울"), ("부산광역시", "부산"), ("대구광역시", "대구"), ("인천광역시", "인천"),
    ("광주광역시", "광주"), ("대전광역시", "대전"), ("울산광역시", "울산"), ("세종특별자치시", "세종"),
    ("경기도", "경기"), ("강원특별자치도", "강원"), ("강원도", "강원"), ("충청북도", "충북"),
    ("충청남도", "충남"), ("전북특별자치도", "전북"), ("전라북도", "전북"), ("전라남도", "전남"),
    ("경상북도", "경북"), ("경상남도", "경남"), ("제주특별자치도", "제주"), ("제주도", "제주"),
]
# 시도별 시·군·구. 여러 시도에 같은 이름이 있는 구(중구·동구 등)는 시도가 먼저 정해졌을 때만 쓴다.
DISTRICTS = {
    "서울": "종로구 중구 용산구 성동구 광진구 동대문구 중랑구 성북구 강북구 도봉구 노원구 은평구 서대문구 마포구 양천구 강서구 구로구 금천구 영등포구 동작구 관악구 서초구 강남구 송파구 강동구",
    "부산": "중구 서구 동구 영도구 부산진구 동래구 남구 북구 해운대구 사하구 금정구 강서구 연제구 수영구 사상구 기장군",
    "대구": "중구 동구 서구 남구 북구 수성구 달서구 달성군 군위군",
    "인천": "중구 동구 미추홀구 연수구 남동구 부평구 계양구 서구 강화군 옹진군",
    "광주": "동구 서구 남구 북구 광산구",
    "대전": "동구 중구 서구 유성구 대덕구",
    "울산": "중구 남구 동구 북구 울주군",
    "세종": "",
    "경기": "수원시 성남시 의정부시 안양시 부천시 광명시 평택시 동두천시 안산시 고양시 과천시 구리시 남양주시 오산시 시흥시 군포시 의왕시 하남시 용인시 파주시 이천시 안성시 김포시 화성시 광주시 양주시 포천시 여주시 연천군 가평군 양평군",
    "강원": "춘천시 원주시 강릉시 동해시 태백시 속초시 삼척시 홍천군 횡성군 영월군 평창군 정선군 철원군 화천군 양구군 인제군 고성군 양양군",
    "충북": "청주시 충주시 제천시 보은군 옥천군 영동군 증평군 진천군 괴산군 음성군 단양군",
    "충남": "천안시 공주시 보령시 아산시 서산시 논산시 계룡시 당진시 금산군 부여군 서천군 청양군 홍성군 예산군 태안군",
    "전북": "전주시 군산시 익산시 정읍시 남원시 김제시 완주군 진안군 무주군 장수군 임실군 순창군 고창군 부안군",
    "전남": "목포시 여수시 순천시 나주시 광양시 담양군 곡성군 구례군 고흥군 보성군 화순군 장흥군 강진군 해남군 영암군 무안군 함평군 영광군 장성군 완도군 진도군 신안군",
    "경북": "포항시 경주시 김천시 안동시 구미시 영주시 영천시 상주시 문경시 경산시 의성군 청송군 영양군 영덕군 청도군 고령군 성주군 칠곡군 예천군 봉화군 울진군 울릉군",
    "경남": "창원시 진주시 통영시 사천시 김해시 밀양시 거제시 양산시 의령군 함안군 창녕군 고성군 남해군 하동군 산청군 함양군 거창군 합천군",
    "제주": "제주시 서귀포시",
}
DISTRICTS = {p: d.split() for p, d in DISTRICTS.items()}
# 이름이 전국에서 하나뿐인 시군구 → 시도를 거꾸로 추정할 때 쓴다
_count = {}
for p, ds in DISTRICTS.items():
    for d in ds:
        _count.setdefault(d, []).append(p)
UNIQUE_DISTRICT = {d: ps[0] for d, ps in _count.items() if len(ps) == 1 and d not in ("광주시",)}


def district_forms(d):
    """'수원시' 는 '수원' 으로도 쓰인다. 두 글자 이하 어간(중구→중)은 쓰지 않는다."""
    stem = d[:-1]
    return [d, stem] if len(stem) >= 2 and d[-1] in "시군" else [d]


def find_provinces(text):
    found = []
    for word, p in PROVINCE_WORDS:
        if word in text and p not in found:
            found.append(p)
    if "전남광주" in text:
        found += [p for p in ("전남", "광주") if p not in found]
    # [서울], 서울시, '서울 ' 처럼 짧게 쓴 경우
    for p in PROVINCES:
        if p in found:
            continue
        if re.search(rf"(\[|\(|^|\s|「|『|<){p}(\]|\)|시\b|시 |\s|·|,|/|특별|광역)", text):
            if p == "광주" and "경기" in found:
                continue
            found.append(p)
    return found


def find_districts(text, provinces):
    out = []
    cands = provinces or PROVINCES
    for p in cands:
        for d in DISTRICTS[p]:
            if not provinces and d not in UNIQUE_DISTRICT:
                continue
            full, *stem = district_forms(d)
            # 줄임말(수원·고양)은 뒤에 한글이 붙지 않을 때만 인정한다 — '고양이' 같은 오탐 방지
            if re.search(rf"(?<![가-힣]){full}", text) or (stem and re.search(rf"(?<![가-힣]){stem[0]}(?![가-힣])", text)):
                out.append((p, d))
    return out


# ── 지원 종류 ────────────────────────────────────────────────────────
KINDS = [
    ("loan", "대출·보증", r"융자|대출|정책자금|경영안정자금|보증|이차보전|이자\s?지원|이자보전|특례자금|육성자금|자금\s?지원|자금 지원"),
    ("cash", "지원금", r"지원금|보조금|장려금|수당|보험료|임차료|임대료|월세|공과금|전기요금|바우처|급여|재기|폐업|철거|원상복구|점포\s?정리|환급|감면|경영안정|안심|회복"),
    ("facility", "시설·기기", r"시설|환경\s?개선|인테리어|리모델링|스마트|키오스크|테이블\s?오더|간판|기기|설비|장비|디지털\s?전환|자동화|개보수|수리"),
    ("sales", "판로·온라인", r"판로|온라인|라이브\s?커머스|입점|박람회|전시회|마케팅|홍보|판매전|기획전|쇼핑몰|배달|브랜드|상품화|수출|팝업|페스티벌|축제|홈쇼핑|유통"),
    ("hire", "인력·고용", r"고용|채용|인력|일자리|인건비|근로자|직원|사회보험"),
    ("cert", "인증·특허", r"인증|특허|상표|지식재산|IP|디자인|품질|표준|시험"),
    ("edu", "교육·컨설팅", r"교육|아카데미|컨설팅|멘토링|강좌|세미나|설명회|코칭|역량\s?강화|진단|상담|클리닉"),
]

# ── 대상 ────────────────────────────────────────────────────────────
SOHO = r"소상공인|자영업|전통시장|골목|상점가|상인|점포|가게|소공인|1인\s?사업자|백년가게|노포|로컬|상권|음식점|외식|식당|카페|미용"
SME = r"중소기업|벤처|스타트업|기술개발|R&D|연구개발|특허|IP|수출기업|제조기업|혁신기업|기술사업화|기업부설|강소기업|중견기업|테크|AI\s?기업|반도체|바이오"
# 소상공인24 대출상품 중 사업자금이 아닌 개인 금융(학자금·주택·생활비)은 뺀다
PERSONAL_LOAN = r"학자금|전세|월세|주택|모기지|보금자리|디딤돌|신혼|오피스텔|생활안정|장례|혼례|결혼|의료비|요양비|학습비|노후|구입자금|사잇돌|햇살론|새희망홀씨|희망사다리|소액생계비|불법사금융|국민행복기금|근로자생활|차량구입|사회복지론|전세사기"
OPERATOR = r"수행기관|운영기관|위탁기관|전문기관|주관기관|평가위원|심사위원|전문위원|강사\s?모집|멘토\s?모집|컨설턴트\s?모집|공급기업|협력기관|운영사|용역|입찰|위원\s?모집|위원\s?공개\s?모집|전문가\s?풀|인력\s?풀"
AUDIENCE_TAGS = [
    ("청년", r"청년"), ("여성", r"여성"), ("장애인", r"장애인"), ("폐업·재기", r"폐업|재기|재창업|희망리턴"),
    ("예비창업", r"예비\s?창업|창업\s?준비"), ("초기창업", r"초기\s?창업|창업\s?[1-7]\s?년\s?(이내|미만)|신규\s?창업"), ("전통시장", r"전통시장|상점가|상인회"),
    ("농·어업", r"농업인|농가|어업인|어가|축산|농식품|수산"),
]

# ── 업종 ────────────────────────────────────────────────────────────
INDUSTRIES = {
    "food": r"음식|외식|식당|요식|카페|커피|베이커리|제과|푸드|주방|위생|배달",
    "retail": r"소매|도소매|슈퍼|편의점|판매점|마트|잡화",
    "beauty": r"미용|뷰티|헤어|네일|피부|이용업|화장품",
    "maker": r"제조|소공인|공방|수제|뿌리|공장|수공예",
    "online": r"온라인|라이브\s?커머스|쇼핑몰|스마트스토어|이커머스|전자상거래|셀러",
    "stay": r"숙박|관광|여행|펜션|민박|숙소",
    "academy": r"학원|교습소",
    "farm": r"농업인|농가|어업인|어가|축산|수산|임업|농식품|귀농",
}


def classify(title, agency, extra=""):
    text = f"{title} {agency} {extra}"
    kinds = [k for k, _, rx in KINDS if re.search(rx, title)]
    tags = [name for name, rx in AUDIENCE_TAGS if re.search(rx, title)]
    inds = [k for k, rx in INDUSTRIES.items() if re.search(rx, title)]
    return text, kinds, tags, inds


def parse_end(v):
    """마감일 → (날짜문자열 or None, 상시 여부)"""
    if not v:
        return None, True
    m = re.match(r"(\d{4})[-.]?(\d{2})[-.]?(\d{2})", v.strip())
    if m:
        return f"{m[1]}-{m[2]}-{m[3]}", False
    return None, True  # 예산 소진시까지, 상시 접수 등


def load(name):
    p = RAW / name
    return [json.loads(l) for l in p.open(encoding="utf-8")] if p.exists() else []


def crawl():
    """새로 받아 data/raw/new 에 두고, 건수가 충분할 때만 data/raw 로 옮긴다. 모자라면 한 번 더 받는다."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    new = RAW / "new"
    jobs = {
        "sbiz.jsonl": ["sbiz_crawl.py", "list", "all", "-o"],
        "bizinfo.jsonl": ["sources_crawl.py", "list", "-o"],
    }
    todo = list(jobs)
    for attempt in (1, 2):
        new.mkdir(parents=True, exist_ok=True)
        procs = {n: subprocess.Popen([sys.executable, str(SCRIPTS / jobs[n][0]), *jobs[n][1:], str(new / n)],
                                     env=env, stderr=subprocess.PIPE, text=True, encoding="utf-8") for n in todo}
        for n, p in procs.items():
            _, err = p.communicate()
            tail = err.strip().splitlines()[-1:] if err else []
            print(f"  [{attempt}] {n}: {' '.join(tail)} (exit {p.returncode})")
        todo = [n for n in todo if count(new / n) < MIN_ROWS[n]]
        if not todo:
            break
    if todo:
        sys.exit(f"수집 실패: {', '.join(f'{n} {count(new / n)}건' for n in todo)} — 페이지를 새로 만들지 않는다")
    for n in jobs:
        shutil.move(str(new / n), str(RAW / n))
    shutil.rmtree(new, ignore_errors=True)


def count(path):
    return sum(1 for _ in path.open(encoding="utf-8")) if path.exists() else 0


def build():
    today = datetime.now(KST).date().isoformat()
    sbiz = load("sbiz.jsonl")
    biz = load("bizinfo.jsonl")

    # 소상공인24 통합조회에 연계된 기업마당 공고(PBLN_*)는 기업마당 쪽으로 합치고, 지원대상만 가져온다
    combine_target = {r["source_id"]: r["raw"].get("rcrtTypeCdNm") for r in sbiz
                      if r["source"] == "sbiz24_combine" and str(r["source_id"]).startswith("PBLN")}

    items, seen, seen_titles = [], set(), set()
    stats = {"sbiz_collected": len(sbiz), "bizinfo_collected": len(biz), "closed": 0, "operator": 0, "personal": 0, "dup": 0}

    def add(r, key, target, is_loan_product=False):
        if key in seen:
            stats["dup"] += 1
            return
        seen.add(key)
        end, rolling = parse_end(r.get("apply_end"))
        if r.get("status") == "마감" or (end and end < today):
            stats["closed"] += 1
            return
        title = re.sub(r"\s+", " ", html.unescape(r["title"])).strip()
        agency = html.unescape(r.get("agency") or "").strip()
        field = (r.get("raw") or {}).get("field") or ""
        # 소상공인24와 기업마당에 따로 올라온 같은 공고: 지역 머리말·공백을 떼고 제목+마감일로 합친다
        tkey = (re.sub(r"^\[[^\]]*\]|[\s\W_]", "", title), end)
        if tkey in seen_titles:
            stats["dup"] += 1
            return
        seen_titles.add(tkey)
        text, kinds, tags, inds = classify(title, agency)
        if is_loan_product and re.search(PERSONAL_LOAN, title):
            stats["personal"] += 1
            return
        if is_loan_product and "loan" not in kinds:
            kinds.insert(0, "loan")
        if not kinds:
            kinds = ["etc"]

        # 대상: 운영기관 모집은 뺀다
        if re.search(OPERATOR, title) or target in ("위탁기관", "수행기관", "컨설턴트", "회계법인"):
            stats["operator"] += 1
            return
        if (target and "소상공인" in target) or target == "전통시장" or r["source"] == "sbiz24" \
                or is_loan_product or re.search(SOHO, text):
            aud = "soho"
        elif target in ("중소기업", "창업벤처") or re.search(SME, text) or field in ("기술", "수출"):
            aud = "sme"
        else:
            aud = "all"

        # 지역: 기업마당은 '시도 / 기관' 앞부분, 나머지는 제목·기관에서 찾는다
        head = agency.split("/")[0].strip()
        provs = find_provinces(f"{title} {head}")
        for word, p in PROVINCE_WORDS + [(p, p) for p in PROVINCES]:
            if head.startswith(word) and p not in provs and not (p == "광주" and head.startswith("광주시")):
                provs.append(p)
        dists = find_districts(title + " " + agency, provs)
        if not provs and dists:
            provs = sorted({p for p, _ in dists})

        items.append({
            "t": title,
            "a": agency,
            "u": r["canonical_url"],
            "s": {"sbiz24": "소상공인24", "sbiz24_combine": "소상공인24", "bizinfo": "기업마당"}[r["source"]],
            "st": (r.get("apply_start") or "")[:10] or None,
            "e": end,
            "ro": rolling,
            "rn": None if not rolling or not r.get("apply_end") else r["apply_end"].strip()[:20],
            "k": kinds,
            "au": aud,
            "tg": tags,
            "in": inds,
            "p": provs,
            "d": [d for _, d in dists],
            "sched": r.get("status") == "회차예정",
        })

    for r in biz:
        add(r, r["source_id"], combine_target.get(r["source_id"]))
    for r in sbiz:
        g = (r.get("raw") or {}).get("pbancGubun")
        if str(r["source_id"]).startswith("PBLN"):
            if r["source_id"] in seen:
                continue  # 기업마당에서 이미 처리
            add(r, r["source_id"], (r.get("raw") or {}).get("rcrtTypeCdNm"))
        elif g == "C":
            add(r, "loan:" + str(r["source_id"]), None, is_loan_product=True)
        else:
            add(r, "sbiz:" + str(r["source_id"]), (r.get("raw") or {}).get("rcrtTypeCdNm"))

    crawled = max((r.get("crawled_at") or "") for r in sbiz + biz)[:16].replace("T", " ")
    meta = {**stats, "open": len(items), "crawled_at": crawled, "built": today}
    data = {"meta": meta, "districts": DISTRICTS, "items": items}

    (ROOT / "data" / "programs.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tpl = (ROOT / "src" / "page.html").read_text(encoding="utf-8")
    out = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    (ROOT / "page.html").write_text(out, encoding="utf-8")

    # 웹 배포용 완전한 HTML: <head> 추가분 + 페이지의 <title>/<style> 은 head 로, 나머지는 body 로
    cut = out.index('<div class="wrap">')
    web_head = (ROOT / "src" / "web-head.html").read_text(encoding="utf-8")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(
        f'<!doctype html>\n<html lang="ko">\n<head>\n{web_head}{out[:cut]}</head>\n<body>\n{out[cut:]}</body>\n</html>\n',
        encoding="utf-8")

    from collections import Counter
    print(f"접수 중 {len(items)}건 (마감 제외 {stats['closed']}, 운영기관 모집 제외 {stats['operator']}, 개인 대출 제외 {stats['personal']}, 중복 {stats['dup']})")
    print("대상", Counter(i["au"] for i in items))
    print("종류", Counter(k for i in items for k in i["k"]))
    print("지역 없음(전국)", sum(not i["p"] for i in items), "/ 시군구 있음", sum(bool(i["d"]) for i in items))
    print("page.html", round(len(out.encode()) / 1024), "KB")


if __name__ == "__main__":
    if "--crawl" in sys.argv:
        print("수집 중…")
        crawl()
    build()
