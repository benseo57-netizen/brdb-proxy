import os
import json
import asyncio
import smtplib
import requests
import time
import re
import html as html_lib
import xml.etree.ElementTree as ET
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import google.generativeai as genai

# 환경변수
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
GMAIL_USER     = os.environ['GMAIL_USER']
GMAIL_APP_PASS = os.environ['GMAIL_APP_PASSWORD']
TO_EMAIL       = os.environ['TO_EMAIL']
BCC_EMAIL      = os.environ.get('BCC_EMAIL', '')

genai.configure(api_key=GEMINI_API_KEY)

# ============================================================
# RSS 쿼리
# ============================================================
QUERIES = [
    # ── 국내 기업 ──
    # 1 — 성일하이텍 직접 모니터링 (한국어)
    {"q": '"성일하이텍" OR "에코프로씨엔지" OR "아이에스티엠씨" OR "IS에코솔루션"',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},

    # 2 — SungEel 영문명 직접 감시 (신규)
    {"q": '"SungEel" OR "Sungeel HiTech"',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # ── 글로벌 재활용사 ──
    # 3 — 메이저
    {"q": '("Glencore" OR "Umicore" OR "Redwood Materials" OR "Ascend Elements") "recycling"',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # 4 — 북미 중소형 (Li-Cycle 제거 → Retriev·Battery Resources 추가 / IS Eco Solution·Interco·Blue Whale·Princeton NuEnergy 신규)
    {"q": '("Cirba Solutions" OR "Ecobat" OR "Retriev" OR "Ace Green" OR "Battery Resources" OR "Interco" OR "Blue Whale" OR "Princeton NuEnergy" OR "IS Eco Solution") "battery"',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # 5 — 유럽 재활용사 (신규: 성일 폴란드·헝가리 법인 인접 경쟁사)
    {"q": '("Fortum" OR "Stena Recycling" OR "BASF") ("battery recycling" OR "battery waste" OR "black mass")',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # 6 — Northvolt: 파산 후 자산 매각·공장 인수 맥락으로 한정
    {"q": '"Northvolt" ("acquisition" OR "asset sale" OR "factory" OR "takeover")',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # ── 배터리 제조사 ──
    # 7 — 셀 메이커
    {"q": '("LG Energy Solution" OR "Samsung SDI" OR "SK On" OR "Panasonic" OR "CATL" OR "BYD") "recycling"',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # 8 — 완성차 (battery closed-loop → 실제 기사 표현으로 교체)
    {"q": '("Tesla" OR "Hyundai" OR "Toyota" OR "Honda" OR "Volkswagen") ("battery take-back" OR "end-of-life battery" OR "second-life battery")',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # ── 양극재·전구체 ──
    # 9
    {"q": '("EcoPro BM" OR "L&F" OR "POSCO Future M" OR "LG Chem") ("precursor" OR "cathode")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 10
    {"q": '("에코프로비엠" OR "엘앤에프" OR "포스코퓨처엠" OR "LG화학") ("전구체" OR "양극재")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},

    # ── 리튬 원재료 생산사 ──
    # 11
    {"q": '("Albemarle" OR "SQM" OR "Ganfeng" OR "Tianqi") ("lithium supply" OR "production cut" OR "mine")',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # ── 블랙매스·스크랩 ──
    # 12
    {"q": '("black mass" OR "battery scrap" OR "feedstock") ("shortage" OR "tender" OR "payables" OR "price")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 13
    {"q": '("블랙매스" OR "폐배터리 스크랩") ("입찰" OR "매입가" OR "공급 부족")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},

    # ── 원재료 가격 ──
    # 14
    {"q": '("nickel sulfate" OR "cobalt sulfate") ("price" OR "market" OR "index")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 15
    {"q": '("lithium carbonate" OR "lithium hydroxide") ("spot" OR "price" OR "supply")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 16
    {"q": '("황산니켈" OR "황산코발트" OR "탄산리튬" OR "수산화리튬") ("가격" OR "시황")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},

    # ── 인도네시아 니켈 (신규: HPAL·HPM 분석 맥락) ──
    # 17
    {"q": '"Indonesia" ("nickel" OR "HPAL" OR "nickel ore") ("export" OR "price" OR "quota" OR "HPM")',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # ── 정책·규제 ──
    # 18
    {"q": '("EU Battery Regulation" OR "Battery Passport" OR "recycled content" OR "OBBBA") "compliance"',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 19
    {"q": '("critical minerals" OR "IRA" OR "OBBBA") "battery recycling"',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 20 — 한국 정책 (배터리 단독 → 실제 기사 표현으로 확장)
    {"q": '("이차전지" OR "사용후배터리" OR "폐배터리") ("EPR" OR "핵심광물" OR "순환이용" OR "재활용 의무")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},

    # ── 인도 ──
    # 21
    {"q": '"India" ("battery recycling" OR "EPR" OR "black mass" OR "CPCB")',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # ── 투자·M&A ──
    # 22
    {"q": '"battery recycling" ("M&A" OR "acquisition" OR "joint venture")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 23
    {"q": '"배터리 재활용" ("투자" OR "JV" OR "파트너십")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},

    # ── 기술·공정 ──
    # 24 — 수계 공정 (hydromet 약칭 추가)
    {"q": '("hydrometallurgy" OR "hydromet" OR "direct recycling") ("battery" OR "recovery" OR "purity")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    # 25 — LFP 전용 (신규: 성일 전략 집중 분야)
    {"q": '("LFP" OR "lithium iron phosphate") ("recycling" OR "recovery" OR "black mass")',
     "lang": "en", "gl": "US", "ceid": "US:en"},

    # ── 일본어 ──
    # 26
    {"q": '("住友金属鉱山" OR "日亜化学") ("正極材" OR "前駆体" OR "リサイクル")',
     "lang": "ja", "gl": "JP", "ceid": "JP:ja"},
    # 27
    {"q": '("パナソニック" OR "トヨタ") ("電池リサイクル" OR "回収")',
     "lang": "ja", "gl": "JP", "ceid": "JP:ja"},

    # ── 중국어 ──
    # 28
    {"q": '("硫酸镍" OR "硫酸钴" OR "碳酸锂") ("价格" OR "现货")',
     "lang": "zh-CN", "gl": "CN", "ceid": "CN:zh-CN"},
    # 29
    {"q": '"动力电池回收" ("政策" OR "标准")',
     "lang": "zh-CN", "gl": "CN", "ceid": "CN:zh-CN"},

    # ── 헝가리어 (신규: 성일·삼성SDI 현지 법인 모니터링) ──
    # 30
    {"q": '"SungEel" OR "Samsung SDI" OR "akkuhulladék" OR "akkumulátor" OR "újrahasznosít"',
     "lang": "hu", "gl": "HU", "ceid": "HU:hu"},

    # ── SMM 직접 피드 ──
    # 31
    {"direct_url": "https://www.google.com/alerts/feeds/03699096368296272379/11789334169558310879",
     "lang": "en"},
]

NOISE_KEYWORDS = [
    "crypto","bitcoin","ethereum","nft","dogecoin","게임","영화","드라마","리뷰",
    "car review","smartphone review","stock tip","smartwatch","battery etf",
    "lithium etf","목표가 상향","목표가 하향","투자의견","eurekaalert","전자폐기물",
    "cassava","agriculture","crop","petro","petroleum","oil refin",
    "dow jones","s&p 500","nasdaq"
]

NOISE_SOURCES = [
    "openpr","prnewswire","businesswire","globenewswire","einpresswire",
    "accesswire","prnews","prlog","marketwired","newswire","pr.com","prweb",
    "discoveryalert","bravenewcoin","eurekaalert","cryptoslate","coindesk",
    "benzinga","seekingalpha","motleyfool","investopedia","indexbox",
    "msn","msn.com",
]

WHITELIST = [
    # 공통 배터리·재활용
    "battery", "배터리", "전지", "이차전지", "사용후배터리", "폐배터리",
    "recycl", "재활용", "순환이용",

    # 핵심 금속
    "lithium", "리튬", "nickel", "니켈", "cobalt", "코발트",

    # 소재·공정
    "black mass", "블랙매스", "cathode", "양극재", "precursor", "전구체",
    "anode", "electrolyte", "feedstock", "scrap", "스크랩",
    "황산니켈", "황산코발트", "탄산리튬", "수산화리튬",
    "nickel sulfate", "cobalt sulfate", "lithium carbonate", "lithium hydroxide",
    "hydrometallurgy", "hydromet",
    "lfp", "lithium iron phosphate",

    # EV·인프라
    "gigafactory", "kwh", "mwh", "ev ", "electric vehicle",

    # 글로벌 재활용사
    "ascend", "redwood", "cirba", "ecobat", "umicore",
    "glencore", "northvolt", "retriev", "battery resources",
    "interco", "blue whale", "princeton nuenergy",
    "is eco solution",
    "fortum", "stena",

    # 성일하이텍
    "sungeel", "성일",

    # 셀 메이커·완성차
    "samsung",          # samsung sdi보다 넓게 — 헝가리 기사 대응
    "catl", "byd", "lges", "sk on", "panasonic",
    "albemarle", "sqm", "ganfeng", "tianqi",

    # 국내 소재사
    "성일하이텍", "에코프로", "포스코퓨처엠",

    # 정책
    "circular economy", "생산자책임",

    # 헝가리어 — 헝가리 쿼리 대응
    "akkumulátor", "akkuhulladék",

    # 중국어
    "电池", "回收", "锂", "镍", "钴",

    # 일본어
    "リサイクル", "電池", "リチウム", "ニッケル", "コバルト",
]

# ============================================================
# 유틸
# ============================================================
def decode_entities(text):
    return html_lib.unescape(text or "")

def esc(text):
    return (str(text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def parse_date(pub_str):
    if not pub_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(pub_str).replace(tzinfo=None)
    except:
        pass
    try:
        return datetime.fromisoformat(pub_str.replace('Z', '').replace('+00:00', ''))
    except:
        return None

def extract_real_url(url):
    """구글 리다이렉트 URL에서 실제 URL 추출"""
    if "google.com/url" in url:
        match = re.search(r'[?&]url=([^&]+)', url)
        if match:
            return urllib.parse.unquote(match.group(1))
    return url

# ============================================================
# RSS 수집
# ============================================================
def collect_rss():
    now = datetime.utcnow()
    cutoff_48h = now - timedelta(hours=48)
    cutoff_72h = now - timedelta(hours=72)

    raw = []
    seen = set()

    for item in QUERIES:
        is_smm = "direct_url" in item
        cutoff = cutoff_72h if is_smm else cutoff_48h

        try:
            if is_smm:
                url = item["direct_url"]
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                print(f"SMM 피드 응답코드: {resp.status_code}")
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
            else:
                q = item["q"] + " when:3d"
                url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}"
                       f"&hl={item['lang']}&gl={item['gl']}&ceid={item['ceid']}&num=10"
                       f"&cb={int(now.timestamp())}")
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)

            ns = {"atom": "http://www.w3.org/2005/Atom"}
            is_atom = root.tag.endswith("feed")
            entries = root.findall(".//atom:entry", ns) if is_atom else root.findall(".//item")

            for entry in entries:
                if is_atom:
                    title_el = entry.find("atom:title", ns) or entry.find("title")
                    title = decode_entities((title_el.text or "") if title_el is not None else "")
                    title = re.sub(r'<[^>]+>', '', title)
                    link_el = entry.find("atom:link", ns)
                    link = link_el.get("href", "") if link_el is not None else ""
                    link = extract_real_url(link)
                    pub_str = (entry.findtext("atom:published", "", ns) or
                               entry.findtext("atom:updated", "", ns))
                    source = "SMM Metal"
                    snippet = decode_entities(re.sub(r'<[^>]+>', '', (
                        entry.findtext("atom:summary", "", ns) or
                        entry.findtext("atom:content", "", ns) or ""
                    )))[:200]
                else:
                    title = decode_entities((entry.findtext("title") or "").strip())
                    link = (entry.findtext("link") or "").strip()
                    link = extract_real_url(link)
                    pub_str = (entry.findtext("pubDate") or "").strip()
                    source_el = entry.find("source")
                    source = source_el.text.strip() if source_el is not None else ""
                    snippet = decode_entities(re.sub(r'<[^>]+>', '',
                        entry.findtext("description") or ""))[:200]

                if not title or not link or link in seen:
                    continue

                pub_date = parse_date(pub_str)
                if pub_date and pub_date < cutoff:
                    continue

                lower_title  = title.lower()
                lower_source = source.lower()
                lower_link   = link.lower()

                if any(k in lower_title for k in NOISE_KEYWORDS):
                    continue
                if any(s in lower_source or s in lower_link for s in NOISE_SOURCES):
                    continue

                if source != "SMM Metal":
                    if not any(w in lower_title for w in WHITELIST):
                        continue

                seen.add(link)
                raw.append({
                    "title": title, "link": link, "source": source,
                    "pub": pub_str, "pub_date": pub_date,
                    "lang": item.get("lang", "en"), "snippet": snippet
                })

            time.sleep(0.12)
        except Exception as e:
            print(f"RSS 오류: {e}")

    raw.sort(key=lambda x: x.get("pub_date") or datetime.min, reverse=True)

    deduped = []
    for a in raw:
        words = {w for w in re.sub(r'[^\w\s]', ' ', a["title"]).split() if len(w) >= 2}
        is_dup = any(
            len(words & {w for w in re.sub(r'[^\w\s]', ' ', b["title"]).split() if len(w) >= 2}) >= 3
            for b in deduped
        )
        if not is_dup:
            deduped.append(a)

    smm_count = sum(1 for a in deduped if "SMM" in a.get("source", ""))
    print(f"수집: {len(raw)}건 → 중복 제거 후: {len(deduped)}건 (SMM: {smm_count}건)")
    return deduped

# ============================================================
# Jina로 본문 추출 (3,000자)
# ============================================================
def fetch_body(real_url):
    try:
        resp = requests.get(
            f"https://r.jina.ai/{real_url}",
            timeout=25,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            return resp.text[:3000]
    except Exception as e:
        print(f"Jina 오류: {e}")
    return ""

# ============================================================
# Playwright로 실제 URL 추출
# ============================================================
async def get_real_url(page, cbm_url):
    try:
        await page.goto(cbm_url, wait_until="commit", timeout=15000)
        try:
            await page.wait_for_url(
                lambda url: "news.google.com" not in url,
                timeout=10000
            )
        except:
            pass
        final_url = page.url
        if "news.google.com" not in final_url:
            return final_url
    except Exception as e:
        print(f"리다이렉트 실패: {e}")
    return None

# ============================================================
# 본문 수집 (SMM 최대 2건 + 일반 15건으로 확대)
# ============================================================
async def enrich_articles(articles):
    smm     = [a for a in articles if "SMM" in a.get("source", "")][:2]
    general = [a for a in articles if "SMM" not in a.get("source", "")][:15]  # 9 → 15
    targets = smm + general

    print(f"\n본문 추출 대상: SMM {len(smm)}건 + 일반 {len(general)}건 = {len(targets)}건")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        body_success = 0
        body_snippet = 0

        for i, article in enumerate(targets):
            print(f"[{i+1}/{len(targets)}] {article['title'][:55]}")
            link = article["link"]

            if "SMM" in article.get("source", "") or "news.google.com" not in link:
                body = fetch_body(link)
                if body:
                    article["body"] = body
                    body_success += 1
                    print(f"  ✅ 직접 Jina ({len(body)}자)")
                else:
                    body_snippet += 1
                    print(f"  ⚠️ Jina 실패 — 스니펫 사용")
                continue

            real_url = await get_real_url(page, link)
            if real_url:
                article["real_url"] = real_url   # 이메일 링크용으로 저장
                body = fetch_body(real_url)
                article["body"] = body
                if body:
                    body_success += 1
                    print(f"  ✅ {real_url[:65]} ({len(body)}자)")
                else:
                    body_snippet += 1
                    print(f"  ⚠️ URL 추출됐으나 본문 없음 — 스니펫 사용")
            else:
                body_snippet += 1
                print(f"  ⚠️ 리다이렉트 실패 — 스니펫 사용")

        await browser.close()

    print(f"\n본문 추출 결과: 성공 {body_success}건 / 스니펫 대체 {body_snippet}건")
    return targets

# ============================================================
# Gemini 분석
# ============================================================
def analyze(articles):
    today     = datetime.now().strftime("%Y년 %m월 %d일")
    today_str = datetime.now().strftime("%Y-%m-%d")

    smm_articles     = [a for a in articles if "SMM" in a.get("source", "")][:2]
    general_articles = [a for a in articles if "SMM" not in a.get("source", "")]

    def format_article(i, a):
        line = (f"{i+1}. [{a['lang'].upper()}] {a['title']}\n"
                f"   출처: {a.get('source','불명')} | 날짜: {a.get('pub','')} | 링크: {a['link']}")
        body = a.get("body", "") or a.get("snippet", "")
        if body:
            line += f"\n   [본문]: {body[:2000]}"
        return line

    smm_section     = "\n\n".join(format_article(i, a) for i, a in enumerate(smm_articles))
    general_section = "\n\n".join(format_article(i, a) for i, a in enumerate(general_articles))

    prompt = f"""당신은 리튬이온 배터리 재활용 산업 전문 시니어 애널리스트입니다. 아래 뉴스를 분석하여 JSON만 출력하세요.
오늘 날짜: {today}

━━━ [SMM Metal 시황 기사 — 최우선 포함, 최대 2건] ━━━
{smm_section if smm_section else "오늘 SMM 기사 없음"}

━━━ [일반 뉴스] ━━━
{general_section}

[선별 기준]
- 오늘({today_str}) 기사 최우선. 어제 기사는 오늘 기사 부족 시만 포함
- 동일 기업이라도 주제(실적/투자/정책/기술/시황)가 다르면 별도 기사로 포함 가능
- 동일 기업·동일 주제인 경우에만 가장 최신 1건으로 제한, 중복 절대 금지
- 성일하이텍 관련 기사가 여러 건이면 가장 중요한 1건만
- 배터리 재활용, 블랙매스, 원재료(Li/Ni/Co), 공급망, 정책·규제, 투자·M&A 우선
- 단순 주가 등락, PR 배포, ETF, 학술 보도자료 제외

[요약 작성 기준 — 가장 중요]
- 3문장 이내 자유 서술형으로 작성
- 본문에 등장하는 기관명·기업명·금액·수치·날짜는 빠짐없이 반영 (이것이 최우선)
- 수치 없이 "~할 것으로 전망된다" 같은 추상적 요약 절대 금지
- 기업명은 정식 전체 명칭 사용 (약칭 금지)
- 계획 발표 ≠ 실제 시작, MOU ≠ 계약, 검토 ≠ 확정 — 반드시 구분
- 성일하이텍 관점은 강제하지 않음. 직접적 연관성이 명확할 때만 자연스럽게 언급
- 나쁜 예: "리튬 시장이 공급 부족 국면에 진입할 것으로 전망된다."
- 좋은 예: "Canaccord Genuity는 2026~2035년 구조적 리튬 공급부족을 경고했고, Morgan Stanley는 LCE 8만 톤, UBS는 2만 2천 톤 부족을 추정했다. 탄산리튬 현물가는 4월 23일 기준 1kg당 20.29달러로 연초 대비 2배 이상 반등했다."
- 좋은 예2: "포스코퓨처엠(POSCO Future M)이 베트남 타이응웬성에서 IRC를 획득하고 3,570억 원을 투자해 2028년 인조흑연 음극재 양산을 목표로 한다."

[트렌드 3개 기준]
- 한국/중국/미국·EU 지역별 균형
- 오늘 기사의 특정 기업명·수치·정책명 직접 인용
- 이 뉴스 없이는 쓸 수 없는 구체적 내용
- 금지: '중요성이 부각된다', '필요성이 대두된다' 같은 일반론

[시사점 4~5개 기준]
- 성일하이텍(국내 최대 배터리 재활용, 블랙매스 생산 및 황산니켈·황산코발트·탄산리튬 판매) 관점
- 해외 법인(미국 인디애나, 폴란드, 헝가리, 인도, 말레이시아, 중국) 연계 검토
- 오늘 기사의 구체적 기업명·수치·정책 직접 언급
- 자연스러운 한국어 문장으로 작성

[출력: JSON만]
{{
  "articles": [{{
    "title": "원문 제목",
    "source": "출처",
    "date": "날짜",
    "link": "URL",
    "summary": "본문 수치·기관명·기업명 필수 반영, 3문장 이내 자유 서술.",
    "tag": "원재료 및 시황|투자 및 M&A|정책 및 규제|공급망 및 파트너십|기술 및 공정 중 하나",
    "region": "한국|중국|미국|EU|일본|글로벌"
  }}],
  "trends": [{{"title": "트렌드 제목", "body": "구체적 내용 2~3문장"}}],
  "insights": ["시사점"]
}}

articles: SMM 최대 2건 + 일반 기사 합산 총 8~12건 (동일 기업이라도 주제가 다르면 별도 포함).
trends 3개(지역 균형). insights 4~5개. 모든 텍스트 한국어."""

    model = genai.GenerativeModel("gemini-2.5-flash")
    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        temperature=0.2
    )

    for attempt in range(3):
        try:
            time.sleep(6)
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            return json.loads(response.text)
        except Exception as ex:
            print(f"Gemini 오류 (시도 {attempt+1}/3): {ex}")
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f"{wait}초 대기 후 재시도...")
                time.sleep(wait)

    raise Exception("Gemini 분석 3회 모두 실패")

# ============================================================
# 이메일 HTML 생성
# ============================================================
def build_email(data):
    today = datetime.now().strftime("%Y년 %m월 %d일")
    TAG_ORDER = ["원재료 및 시황","공급망 및 파트너십","투자 및 M&A","정책 및 규제","기술 및 공정"]

    by_tag = {}
    for a in data.get("articles", []):
        tag = a.get("tag", "기타")
        by_tag.setdefault(tag, []).append(a)

    def card(a):
        # real_url 우선, 없으면 link 사용 — Google News 리다이렉트 방지
        url = esc(a.get("real_url") or a.get("link", ""))
        summary = esc(a.get("summary", "")).replace('\n', '<br>')
        return f"""
        <div style="border:1px solid #e0e4ea;border-radius:6px;padding:14px 16px;margin-bottom:12px;background:#fff;">
          <p style="font-size:14px;font-weight:700;color:#0f2744;margin:0 0 3px;">
            <a href="{url}" style="color:#0f2744;text-decoration:none;">{esc(a.get('title',''))}</a>
          </p>
          <p style="font-size:11px;color:#94a3b8;margin:0 0 8px;">{esc(a.get('source',''))} · {esc(a.get('date',''))}</p>
          <p style="font-size:13px;color:#374151;line-height:1.75;margin:0 0 10px;">{summary}</p>
          <span style="display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:10px;background:#dcfce7;color:#15803d;margin-right:5px;">{esc(a.get('region',''))}</span>
          <a href="{url}" style="font-size:11px;color:#ea580c;text-decoration:none;border:1px solid #fdba74;border-radius:10px;padding:2px 9px;">원문 보기</a>
        </div>"""

    articles_html = ""
    first = True
    for tag in TAG_ORDER:
        if tag not in by_tag:
            continue
        mt = "margin-top:0;" if first else ""
        articles_html += f'<p style="font-size:13px;font-weight:700;color:#1a3a5c;{mt}margin-bottom:8px;padding-bottom:4px;border-bottom:2px solid #cbd5e1;">[ {esc(tag)} ]</p>'
        first = False
        for a in by_tag[tag]:
            articles_html += card(a)

    trends_html = ""
    for i, t in enumerate(data.get("trends", [])):
        trends_html += f"""
        <div style="border-left:3px solid #2563eb;padding:10px 14px;margin-bottom:12px;background:#f0f5ff;">
          <p style="font-size:11px;font-weight:700;color:#2563eb;margin:0 0 3px;">TREND 0{i+1}</p>
          <p style="font-size:13px;font-weight:700;color:#0f2744;margin:0 0 5px;">{esc(t.get('title',''))}</p>
          <p style="font-size:13px;color:#374151;line-height:1.75;margin:0;">{esc(t.get('body',''))}</p>
        </div>"""

    insights_html = ""
    insights = data.get("insights", [])
    for i, ins in enumerate(insights):
        bb = "border-bottom:1px solid #fef3c7;" if i < len(insights) - 1 else ""
        insights_html += (
            f'<div style="font-size:13px;color:#374151;line-height:1.75;padding:5px 0;{bb}">'
            f'<span style="color:#d97706;font-weight:700;margin-right:6px;">&#9658;</span>'
            f'{esc(ins)}</div>'
        )

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:16px;background:#eef0f3;">
<div style="max-width:660px;margin:0 auto;background:#fff;font-family:'Malgun Gothic','맑은 고딕',Arial,sans-serif;">
  <div style="background:#0f2744;padding:22px 28px;">
    <p style="color:#fff;font-size:18px;font-weight:700;margin:0 0 4px;">BATTERY RECYCLING DAILY BRIEF</p>
    <p style="color:#90b4d8;font-size:12px;margin:0;">{today}&nbsp;&nbsp;|&nbsp;&nbsp;Battery Intelligence Report</p>
  </div>
  <div style="background:#1a3a5c;color:#fff;font-size:11px;font-weight:700;letter-spacing:1px;padding:7px 28px;">SECTION 1 &nbsp;/&nbsp; 분야별 핵심 기사</div>
  <div style="padding:16px 28px 8px;background:#f5f6f8;">{articles_html}</div>
  <div style="background:#1a3a5c;color:#fff;font-size:11px;font-weight:700;letter-spacing:1px;padding:7px 28px;">SECTION 2 &nbsp;/&nbsp; 오늘의 산업 흐름</div>
  <div style="padding:16px 28px 8px;background:#f5f6f8;">{trends_html}</div>
  <div style="background:#1a3a5c;color:#fff;font-size:11px;font-weight:700;letter-spacing:1px;padding:7px 28px;">SECTION 3 &nbsp;/&nbsp; 재활용 사업자 관점 시사점</div>
  <div style="padding:16px 28px 20px;background:#f5f6f8;">
    <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:14px 16px;">{insights_html}</div>
  </div>
  <div style="background:#0f2744;padding:14px 28px;text-align:center;">
    <p style="color:#7ea8d4;font-size:11px;margin:0;">Battery Recycling Daily Brief&nbsp;&nbsp;|&nbsp;&nbsp;{today}</p>
    <p style="color:#7ea8d4;font-size:10px;margin:5px 0 0;">(c) Ben Seo, Sales &amp; Marketing Division / SungEel HiTech</p>
  </div>
</div>
</body></html>"""

# ============================================================
# Gmail 발송
# ============================================================
def send_email(html_body):
    today = datetime.now().strftime("%Y년 %m월 %d일")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[배터리 산업 Daily Brief] {today}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    # Bcc 헤더 없음 — sendmail recipients에만 추가
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        bcc_list   = [addr.strip() for addr in BCC_EMAIL.split(',') if addr.strip()] if BCC_EMAIL else []
        recipients = [TO_EMAIL] + bcc_list
        smtp.sendmail(GMAIL_USER, recipients, msg.as_string())
    print(f"발송 완료 → {TO_EMAIL} (BCC {len(bcc_list)}명)")

# ============================================================
# 메인
# ============================================================
async def main():
    print("=== BRDB 시작 ===")
    articles = collect_rss()
    if not articles:
        print("기사 없음 - 종료")
        return

    articles = await enrich_articles(articles)
    data     = analyze(articles)
    html     = build_email(data)
    send_email(html)
    print("=== 완료 ===")

if __name__ == "__main__":
    asyncio.run(main())

