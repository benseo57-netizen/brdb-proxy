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

genai.configure(api_key=GEMINI_API_KEY)

# ============================================================
# RSS 쿼리
# ============================================================
QUERIES = [
    {"q": '"성일하이텍" OR "에코프로씨엔지" OR "아이에스티엠씨"', "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("Glencore" OR "Umicore" OR "Redwood Materials" OR "Ascend Elements") "recycling"', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("Cirba Solutions" OR "Ecobat" OR "Li-Cycle" OR "Ace Green") "battery recycling"', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("LG Energy Solution" OR "Samsung SDI" OR "SK On" OR "Panasonic" OR "CATL" OR "BYD") "recycling"', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("Tesla" OR "Hyundai" OR "Toyota" OR "Honda" OR "Volkswagen") "battery closed-loop"', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("EcoPro BM" OR "L&F" OR "POSCO Future M" OR "LG Chem") ("precursor" OR "cathode")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("에코프로비엠" OR "엘앤에프" OR "포스코퓨처엠" OR "LG화학") ("전구체" OR "양극재")', "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("Albemarle" OR "SQM" OR "Ganfeng" OR "Tianqi") ("lithium supply" OR "production cut" OR "mine")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("black mass" OR "battery scrap" OR "feedstock") ("shortage" OR "tender" OR "payables" OR "price")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("블랙매스" OR "폐배터리 스크랩") ("입찰" OR "매입가" OR "공급 부족")', "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("nickel sulfate" OR "cobalt sulfate") ("price" OR "market" OR "index")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("lithium carbonate" OR "lithium hydroxide") ("spot" OR "price" OR "supply")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("황산니켈" OR "황산코발트" OR "탄산리튬" OR "수산화리튬") ("가격" OR "시황")', "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("EU Battery Regulation" OR "Battery Passport" OR "recycled content" OR "OBBBA") "compliance"', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("critical minerals" OR "IRA" OR "OBBBA") "battery recycling"', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"배터리" ("EPR" OR "핵심광물" OR "사용후 배터리법")', "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '"India" ("battery recycling" OR "EPR" OR "black mass" OR "CPCB")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"battery recycling" ("M&A" OR "acquisition" OR "joint venture")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"배터리 재활용" ("투자" OR "JV" OR "파트너십")', "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("hydrometallurgy" OR "direct recycling" OR "LFP recycling") ("recovery" OR "purity")', "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("住友金属鉱山" OR "日亜化学") ("正極材" OR "前駆体" OR "リサイクル")', "lang": "ja", "gl": "JP", "ceid": "JP:ja"},
    {"q": '("パナソニック" OR "トヨタ") ("電池リサイクル" OR "回収")', "lang": "ja", "gl": "JP", "ceid": "JP:ja"},
    {"q": '("硫酸镍" OR "硫酸钴" OR "碳酸锂") ("价格" OR "现货")', "lang": "zh-CN", "gl": "CN", "ceid": "CN:zh-CN"},
    {"q": '"动力电池回收" ("政策" OR "标准")', "lang": "zh-CN", "gl": "CN", "ceid": "CN:zh-CN"},
    {"direct_url": "https://www.google.com/alerts/feeds/03699096368296272379/9793158246760815124", "lang": "en"},
]

NOISE_KEYWORDS = [
    "crypto","bitcoin","ethereum","nft","dogecoin","게임","영화","드라마","리뷰",
    "car review","smartphone review","stock tip","smartwatch","battery etf",
    "lithium etf","목표가 상향","목표가 하향","투자의견","eurekaalert","전자폐기물"
]

NOISE_SOURCES = [
    "openpr","prnewswire","businesswire","globenewswire","einpresswire",
    "accesswire","prnews","prlog","marketwired","newswire","pr.com","prweb",
    "discoveryalert","bravenewcoin","eurekaalert","cryptoslate","coindesk",
    "benzinga","seekingalpha","motleyfool","investopedia"
]

# ============================================================
# 유틸
# ============================================================
def decode_entities(text):
    return html_lib.unescape(text or "")

def esc(text):
    """HTML 특수문자 이스케이프"""
    return (str(text or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

# ============================================================
# RSS 수집
# ============================================================
def collect_rss():
    cutoff = datetime.utcnow() - timedelta(hours=72)
    raw = []
    seen = set()

    for item in QUERIES:
        try:
            if "direct_url" in item:
                url = item["direct_url"]
            else:
                q = item["q"] + " when:3d"
                url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}"
                       f"&hl={item['lang']}&gl={item['gl']}&ceid={item['ceid']}&num=10")

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
                    pub = (entry.findtext("atom:published", "", ns) or
                           entry.findtext("atom:updated", "", ns))
                    source = "SMM Metal"
                    snippet = decode_entities(re.sub(r'<[^>]+>', '', (
                        entry.findtext("atom:summary", "", ns) or
                        entry.findtext("atom:content", "", ns) or ""
                    )))[:200]
                else:
                    title = decode_entities((entry.findtext("title") or "").strip())
                    link = (entry.findtext("link") or "").strip()
                    pub = (entry.findtext("pubDate") or "").strip()
                    source_el = entry.find("source")
                    source = source_el.text.strip() if source_el is not None else ""
                    snippet = decode_entities(re.sub(r'<[^>]+>', '',
                        entry.findtext("description") or ""))[:200]

                if not title or not link or link in seen:
                    continue

                lower_title  = title.lower()
                lower_source = source.lower()
                lower_link   = link.lower()

                if any(k in lower_title for k in NOISE_KEYWORDS):
                    continue
                if any(s in lower_source or s in lower_link for s in NOISE_SOURCES):
                    continue

                seen.add(link)
                raw.append({
                    "title": title, "link": link, "source": source,
                    "pub": pub, "lang": item.get("lang", "en"), "snippet": snippet
                })

            time.sleep(0.12)
        except Exception as e:
            print(f"RSS 오류: {e}")

    # 중복 제거
    deduped = []
    for a in raw:
        words = {w for w in re.sub(r'[^\w\s]', ' ', a["title"]).split() if len(w) >= 2}
        is_dup = any(
            len(words & {w for w in re.sub(r'[^\w\s]', ' ', b["title"]).split() if len(w) >= 2}) >= 3
            for b in deduped
        )
        if not is_dup:
            deduped.append(a)

    print(f"수집: {len(raw)}건 → 중복 제거 후: {len(deduped)}건")
    return deduped

# ============================================================
# Jina로 본문 추출
# ============================================================
def fetch_body(real_url):
    try:
        resp = requests.get(
            f"https://r.jina.ai/{real_url}",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            return resp.text[:500]
    except Exception as e:
        print(f"Jina 오류: {e}")
    return ""

# ============================================================
# Playwright로 실제 URL 추출
# ============================================================
async def get_real_url(page, cbm_url):
    try:
        await page.goto(cbm_url, wait_until="networkidle", timeout=20000)
        final_url = page.url
        if "news.google.com" not in final_url:
            return final_url
    except Exception as e:
        print(f"리다이렉트 실패: {e}")
    return None

# ============================================================
# 본문 수집 (SMM 3건 + 일반 9건 = 최대 12건)
# ============================================================
async def enrich_articles(articles):
    smm     = [a for a in articles if "SMM" in a.get("source", "")][:3]
    general = [a for a in articles if "SMM" not in a.get("source", "")][:9]
    targets = smm + general

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        for i, article in enumerate(targets):
            print(f"[{i+1}/{len(targets)}] {article['title'][:50]}")
            link = article["link"]

            # SMM 또는 직접 URL → Jina 바로 시도
            if "SMM" in article.get("source", "") or "news.google.com" not in link:
                body = fetch_body(link)
                if body:
                    article["body"] = body
                    print(f"  ✅ 직접 Jina ({len(body)}자)")
                continue

            # 구글뉴스 CBM → Playwright로 실제 URL 추출
            real_url = await get_real_url(page, link)
            if real_url:
                body = fetch_body(real_url)
                article["body"] = body
                article["real_url"] = real_url
                print(f"  ✅ {real_url[:60]} ({len(body)}자)")
            else:
                print(f"  ⚠️ 스니펫 사용")

        await browser.close()

    return targets

# ============================================================
# Gemini 분석
# ============================================================
def analyze(articles):
    today     = datetime.now().strftime("%Y년 %m월 %d일")
    today_str = datetime.now().strftime("%Y-%m-%d")

    article_list = []
    for i, a in enumerate(articles):
        line = (f"{i+1}. [{a['lang'].upper()}] {a['title']} | "
                f"출처: {a.get('source','불명')} | 날짜: {a.get('pub','')} | 링크: {a['link']}")
        body = a.get("body", "") or a.get("snippet", "")
        if body:
            line += f"\n   [본문]: {body[:400]}"
        article_list.append(line)

    prompt = f"""당신은 리튬이온 배터리 재활용 산업 전문 애널리스트입니다. 아래 뉴스를 분석하여 JSON만 출력하세요.
오늘 날짜: {today}

[뉴스 목록]
{chr(10).join(article_list)}

[선별 기준]
- 오늘({today_str}) 또는 어제 기사 최우선
- 배터리 재활용, 블랙매스, 원재료(Li/Ni/Co), 공급망, 정책·규제, 투자·M&A 우선
- 출처가 'SMM Metal'인 기사는 무조건 최소 1건 이상 포함
- 단순 주가 등락, PR 배포, ETF, 학술 보도자료 제외

[정확도 주의사항]
- 본문에 구체적 기업명·협력사명·계약 규모·수치가 있으면 반드시 요약에 반영
- 계획 발표 ≠ 실제 시작. 반드시 구분
- 수치는 원문 그대로 기재

[트렌드 3개]
- 한국/중국/미국·EU 지역별 균형
- 오늘 기사의 특정 기업명·수치·정책명 직접 인용
- 금지 패턴: '중요성이 부각된다' 같은 뻔한 결론 절대 금지

[시사점 4~5개]
- 성일하이텍: 국내 최대 리튬이온 배터리 재활용. 블랙매스 생산 후 황산니켈·황산코발트·탄산리튬 판매
- 해외 법인: 미국(인디애나), 폴란드, 헝가리, 인도, 말레이시아, 중국
- '우리는' 또는 '성일하이텍은'으로 시작

[출력: JSON만. {{ 로 시작 }} 로 끝]
{{
  "articles": [{{
    "title": "원문 제목",
    "source": "출처",
    "date": "날짜",
    "link": "URL",
    "summary": "▪ [팩트] 기업명 전체·협력사명·구체적 계약/수치 포함 1~2줄.\\n▪ [밸류체인 영향] 확실한 영향만. 불확실하면 '정보 부족으로 판단 보류'.\\n▪ [체크 포인트] 원문에서 확인할 핵심 변수 1개.",
    "tag": "원재료 및 시황|투자 및 M&A|정책 및 규제|공급망 및 파트너십|기술 및 공정 중 하나",
    "region": "한국|중국|미국|EU|일본|글로벌"
  }}],
  "trends": [{{"title": "트렌드 제목", "body": "2~3문장"}}],
  "insights": ["시사점"]
}}

articles 6~8건(SMM Metal 최소 1건). trends 3개(지역 균형). insights 4~5개. 모든 텍스트 한국어."""

    model = genai.GenerativeModel("gemini-2.5-flash")
    for attempt in range(3):
        try:
            time.sleep(6)  # RPM 관리
            response = model.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r'```json|```', '', raw).strip()
            s, e = raw.index('{'), raw.rindex('}')
            return json.loads(raw[s:e+1])
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
        summary = esc(a.get("summary", "")).replace('\n', '<br>')
        return f"""
        <div style="border:1px solid #e0e4ea;border-radius:6px;padding:14px 16px;margin-bottom:12px;background:#fff;">
          <p style="font-size:14px;font-weight:700;color:#0f2744;margin:0 0 3px;">
            <a href="{esc(a.get('link',''))}" style="color:#0f2744;text-decoration:none;">{esc(a.get('title',''))}</a>
          </p>
          <p style="font-size:11px;color:#94a3b8;margin:0 0 8px;">{esc(a.get('source',''))} · {esc(a.get('date',''))}</p>
          <p style="font-size:13px;color:#374151;line-height:1.75;margin:0 0 10px;">{summary}</p>
          <span style="display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:10px;background:#dcfce7;color:#15803d;margin-right:5px;">{esc(a.get('region',''))}</span>
          <a href="{esc(a.get('link',''))}" style="font-size:11px;color:#ea580c;text-decoration:none;border:1px solid #fdba74;border-radius:10px;padding:2px 9px;">원문 보기</a>
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
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        smtp.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print(f"발송 완료 → {TO_EMAIL}")

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
