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
# SMM 시세 설정
# ============================================================
VAT_RATE = 1.13

SPOT_TARGETS = [
    {"name": "황산코발트",       "name_en": "Cobalt Sulphate",
     "url": "https://www-old.metal.com/Chemical-Compound/201102250381",
     "metal_content": 0.205, "metal_label": "Co"},
    {"name": "공업용 탄산리튬",   "name_en": "Industrial Li2CO3",
     "url": "https://www-old.metal.com/lithium/201905160001"},
    {"name": "배터리용 탄산리튬", "name_en": "Battery Li2CO3",
     "url": "https://www-old.metal.com/Lithium/201102250059"},
]

# 선물: Eastmoney 주연(主連) 페이지 — M계약 탐색 불필요, 항상 최근월 자동 롤링
FUTURES_EM = [
    {
        "name":      "탄산리튬 선물",
        "exchange":  "GFEX",
        "url":       "https://www.metal.com/gfex",   # SMM GFEX 전용 페이지 (Playwright)
        "ticker":    "LCM",
        "method":    "playwright",
        "sina_code": "nf_LCM",
    },
    {
        "name":      "니켈 선물",
        "exchange":  "LME",
        "url":       None,
        "ticker":    "LME·3M",
        "method":    "lme",                           # westmetall.com (requests)
        "sina_code": None,
    },
]

# ============================================================
# RSS 쿼리
# ============================================================
QUERIES = [
    {"q": '("황산니켈" OR "황산코발트" OR "탄산리튬" OR "수산화리튬") ("가격" OR "시황" OR "공급")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("nickel sulfate" OR "cobalt sulfate" OR "lithium carbonate" OR "lithium hydroxide") ("price" OR "market" OR "supply")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("nickel" OR "cobalt") ("battery" OR "supply chain") ("price" OR "shortage" OR "market" OR "index")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"lithium" ("battery" OR "recycling") ("price" OR "spot" OR "supply" OR "shortage")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("硫酸镍" OR "硫酸钴" OR "碳酸锂" OR "氢氧化锂") ("价格" OR "现货" OR "供应")',
     "lang": "zh-CN", "gl": "CN", "ceid": "CN:zh-CN"},
    {"q": '"SMM" ("nickel" OR "cobalt" OR "lithium" OR "black mass" OR "battery" OR "recycling")',
     "lang": "en", "gl": "US", "ceid": "US:en", "priority": True},
    {"q": '"Fastmarkets" ("nickel" OR "cobalt" OR "lithium" OR "black mass" OR "battery")',
     "lang": "en", "gl": "US", "ceid": "US:en", "priority": True},
    {"q": '"S&P Global" ("battery" OR "recycling" OR "black mass" OR "lithium carbonate" OR "nickel sulfate" OR "cobalt sulfate" OR "EV battery")',
     "lang": "en", "gl": "US", "ceid": "US:en", "priority": True},
    {"q": '"Benchmark Mineral Intelligence" OR "Benchmark Minerals" ("lithium" OR "battery" OR "cathode" OR "recycling")',
     "lang": "en", "gl": "US", "ceid": "US:en", "priority": True},
    {"q": '"성일하이텍" OR "에코프로씨엔지" OR "아이에스티엠씨" OR "IS에코솔루션"',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '"SungEel" OR "Sungeel HiTech" OR "IS Eco Solution"',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("Ascend Elements" OR "Redwood Materials" OR "Umicore") ("battery" OR "recycling" OR "black mass" OR "cathode")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"Glencore" ("cobalt" OR "nickel" OR "battery recycling" OR "black mass")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"Cirba Solutions" OR "Ecobat" OR "Retriev" OR "Ace Green" OR "Battery Resources" OR "Interco" OR "Princeton NuEnergy"',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("Fortum" OR "Stena Recycling" OR "BASF") ("battery" OR "recycling" OR "black mass")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("black mass" OR "battery scrap" OR "feedstock") ("price" OR "shortage" OR "tender" OR "payables")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("블랙매스" OR "폐배터리 스크랩") ("입찰" OR "매입가" OR "공급")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '"SK온" -목표주가 -목표가 -주가전망 -증권 -유상증자 -전환사채 -IR공시',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '"LG에너지솔루션" -목표주가 -목표가 -주가전망 -증권 -유상증자 -전환사채 -IR공시',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '"삼성SDI" -목표주가 -목표가 -주가전망 -증권 -유상증자 -전환사채 -IR공시',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("SK On" OR "LG Energy Solution" OR "Samsung SDI") -"price target" -"analyst" -"rating" -"upgrades" -"downgrades"',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("CATL" OR "BYD") ("battery recycling" OR "cathode" OR "black mass" OR "supply chain" OR "gigafactory")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("宁德时代" OR "比亚迪") ("电池回收" OR "回收" OR "黑粉" OR "原材料" OR "碳酸锂" OR "供应链")',
     "lang": "zh-CN", "gl": "CN", "ceid": "CN:zh-CN"},
    {"q": '"パナソニック" ("電池" OR "リサイクル" OR "リチウム" OR "EV")',
     "lang": "ja", "gl": "JP", "ceid": "JP:ja"},
    {"q": '"Northvolt" ("acquisition" OR "asset sale" OR "factory" OR "takeover" OR "insolvency")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("에코프로비엠" OR "엘앤에프" OR "포스코퓨처엠" OR "LG화학") -목표주가 -목표가 -증권',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("EcoPro BM" OR "L&F" OR "POSCO Future M" OR "LG Chem") ("precursor" OR "cathode" OR "battery")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("住友金属鉱山" OR "日亜化学") ("正極材" OR "前駆体" OR "リサイクル" OR "電池")',
     "lang": "ja", "gl": "JP", "ceid": "JP:ja"},
    {"q": '("Albemarle" OR "SQM" OR "Ganfeng" OR "Tianqi") ("lithium" OR "mine" OR "production" OR "supply")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("Pilbara Minerals" OR "Liontown" OR "Arcadium" OR "Sigma Lithium") ("lithium" OR "mine" OR "production" OR "supply")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"Indonesia" ("nickel" OR "HPAL" OR "nickel ore") ("export" OR "price" OR "quota" OR "HPM" OR "mine")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("nikel" OR "HPAL" OR "RKEF") ("harga" OR "ekspor" OR "tambang" OR "produksi" OR "kuota")',
     "lang": "id", "gl": "ID", "ceid": "ID:id"},
    {"q": '("DRC" OR "Congo") ("cobalt" OR "mining") ("production" OR "export" OR "price" OR "supply")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("hydrometallurgy" OR "hydromet" OR "HPAL") ("battery" OR "recycling" OR "nickel" OR "cobalt" OR "lithium")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("pyrometallurgy" OR "smelting" OR "direct recycling") ("battery" OR "black mass" OR "recycling")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("LFP" OR "lithium iron phosphate") ("recycling" OR "recovery" OR "black mass")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("습식제련" OR "건식제련" OR "HPAL" OR "직접재활용") ("배터리" OR "재활용" OR "블랙매스")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '("EU Battery Regulation" OR "Battery Passport" OR "recycled content" OR "battery directive") ("compliance" OR "deadline" OR "standard")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("IRA" OR "OBBBA" OR "critical minerals") ("battery" OR "recycling" OR "supply chain")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"India" ("battery recycling" OR "EPR" OR "black mass" OR "CPCB" OR "critical mineral")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '("이차전지" OR "사용후배터리" OR "폐배터리") ("EPR" OR "핵심광물" OR "순환이용" OR "재활용 의무" OR "생산자책임")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '"动力电池回收" ("政策" OR "标准" OR "法规")',
     "lang": "zh-CN", "gl": "CN", "ceid": "CN:zh-CN"},
    {"q": '"battery recycling" ("M&A" OR "acquisition" OR "joint venture" OR "investment" OR "funding")',
     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": '"배터리 재활용" ("투자" OR "JV" OR "파트너십" OR "인수" OR "합작")',
     "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": '"SungEel" OR "Samsung SDI" OR "SK On" OR "akkuhulladék" OR "akkumulátor" OR "újrahasznosít"',
     "lang": "hu", "gl": "HU", "ceid": "HU:hu"},
    {"direct_url": "https://www.google.com/alerts/feeds/03699096368296272379/11789334169558310879",
     "lang": "en"},
]

# ============================================================
# 노이즈 필터
# ============================================================
NOISE_KEYWORDS = [
    "crypto", "bitcoin", "ethereum", "nft", "dogecoin",
    "게임", "영화", "드라마", "리뷰", "car review", "smartphone review",
    "stock tip", "smartwatch",
    "battery etf", "lithium etf", "stocks:", "is it too late",
    "stock surges", "stock falls", "stock rises", "stock drops",
    "shares surge", "shares fall",
    "주가 상승", "주가 하락", "주가 급등", "주가 급락",
    "목표가 상향", "목표가 하향", "목표 주가", "투자의견", "유증", "유상증자",
    "주가 전망", "주가 목표", "증권 리포트", "analyst rating", "price target",
    "buy rating", "sell rating", "52주 신고가", "52주 신저가",
    "상한가", "하한가", "거래량 상위",
    "[ir]", "ir공시", "ir]", "뱅크 리포트", "리포트 브리핑",
    "투자분석", "브랜드 평판", "전환사채",
    "share price", "fundamentals", "dividend", "dividen",
    "ferrochrome", "shadow fleet",
    "flagship sedan", "driving range", "test drive",
    "0-100km", "top speed", "horsepower",
    "eurekaalert", "전자폐기물",
    "cassava", "agriculture", "crop",
    "petro", "petroleum", "oil refin",
    "dow jones", "s&p 500", "nasdaq",
    "blue whale season", "whale watching", "whale migration",
    "motorola", "samsung galaxy", "iphone", "ipad", "smartphone launch",
    "foldable phone", "razr", "pixel phone", "snapdragon",
    "launched in india", "goes on sale", "pre-order",
]

NOISE_SOURCES = [
    "openpr", "prnewswire", "businesswire", "globenewswire", "einpresswire",
    "accesswire", "prnews", "prlog", "marketwired", "newswire", "pr.com", "prweb",
    "discoveryalert", "bravenewcoin", "eurekaalert", "cryptoslate", "coindesk",
    "benzinga", "seekingalpha", "motleyfool", "investopedia", "indexbox",
    "msn", "msn.com", "aol.com", "simplywall.st", "futunn.com", "judal.co.kr",
    "investingnews.com", "thebull.com.au", "marketsmojo.com",
    "switzer.com.au", "nai500.com", "kalkinemedia.com",
]

NOISE_URL_PATHS = ["/stock/", "/en/stock/", "/stocks/", "/share-price/", "/equity/"]

NOISE_PAIRS = [
    ("plastic", "recycl"), ("alumin", "recycl"), ("bauxite", "recycl"),
    ("fiber", "recycl"), ("packaging", "recycl"), ("paper", "recycl"),
    ("recycled film", "feedstock"), ("scrap", "alumin"),
]

_NOISE_RE_KO = re.compile(
    r'(목표\s*주가|목표가)\s*(상향|하향|제시|유지|\d+만원|\d+달러|\d+억)'
    r'|\d+만원\s*(목표|하향|상향)'
    r'|(kb|nh투자|ibk투자|하나|미래에셋|키움|신한투자|대신|삼성|한국투자)증권\s*(전망|상향|하향|제시|목표|리포트|보고서)'
    r'|주가\s*(상승|하락|급등|급락|전망|목표)'
    r'|52주\s*(신고가|신저가)'
    r'|(상한가|하한가|거래정지)'
    r'|(유증|유상증자|전환사채|CB\s*발행)'
    r'|(코스닥|코스피)\s*(거래량|상위|순위)'
    r'|수익률.{0,10}(주가|투자|%)'
    r'|(애널리스트|analyst).{0,15}(전망|목표|제시|rating|target)'
    r'|\[IR\]|\[ir\]|IR공시|IR\s*행사',
    re.IGNORECASE
)

_NOISE_RE_EN = re.compile(
    r'(raises?|cuts?|lifts?|lowers?|maintains?|reiterates?)\s*(price\s*)?target'
    r'|price\s*target\s*(raised|cut|lifted|lowered|increased|decreased)'
    r'|(upgrades?|downgrades?)\s*(to\s*)?(buy|hold|sell|overweight|underweight|neutral)'
    r'|analyst\s*(rating|note|report|target)'
    r'|stock\s*(surges?|soars?|falls?|drops?|rises?|climbs?)\s*\d+\s*%'
    r'|shares\s*(up|down)\s*\d+\s*%'
    r'|(bank of america|goldman sachs|morgan stanley|jpmorgan|daiwa|macquarie|barclays|ubs|citigroup)\s*(raises?|cuts?|initiates?|target)'
    r'|investor\s*(relations|day|briefing)'
    r'|earnings\s*call\s*transcript'
    r'|leads?\s+stock\s+performance'
    r'|share\s*price\s*and\s*fundamentals'
    r'|\d+\.?\d*%\s*(return|gain|rise)\s',
    re.IGNORECASE
)

def is_stock_noise(title: str) -> bool:
    return bool(_NOISE_RE_KO.search(title) or _NOISE_RE_EN.search(title))

WHITELIST = [
    "battery", "배터리", "전지", "이차전지", "사용후배터리", "폐배터리",
    "recycl", "재활용", "순환이용",
    "lithium", "리튬", "nickel", "니켈", "cobalt", "코발트",
    "black mass", "블랙매스",
    "cathode", "양극재", "precursor", "전구체",
    "anode", "electrolyte", "feedstock", "scrap", "스크랩",
    "황산니켈", "황산코발트", "탄산리튬", "수산화리튬",
    "nickel sulfate", "cobalt sulfate", "lithium carbonate", "lithium hydroxide",
    "hydrometallurgy", "hydromet", "hpal",
    "pyrometallurgy", "smelting", "습식제련", "건식제련",
    "lfp", "lithium iron phosphate",
    "gigafactory", "kwh", "mwh", "ev ", "electric vehicle",
    "fastmarkets", "benchmark mineral", "s&p global", "smm",
    "sungeel", "성일", "ascend", "redwood", "cirba", "ecobat", "umicore", "glencore",
    "retriev", "battery resources", "interco", "princeton nuenergy",
    "is eco solution", "fortum", "stena",
    "samsung", "sk온", "sk on", "lg에너지솔루션", "lg energy solution", "삼성sdi",
    "catl", "byd", "panasonic", "northvolt",
    "에코프로비엠", "에코프로", "포스코퓨처엠", "엘앤에프", "성일하이텍",
    "albemarle", "sqm", "ganfeng", "tianqi",
    "pilbara", "liontown", "arcadium", "sigma lithium",
    "circular economy", "생산자책임",
    "nikel", "tambang", "rkef",
    "akkumulátor", "akkuhulladék",
    "电池", "回收", "锂", "镍", "钴", "宁德时代", "比亚迪",
    "リサイクル", "電池", "リチウム", "ニッケル", "コバルト",
]

# ============================================================
# 유틸
# ============================================================
def decode_entities(text):
    return html_lib.unescape(text or "")

def esc(text):
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

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
    if "google.com/url" in url:
        match = re.search(r'[?&]url=([^&]+)', url)
        if match:
            return urllib.parse.unquote(match.group(1))
    return url

# ============================================================
# SMM 시세 수집
# ============================================================
def get_usd_cny_rate() -> float:
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=CNY", timeout=10)
        rate = resp.json()["rates"]["CNY"]
        print(f"  환율: 1 USD = {rate:.4f} CNY")
        return rate
    except Exception as e:
        print(f"  환율 조회 실패({e}), 기본값 7.25")
        return 7.25


async def _scrape_lme_nickel_playwright(page) -> dict:
    """LME 공식 사이트에서 니켈 Cash · 3-month Offer 가격 수집 (Playwright).
    Offer = 공식 종가(Settlement) 기준. 전일 결산가 (T-1).
    Returns: {cash, cash_pct, m3, m3_pct, date}
    """
    try:
        await page.goto(
            "https://www.lme.com/metals/non-ferrous/lme-nickel#Summary",
            wait_until="domcontentloaded",
            timeout=30000
        )
        await page.wait_for_timeout(5000)   # JS 렌더링 대기

        # "LME Nickel Official Prices" 테이블에서 Cash·3M Offer 추출
        result = await page.evaluate("""
            () => {
                const rows = Array.from(document.querySelectorAll('tr'));
                let cash = null, m3 = null;
                for (const row of rows) {
                    const cells = Array.from(row.querySelectorAll('td'));
                    if (cells.length < 3) continue;
                    const label = cells[0].textContent.trim();
                    const offer  = parseFloat(cells[2].textContent.replace(/[^0-9.]/g, ''));
                    if (label === 'Cash'    && offer > 10000) cash = offer;
                    if (label === '3-month' && offer > 10000) m3   = offer;
                    if (cash && m3) break;
                }
                return {cash, m3};
            }
        """)

        cash = result.get("cash")
        m3   = result.get("m3")

        if not cash or not m3:
            print(f"  LME Playwright 파싱 실패: cash={cash}, m3={m3}")
            return {}

        # 등락률: 페이지 상단 hero에서 % 추출 (3-month closing)
        text  = await page.inner_text("body")
        pct_m = re.search(r'([+\-]\d+\.\d+)%', text)
        m3_pct = f"{float(pct_m.group(1)):+.2f}%" if pct_m else "N/A"

        # cash 전일 등락은 페이지에 없음 → m3_pct 참고용으로 동일 사용
        print(f"  LME Nickel (lme.com): Cash=${cash:,.0f}, 3M=${m3:,.0f} ({m3_pct})")
        return {
            "cash":     cash,
            "cash_pct": m3_pct,   # T-1 기준, 페이지에 Cash 단독 pct 없음
            "m3":       m3,
            "m3_pct":   m3_pct,
            "date":     datetime.now().strftime("%d. %b %Y"),
        }

    except Exception as e:
        print(f"  LME lme.com 오류: {e}")
        return {}
    try:
        resp = requests.get(
            "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Ni_cash",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        if resp.status_code != 200:
            print(f"  LME 니켈 HTTP {resp.status_code}")
            return {}

        html = resp.text
        # 디버그: 응답 첫 200자 출력 (차단 여부 확인용)
        print(f"  LME 응답 첫 200자: {html[:200].replace(chr(10), ' ')}")

        # raw HTML에서 <td> 값 추출 (markdown 파이프 아님)
        raw_tds = re.findall(r'<td[^>]*>(.*?)</td>', html, re.DOTALL | re.IGNORECASE)
        # HTML 엔티티 정리
        def clean_td(s):
            return re.sub(r'<[^>]+>', '', s).replace('&nbsp;', ' ').replace('&amp;', '&').strip()
        tds = [clean_td(t) for t in raw_tds if clean_td(t)]

        date_re = re.compile(r'^\d+\.\s+\w+\s+\d{4}$')
        num_re  = re.compile(r'^[\d,]+\.\d+$')

        # 날짜 뒤에 숫자 3개(cash, 3month, stock) 묶기
        rows = []
        i = 0
        while i < len(tds):
            if date_re.match(tds[i]):
                nums = []
                j = i + 1
                while j < len(tds) and len(nums) < 3:
                    if num_re.match(tds[j]):
                        nums.append(float(tds[j].replace(',', '')))
                    elif nums:  # 숫자가 하나라도 있으면 비숫자에서 중단
                        break
                    j += 1
                if len(nums) >= 2:
                    rows.append((tds[i], nums[0], nums[1]))
                i = j
            else:
                i += 1

        if len(rows) < 2:
            print(f"  LME 니켈 파싱 실패 (rows={len(rows)}, tds={len(tds)})")
            print(f"  LME 샘플: {tds[:10]}")
            return {}

        cash    = rows[0][1]
        m3      = rows[0][2]
        prev_c  = rows[1][1]
        prev_3m = rows[1][2]

        cash_pct = f"{(cash - prev_c)  / prev_c  * 100:+.2f}%"
        m3_pct   = f"{(m3   - prev_3m) / prev_3m * 100:+.2f}%"

        print(f"  LME 니켈: Cash=${cash:,.0f}({cash_pct}), 3M=${m3:,.0f}({m3_pct}) [{rows[0][0]}]")
        return {
            "cash":     cash,
            "cash_pct": cash_pct,
            "m3":       m3,
            "m3_pct":   m3_pct,
            "date":     rows[0][0],
        }
    except Exception as e:
        print(f"  LME 니켈 오류: {e}")
        return {}


async def _scrape_spot(page, target: dict) -> dict:
    base = {"name": target["name"], "name_en": target["name_en"]}
    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        text = await page.inner_text("body")

        usd_list = re.findall(
            r"([\d]{1,3}(?:,\d{3})*(?:\.\d+)?)\s*\n\s*USD/t(?:onne)?", text)
        cny_list = re.findall(
            r"([\d]{1,3}(?:,\d{3})*(?:\.\d+)?)\s*\n\s*yuan/t(?:onne)?", text)

        all_pcts = re.findall(r"[+\-][\d,]+\.?\d*\s*\(([+\-]?\d+\.?\d*%)\)", text)
        change_pct = next((p for p in all_pcts if p != "0%"), "N/A")

        date_m = re.search(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})", text)

        usd_excl = float(usd_list[0].replace(",", "")) if usd_list else None
        cny_incl = float(cny_list[0].replace(",", "")) if cny_list else None
        cny_excl = round(cny_incl / VAT_RATE) if cny_incl else None

        mc = target.get("metal_content")
        ml = target.get("metal_label")
        usd_metal = round(usd_excl / mc) if (usd_excl and mc) else None
        cny_metal = round(cny_excl / mc) if (cny_excl and mc) else None

        return {
            **base,
            "date":          date_m.group(1) if date_m else "N/A",
            "usd_excl":      usd_excl,
            "cny_incl":      cny_incl,
            "cny_excl":      cny_excl,
            "usd_metal":     usd_metal,
            "cny_metal":     cny_metal,
            "metal_content": mc,
            "metal_label":   ml,
            "change_pct":    change_pct,
            "status":        "OK",
        }
    except Exception as e:
        return {**base, "status": f"ERROR: {e}"}

def _fetch_sina_price(sina_code: str) -> tuple:
    """Sina Finance hq API로 선물 주연 최신가 수집.
    Playwright 불필요, requests로 즉시 반환.
    Returns: (price_vat_incl: int | None, change_pct: str)
    """
    try:
        resp = requests.get(
            f"https://hq.sinajs.cn/list={sina_code.lower()}",
            timeout=8,
            headers={
                "Referer": "https://finance.sina.com.cn/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
        )
        if resp.status_code != 200:
            print(f"  Sina [{sina_code}] HTTP {resp.status_code}")
            return None, "N/A"

        m = re.search(r'"([^"]*)"', resp.text)
        if not m or len(m.group(1)) < 5:
            print(f"  Sina [{sina_code}] 빈 응답: {resp.text[:80]}")
            return None, "N/A"

        parts = [p.strip() for p in m.group(1).split(',')]
        print(f"  Sina [{sina_code}]: {parts[:9]}")

        # 최신가: parts[1:8] 중 30000~600000 범위 첫 번째 숫자
        price = None
        for p in parts[1:8]:
            try:
                v = float(p)
                if 30000 <= v <= 600000:
                    price = int(v)
                    break
            except Exception:
                continue

        # 등락률: 昨결산(parts[7]) 기준 직접 계산
        change_pct = "N/A"
        if price and len(parts) > 7:
            try:
                prev = float(parts[7])
                if 30000 <= prev <= 600000:
                    change_pct = f"{(price - prev) / prev * 100:+.2f}%"
            except Exception:
                pass

        return price, change_pct

    except Exception as e:
        print(f"  Sina 오류 [{sina_code}]: {e}")
        return None, "N/A"


def _fetch_exchange_settlement(target: dict) -> tuple:
    """거래소 공식 당일 결산가 API 수집 (Playwright 불필요).

    SHFE (니켈): https://www.shfe.com.cn/data/dailydata/kx/kx{YYYYMMDD}.dat
    GFEX (탄산리튬): http://www.gfex.com.cn 계열 API 시도

    주계약 = 미결제약정(OPENINTEREST) 최대 계약.
    Returns: (price_vat_incl: int | None, change_pct: str)
    """
    today = datetime.now().strftime("%Y%m%d")
    exchange = target["exchange"]
    product  = target["ticker"].lower()  # "lcm" or "nim"

    # ── SHFE 니켈 ────────────────────────────────────────────────────
    if exchange == "SHFE":
        urls = [
            f"https://www.shfe.com.cn/data/dailydata/kx/kx{today}.dat",
            # 전날 데이터 fallback (주말/공휴일 등)
            f"https://www.shfe.com.cn/data/dailydata/kx/kx{(datetime.now() - timedelta(days=1)).strftime('%Y%m%d')}.dat",
        ]
        for url in urls:
            try:
                resp = requests.get(url, timeout=10,
                    headers={"Referer": "https://www.shfe.com.cn/",
                             "User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    continue
                data = resp.json()
                contracts = [
                    x for x in data.get("o_curinstrument", [])
                    if str(x.get("PRODUCTID", "")).strip().lower() == "ni"
                    and float(x.get("SETTLEMENTPRICE") or 0) > 0
                ]
                if not contracts:
                    continue
                main = max(contracts, key=lambda x: float(x.get("OPENINTEREST") or 0))
                settle = int(float(main["SETTLEMENTPRICE"]))
                prev   = float(main.get("PRESETTLEMENTPRICE") or 0)
                pct    = f"{(settle-prev)/prev*100:+.2f}%" if prev else "N/A"
                month  = str(main.get("DELIVERYMONTH", "")).strip()
                print(f"  SHFE 결산 NI{month}: {settle:,} CNY/t ({pct})")
                return settle, pct
            except Exception as e:
                print(f"  SHFE API 오류: {e}")
        return None, "N/A"

    # ── GFEX 탄산리튬 ─────────────────────────────────────────────────
    elif exchange == "GFEX":
        # GFEX 공식 일별 결산가 엔드포인트 (여러 패턴 시도)
        gfex_urls = [
            f"https://www.gfex.com.cn/u/interfacesWebTyre/getSettlementInfo?variety=lc&trade_date={today}",
            f"http://www.gfex.com.cn/u/interfacesWebTyre/getSettlementInfo?variety=lc&trade_date={today}",
            f"https://www.gfex.com.cn/gfex/cjsj/historysettlementprice_list.shtml?variety=lc&trade_date={today}",
        ]
        for url in gfex_urls:
            try:
                resp = requests.get(url, timeout=10,
                    headers={"Referer": "https://www.gfex.com.cn/",
                             "User-Agent": "Mozilla/5.0",
                             "Accept": "application/json, text/plain, */*"})
                if resp.status_code != 200:
                    continue
                raw = resp.text.strip()
                if not raw or len(raw) < 10:
                    continue
                # JSON 응답 시도
                try:
                    data = resp.json()
                    contracts = data if isinstance(data, list) else data.get("data", [])
                    contracts = [x for x in contracts
                                 if float(x.get("settlementPrice") or x.get("SETTLEMENTPRICE") or 0) > 0]
                    if not contracts:
                        continue
                    main   = max(contracts, key=lambda x: float(
                        x.get("openInterest") or x.get("OPENINTEREST") or 0))
                    settle = int(float(main.get("settlementPrice") or main.get("SETTLEMENTPRICE")))
                    prev   = float(main.get("preSettlementPrice") or main.get("PRESETTLEMENTPRICE") or 0)
                    pct    = f"{(settle-prev)/prev*100:+.2f}%" if prev else "N/A"
                    print(f"  GFEX 결산 LC: {settle:,} CNY/t ({pct})")
                    return settle, pct
                except Exception:
                    pass
                # 숫자 파싱 fallback
                nums = re.findall(r'\b(1[0-9]{4,5}|[5-9][0-9]{4})\b', raw)
                if nums:
                    settle = int(nums[0])
                    print(f"  GFEX fallback LC: {settle:,}")
                    return settle, "N/A"
            except Exception as e:
                print(f"  GFEX API 오류 ({url[:50]}): {e}")
        print(f"  GFEX API 전체 실패 → N/A")
        return None, "N/A"

    return None, "N/A"


async def _scrape_lcm_playwright(page, target: dict) -> dict:
    """www.metal.com/gfex Playwright로 탄산리튬 선물 주계약 가격 수집.
    GFEX 전용 페이지라 LC 가격대(100,000~300,000 CNY/t)가 다른 품목과 겹치지 않음.
    """
    display = f"{target['exchange']}·{target['ticker']}"
    base = {"name": target["name"], "exchange": target["exchange"], "ticker": display}

    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4000)

        # 데이터 추출 후 페이지 polling JS 강제 중단 (이벤트 루프 점유 방지)
        try:
            await page.evaluate("window.stop()")
        except Exception:
            pass

        price = await page.evaluate("""
            () => {
                // 콤마 제거 후 탐색 — "191,760" → "191760"
                const text = (document.body ? document.body.innerText : '')
                             .replace(/[,，]/g, '');
                // LC 탄산리튬: 100,000~300,000 CNY/t
                // GFEX 타품목: 工业硅 8000~12000, 多晶硅 30000~50000 → 범위 겹침 없음
                const nums = text.match(/[1-9]\\d{4,5}/g) || [];
                for (const s of nums) {
                    const n = parseInt(s);
                    if (n >= 100000 && n <= 300000) return n;
                }
                return null;
            }
        """)

        text = await page.inner_text("body")
        pct_m = re.search(r'([+\-]\d+\.\d+%)', text)
        change_pct = pct_m.group(1) if pct_m else "N/A"

        print(f"  metal.com/gfex LCM: price={price}, pct={change_pct}")

        if price:
            return {
                **base,
                "date":            datetime.now().strftime("%b %d, %Y"),
                "latest":          price,
                "latest_vat_excl": round(price / VAT_RATE),
                "change_pct":      change_pct,
                "prev_close":      None,
                "status":          "OK",
            }
    except Exception as e:
        print(f"  metal.com/gfex 오류: {e}")

    return {**base, "status": "ERROR: 가격 파싱 실패"}


def _scrape_nim_api(target: dict) -> dict:
    """SHFE 공식 결산가 API로 니켈 주계약 가격 수집 (Playwright 불사용)."""
    display = f"{target['exchange']}·{target['ticker']}"
    base = {"name": target["name"], "exchange": target["exchange"], "ticker": display}

    # 1차: Sina
    price, change_pct = _fetch_sina_price(target["sina_code"])
    if price:
        print(f"  Sina OK {display}: {price:,}")
        return {**base, "date": datetime.now().strftime("%b %d, %Y"),
                "latest": price, "latest_vat_excl": round(price / VAT_RATE),
                "change_pct": change_pct, "prev_close": None, "status": "OK"}

    # 2차: SHFE 공식 API
    print(f"  Sina 실패 → SHFE API {display}")
    price, change_pct = _fetch_exchange_settlement(target)
    if price:
        return {**base, "date": datetime.now().strftime("%b %d, %Y"),
                "latest": price, "latest_vat_excl": round(price / VAT_RATE),
                "change_pct": change_pct, "prev_close": None, "status": "OK"}

    return {**base, "status": "ERROR: 가격 파싱 실패"}


async def scrape_smm_prices(usd_cny: float = 7.25) -> dict:
    spot_results, futures_results = [], []
    print("\n[SMM·LME 시세 수집]")

    lme_ni = {}   # Playwright 브라우저 기동 후 수집

    def _make_lme_ni_entry():
        if lme_ni:
            return {
                "name":          "니켈",
                "name_en":       "LME Nickel",
                "source":        "LME",
                "date":          lme_ni["date"],
                "usd_excl":      lme_ni["cash"],
                "cny_incl":      None,
                "cny_excl":      round(lme_ni["cash"] * usd_cny),
                "usd_metal":     None,
                "cny_metal":     None,
                "metal_content": None,
                "metal_label":   None,
                "change_pct":    lme_ni["cash_pct"],
                "delayed":       True,
                "status":        "OK",
            }
        return {"name": "니켈", "name_en": "LME Nickel",
                "source": "LME", "status": "ERROR: 수집 실패"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await ctx.new_page()

        # ── LME 니켈: lme.com Playwright 수집 ─────────────────────────
        print("  LME 니켈 수집 중...", end=" ", flush=True)
        lme_ni = await _scrape_lme_nickel_playwright(page)
        if lme_ni:
            print(f"OK Cash=${lme_ni['cash']:,.0f}, 3M=${lme_ni['m3']:,.0f}")
        else:
            print("W 실패")

        for t in SPOT_TARGETS:
            print(f"  현물: {t['name']} ...", end=" ", flush=True)
            r = await _scrape_spot(page, t)
            spot_results.append(r)
            print("OK" if r["status"] == "OK" else f"W {r['status']}")
            # ★ 코발트 다음에 LME 니켈 삽입 → 순서: 코발트, 니켈, TG리튬, BG리튬
            if t["name"] == "황산코발트":
                ni_entry = _make_lme_ni_entry()
                spot_results.append(ni_entry)
                status_str = f"${lme_ni['cash']:,.0f} ({lme_ni['cash_pct']})" if lme_ni else "ERROR"
                print(f"  현물: 니켈(LME) ... {status_str}")
            await asyncio.sleep(2)

        for t in FUTURES_EM:
            print(f"  선물: {t['name']}({t['exchange']}) ...", end=" ", flush=True)
            if t.get("method") == "playwright":
                r = await _scrape_lcm_playwright(page, t)
                # GFEX live polling 완전 제거: 브라우저 재시작
                # (page.close() / about:blank 는 WebSocket 연결로 인해 blocking 발생)
                try:
                    await browser.close()
                    browser = await p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                    )
                    ctx  = await browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        ),
                        locale="en-US",
                    )
                    page = await ctx.new_page()
                except Exception as e:
                    print(f"  브라우저 재시작 오류: {e}")
            elif t.get("method") == "lme":
                # LME 3개월물 — 앞서 수집한 lme_ni 재사용
                if lme_ni:
                    r = {
                        "name":            t["name"],
                        "exchange":        "LME",
                        "ticker":          "LME·3M",
                        "source":          "LME",
                        "date":            lme_ni["date"],
                        "latest":          round(lme_ni["m3"]),
                        "latest_vat_excl": round(lme_ni["m3"] * usd_cny),
                        "change_pct":      lme_ni["m3_pct"],
                        "delayed":         True,
                        "status":          "OK",
                    }
                    print(f"OK (LME·3M ${lme_ni['m3']:,.0f})")
                else:
                    r = {"name": t["name"], "exchange": "LME",
                         "ticker": "LME·3M", "status": "ERROR: LME 데이터 없음"}
                    print("W LME 데이터 없음")
                futures_results.append(r)
                continue
            else:
                r = _scrape_nim_api(t)
            futures_results.append(r)
            print(f"OK ({r.get('ticker','?')})" if r["status"] == "OK" else f"W {r['status']}")

        await browser.close()

    return {"spot": spot_results, "futures": futures_results}


def compute_spreads(price_data: dict) -> dict:
    spot_map    = {r["name"]: r for r in price_data["spot"]    if r["status"] == "OK"}
    futures_map = {r["exchange"]: r for r in price_data["futures"] if r["status"] == "OK"}
    spreads = {}

    lc_data = futures_map.get("GFEX", {})
    lc_s    = spot_map.get("공업용 탄산리튬", {}).get("cny_excl")
    lc_f    = lc_data.get("latest_vat_excl")
    lc_tick = lc_data.get("ticker", "GFEX·LC????").split("·")[-1]
    if lc_s and lc_f:
        diff = lc_s - lc_f
        spreads["탄산리튬"] = {
            "spot": lc_s, "futures": lc_f, "ticker": lc_tick,
            "spread": diff, "spread_pct": diff / lc_f * 100,
            "structure": "백워데이션" if diff > 0 else "콘탱고",
        }

    # LME 니켈: Cash(현물) vs 3M(선물) — 모두 USD 기준
    ni_data   = futures_map.get("LME", {})
    ni_spot_r = spot_map.get("니켈", {})
    ni_s      = ni_spot_r.get("usd_excl")   # LME Cash (USD/t)
    ni_f      = ni_data.get("latest")        # LME 3M (USD/t)
    if ni_s and ni_f:
        diff = ni_s - ni_f
        spreads["니켈"] = {
            "spot_metal": ni_s, "futures": ni_f, "ticker": "3M",
            "spread": diff, "spread_pct": diff / ni_f * 100,
            "structure": "백워데이션" if diff > 0 else "콘탱고",
            "unit": "USD",
        }

    return spreads


def format_price_for_prompt(price_data: dict, usd_cny: float, spreads: dict) -> str:
    lines = [f"수집: {datetime.now().strftime('%H:%M')} KST | USD/CNY: {usd_cny:.2f}"]

    lines.append("\n[현물 - 증치세제외 기준 (한국->중국 수출가)]")
    for r in price_data["spot"]:
        if r["status"] != "OK":
            continue
        metal_str = ""
        if r.get("usd_metal"):
            metal_str = f" | {r['metal_label']}금속환산: ${r['usd_metal']:,.0f} / CNY{r['cny_metal']:,.0f}"
        lines.append(
            f"  {r['name']}: ${r['usd_excl']:,.0f}/t{metal_str}"
            f" | CNY{r['cny_excl']:,.0f}(제외) | {r['change_pct']}"
        )

    lines.append("\n[선물 - 증치세제외 환산]")
    for r in price_data["futures"]:
        if r["status"] != "OK":
            continue
        ve = r.get("latest_vat_excl")
        ue = round(ve / usd_cny) if ve else None
        lines.append(
            f"  {r['name']}({r.get('ticker','')}): ${ue:,.0f} / CNY{ve:,.0f}"
            f" | 고시가CNY{r.get('latest', 0):,.0f}(포함) | {r['change_pct']}"
        )

    lines.append("\n[현선물 스프레드]")
    if "탄산리튬" in spreads:
        s = spreads["탄산리튬"]
        lines.append(
            f"  탄산리튬({s['ticker']}): 현물CNY{s['spot']:,.0f} vs 선물CNY{s['futures']:,.0f}"
            f" -> {s['structure']} ({s['spread']:+,.0f}, {s['spread_pct']:+.1f}%)"
        )
    if "니켈" in spreads:
        s = spreads["니켈"]
        lines.append(
            f"  니켈LME({s['ticker']}): Cash${s['spot_metal']:,.0f} vs 3M${s['futures']:,.0f}"
            f" -> {s['structure']} ({s['spread']:+,.0f}, {s['spread_pct']:+.1f}%) [T-1]"
        )

    return "\n".join(lines)

# ============================================================
# RSS 수집
# ============================================================
def collect_rss():
    now        = datetime.utcnow()
    cutoff_48h = now - timedelta(hours=48)
    cutoff_72h = now - timedelta(hours=72)
    raw  = []
    seen = set()

    for item in QUERIES:
        is_smm      = "direct_url" in item
        cutoff      = cutoff_72h if is_smm else cutoff_48h
        is_priority = item.get("priority", False)

        try:
            if is_smm:
                url  = item["direct_url"]
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                print(f"SMM 피드 응답코드: {resp.status_code}")
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                # 디버그: 피드 엔트리 수 확인
                ns_dbg = {"atom": "http://www.w3.org/2005/Atom"}
                is_atom_dbg = root.tag.endswith("feed")
                dbg_entries = root.findall(".//atom:entry", ns_dbg) if is_atom_dbg else root.findall(".//item")
                print(f"  SMM 피드 파싱: is_atom={is_atom_dbg}, entries={len(dbg_entries)}")
            else:
                q   = item["q"] + " when:3d"
                url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}"
                       f"&hl={item['lang']}&gl={item['gl']}&ceid={item['ceid']}&num=10"
                       f"&cb={int(now.timestamp())}")
                resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)

            ns      = {"atom": "http://www.w3.org/2005/Atom"}
            is_atom = root.tag.endswith("feed")
            entries = root.findall(".//atom:entry", ns) if is_atom else root.findall(".//item")

            for entry in entries:
                if is_atom:
                    title_el = entry.find("atom:title", ns) or entry.find("title")
                    # Google Alerts <title type="html"><b>...</b></title> 구조 처리
                    # title_el.text는 None → itertext()로 child element 포함 전체 text 추출
                    raw_title = ''.join(title_el.itertext()) if title_el is not None else ""
                    title     = decode_entities(raw_title)
                    title     = re.sub(r'<[^>]+>', '', title).strip()
                    link_el  = entry.find("atom:link", ns)
                    link     = link_el.get("href", "") if link_el is not None else ""
                    link     = extract_real_url(link)
                    pub_str  = (entry.findtext("atom:published", "", ns) or
                                entry.findtext("atom:updated", "", ns))
                    source   = "SMM Metal"
                    snippet  = decode_entities(re.sub(r'<[^>]+>', '', (
                        entry.findtext("atom:summary", "", ns) or
                        entry.findtext("atom:content", "", ns) or ""
                    )))[:200]
                else:
                    title   = decode_entities((entry.findtext("title") or "").strip())
                    link    = (entry.findtext("link") or "").strip()
                    link    = extract_real_url(link)
                    pub_str = (entry.findtext("pubDate") or "").strip()
                    source_el = entry.find("source")
                    source  = source_el.text.strip() if source_el is not None else ""
                    snippet = decode_entities(
                        re.sub(r'<[^>]+>', '', entry.findtext("description") or "")
                    )[:200]

                if not title or not link or link in seen:
                    if is_smm and not title:
                        print(f"  SMM 필터: 제목없음")
                    elif is_smm and not link:
                        print(f"  SMM 필터: 링크없음 | 제목={title[:40]}")
                    elif is_smm and link in seen:
                        print(f"  SMM 필터: 중복 | {title[:40]}")
                    continue

                pub_date = parse_date(pub_str)
                if pub_date and pub_date < cutoff:
                    if is_smm:
                        print(f"  SMM 필터: 오래됨({pub_date.date()}) | {title[:40]}")
                    continue

                if "metal.com" in link.lower():
                    source = "SMM Metal"

                lt = title.lower()
                ls = source.lower()
                ll = link.lower()

                if any(s in ls or s in ll for s in NOISE_SOURCES):
                    continue
                if any(p in ll for p in NOISE_URL_PATHS):
                    continue
                if any(k in lt for k in NOISE_KEYWORDS):
                    continue
                if any(a in lt and b in lt for a, b in NOISE_PAIRS):
                    continue
                if is_stock_noise(title):
                    continue
                if source != "SMM Metal":
                    if not any(w in lt for w in WHITELIST):
                        continue

                seen.add(link)
                raw.append({
                    "title": title, "link": link, "source": source,
                    "pub": pub_str, "pub_date": pub_date,
                    "lang": item.get("lang", "en"), "snippet": snippet,
                    "priority": is_priority,
                })

            time.sleep(0.12)
        except Exception as e:
            print(f"RSS 오류: {e}")

    raw.sort(key=lambda x: x.get("pub_date") or datetime.min, reverse=True)

    company_day_count = {}
    deduped = []
    for a in raw:
        tl      = a["title"].lower()
        pub_day = a["pub_date"].strftime("%Y-%m-%d") if a.get("pub_date") else "unknown"
        words   = {w for w in re.sub(r'[^\w\s]', ' ', a["title"]).split() if len(w) >= 2}
        is_dup  = any(
            len(words & {w for w in re.sub(r'[^\w\s]', ' ', b["title"]).split() if len(w) >= 2}) >= 3
            for b in deduped
        )
        if is_dup:
            continue
        for co in ["lg에너지솔루션", "sk온", "삼성sdi", "에코프로비엠", "catl", "byd"]:
            if co in tl:
                k = f"{co}_{pub_day}"
                company_day_count[k] = company_day_count.get(k, 0) + 1
                if company_day_count[k] > 3:
                    is_dup = True
                break
        if not is_dup:
            deduped.append(a)

    sc = sum(1 for a in deduped if "SMM" in a.get("source", ""))
    pc = sum(1 for a in deduped if a.get("priority"))
    print(f"수집: {len(raw)}건 -> 중복제거: {len(deduped)}건 (SMM:{sc}건, 시황매체:{pc}건)")
    return deduped

# ============================================================
# Jina 본문 추출
# ============================================================
def fetch_body(real_url):
    try:
        resp = requests.get(
            f"https://r.jina.ai/{real_url}",
            timeout=(10, 45),
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if resp.status_code == 200:
            return resp.text[:3000]
    except Exception as e:
        print(f"Jina 오류: {e}")
    return ""

async def get_real_url(page, cbm_url):
    """
    Google News CBMi URL → 실제 기사 URL (Playwright).
    ?oc=5 → &hl=en-US... → 실제 URL 두 단계 redirect 처리.
    page.goto interrupt 예외는 정상 흐름이므로 무시하고 wait_for_url로 계속.
    """
    try:
        await page.goto(cbm_url, wait_until="commit", timeout=15000)
    except Exception:
        # Google이 ?oc=5 → &hl=en-US... 로 redirect 시 Playwright가
        # "interrupted by another navigation" 예외를 던짐 → 무시하고 계속
        pass

    try:
        await page.wait_for_url(
            lambda url: "news.google.com" not in url, timeout=10000)
    except:
        pass

    final_url = page.url
    if "news.google.com" not in final_url:
        return final_url
    return None

# ============================================================
# 본문 수집
# ============================================================
_BATTERY_RELEVANCE_KW = [
    "battery", "배터리", "recycl", "재활용", "black mass", "블랙매스",
    "lithium", "리튬", "nickel", "니켈", "cobalt", "코발트",
    "cathode", "양극재", "precursor", "전구체",
    "황산니켈", "황산코발트", "탄산리튬", "수산화리튬",
    "nickel sulfate", "cobalt sulfate", "lithium carbonate",
    "hpal", "hydromet", "lfp", "ev ", "electric vehicle",
    "gigafactory", "feedstock", "scrap",
    "nickel ore", "nikel", "tambang",
    "电池", "回收", "锂", "镍", "钴", "akkumulátor",
]

def is_battery_relevant(title: str) -> bool:
    return any(k in title.lower() for k in _BATTERY_RELEVANCE_KW)

async def enrich_articles(articles):
    smm = [a for a in articles if "SMM" in a.get("source", "")][:2]
    sk  = ["성일하이텍", "sungeel", "성일"]
    sungeel = [a for a in articles
               if "SMM" not in a.get("source", "")
               and any(k in a["title"].lower() for k in sk)]
    priority = [a for a in articles
                if a.get("priority") and "SMM" not in a.get("source", "")
                and a not in sungeel
                and is_battery_relevant(a["title"])][:3]
    general_pool = [a for a in articles
                    if "SMM" not in a.get("source", "")
                    and a not in sungeel and a not in priority]
    recycling_boost = [a for a in general_pool
                       if any(k in a["title"].lower() for k in [
                           "battery recycl", "ev recycl", "black mass", "블랙매스",
                           "배터리 재활용", "폐배터리", "사용후배터리",
                           "hydromet", "hpal", "이차전지 재활용"])]
    others  = [a for a in general_pool if a not in recycling_boost]
    general = (recycling_boost + others)[:max(0, 15 - len(sungeel) - len(priority))]
    targets = smm + sungeel + priority + general

    print(f"\n본문추출: SMM{len(smm)}+성일{len(sungeel)}+시황{len(priority)}+일반{len(general)}={len(targets)}건")

    browser = None
    async with async_playwright() as p:
        try:
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
                        print(f"  OK Jina ({len(body)}자)")
                    else:
                        body_snippet += 1
                        print("  W 스니펫 사용")
                    continue

                real_url = await get_real_url(page, link)
                if real_url:
                    article["real_url"] = real_url
                    body = fetch_body(real_url)
                    article["body"] = body
                    if body:
                        body_success += 1
                        print(f"  OK {real_url[:65]} ({len(body)}자)")
                    else:
                        body_snippet += 1
                        print("  W 본문없음 스니펫")
                else:
                    body_snippet += 1
                    print("  W 리다이렉트 실패 스니펫")

            print(f"\n본문결과: 성공{body_success}건 / 스니펫{body_snippet}건")
        finally:
            # ★ 수정: try-finally로 예외 발생 시에도 browser 반드시 종료
            if browser:
                await browser.close()

    return targets

# ============================================================
# Gemini 분석
# ============================================================
def analyze(articles, price_data: dict = None, usd_cny: float = 7.25):
    today     = datetime.now().strftime("%Y년 %m월 %d일")
    today_str = datetime.now().strftime("%Y-%m-%d")

    smm_articles     = [a for a in articles if "SMM" in a.get("source", "")][:2]
    general_articles = [a for a in articles if "SMM" not in a.get("source", "")]

    def fmt_article(i, a):
        du   = a.get("real_url") or a["link"]
        line = (f"{i+1}. [{a['lang'].upper()}] {a['title']}\n"
                f"   출처:{a.get('source','불명')} | 날짜:{a.get('pub','')} | {du}")
        body = a.get("body", "") or a.get("snippet", "")
        if body:
            line += f"\n   [본문]: {body[:2000]}"
        return line

    smm_sec = "\n\n".join(fmt_article(i, a) for i, a in enumerate(smm_articles))
    gen_sec = "\n\n".join(fmt_article(i, a) for i, a in enumerate(general_articles))

    if price_data:
        spreads     = compute_spreads(price_data)
        price_str   = format_price_for_prompt(price_data, usd_cny, spreads)
        price_sec   = f"\n[당일 SMM 시세]\n{price_str}\n"
        price_guide = """
[시사점 5개 작성 — 아래 구성 반드시 준수]
① 시세 종합 (1개만, 필수): 탄산리튬·니켈·코발트 스프레드를 하나로 묶어 원료 매입/제품 판매 전략 시사점. 구체적 수치 인용.
② 오늘 기사 기반 (2~3개, 필수): 위 뉴스에서 직접 도출. 공급망/M&A/정책·규제/경쟁사/기술 중 선택. 성일하이텍 관련성 연결.
③ 해외법인 연계 (1개, 필수): 인디애나/폴란드/헝가리/인도/말레이시아/중국 법인 중 오늘 뉴스와 연결.
④ 단기 모멘텀 종합 (1개, 필수, 마지막): 시세+뉴스 종합하여 향후 1~2주 전망 한 문장.

[금지] 시세 관련 내용 2개 이상 금지. 기사/동향 기반 내용 최소 2개 이상 필수.
"""
    else:
        price_sec   = ""
        price_guide = ""

    prompt = f"""당신은 배터리 재활용 산업 전문 시니어 애널리스트입니다. JSON만 출력하세요.
오늘: {today}
{price_sec}
[SMM Metal 기사 최우선 2건]
{smm_sec if smm_sec else "없음"}

[일반 뉴스]
{gen_sec}

[필수 선별 규칙]
- articles는 반드시 8건 이상 12건 이하로 선택. 4건·5건 등 부족한 경우 절대 금지.
- 위 뉴스 목록에서 최대한 많이 선택. 관련도 낮아도 배터리/소재/공급망이면 포함.
- 성일하이텍 기사 반드시 포함.
- 태그: 반드시 아래 5개 중 정확히 하나 선택 → 원재료 및 시황 / 투자 및 M&A / 정책 및 규제 / 공급망 및 파트너십 / 기술 및 공정
- 금지: 증권리포트/주가기사/IR공시/유상증자/ETF/신차리뷰/PR배포/스마트폰기사

[요약기준] 3문장이내. 기관명.기업명.금액.수치.날짜 필수. 추상적요약금지.
계획!=실행, MOU!=계약, 검토!=확정.

[트렌드3개] 한국/중국/미국EU 균형. 오늘기사 수치.정책명 직접인용.
{price_guide}

JSON (articles 최소8건 필수):
{{"articles":[{{"title":"","source":"","date":"","link":"","summary":"3문장이내 수치포함","tag":"원재료 및 시황|투자 및 M&A|정책 및 규제|공급망 및 파트너십|기술 및 공정","region":"한국|중국|미국|EU|일본|인도네시아|글로벌"}}],"trends":[{{"title":"","body":"2~3문장"}}],"insights":[""]}}
articles 최소8건~최대12건. trends 3개. insights 5개. 모든텍스트 한국어."""

    model = genai.GenerativeModel("gemini-2.5-flash")
    cfg   = genai.GenerationConfig(response_mime_type="application/json", temperature=0.2)

    for attempt in range(3):
        try:
            time.sleep(6)
            resp = model.generate_content(prompt, generation_config=cfg)
            try:
                return json.loads(resp.text)
            except json.JSONDecodeError:
                cleaned = re.sub(r"^```json\s*|\s*```$", "", resp.text.strip())
                return json.loads(cleaned)
        except Exception as ex:
            print(f"Gemini 오류({attempt+1}/3): {ex}")
            if attempt < 2:
                w = 30 * (attempt + 1)
                print(f"{w}초 대기...")
                time.sleep(w)

    raise Exception("Gemini 3회 실패")

# ============================================================
# 시세 HTML 블록
# ============================================================
def _fmt(val, prefix="") -> str:
    if val is None:
        return "—"
    return f"{prefix}{val:,.0f}"

def _pct_color(pct: str) -> str:
    if not pct or pct == "N/A":
        return "#888888"
    return "#c0392b" if "+" in pct else "#2471a3"

def _source_badge(source: str) -> str:
    """출처 소형 배지 (SMM / LME)"""
    colors = {"LME": ("#dbeafe", "#1d4ed8"), "SMM": ("#f0fdf4", "#15803d")}
    bg, fg = colors.get(source, ("#f1f5f9", "#64748b"))
    return (
        f'<span style="display:inline-block;background:{bg};color:{fg};'
        f'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
        f'margin-left:4px;vertical-align:middle;">{source}</span>'
    )

def build_price_section(price_data: dict, usd_cny: float) -> str:
    today   = datetime.now().strftime("%Y.%m.%d")
    spreads = compute_spreads(price_data)

    # ── 스프레드 배지 ────────────────────────────────────────────
    spread_badges = ""
    for k, label in [("탄산리튬", "LC"), ("니켈", "Ni")]:
        if k in spreads:
            s   = spreads[k]
            clr = "#c0392b" if s["spread"] > 0 else "#2563eb"
            sep = "&nbsp;&nbsp;" if spread_badges else ""
            spread_badges += (
                f'{sep}<span style="display:inline-block;background:{clr};color:#fff;'
                f'font-size:11px;font-weight:700;padding:3px 8px;border-radius:4px;">'
                f'{label} {s["structure"]} {s["spread_pct"]:+.1f}%</span>'
            )

    # ── 현물 행 ─────────────────────────────────────────────────
    spot_rows = ""
    for r in price_data["spot"]:
        ok      = r.get("status") == "OK"
        name    = r.get("name", "")
        src     = r.get("source", "SMM")
        pct     = r.get("change_pct", "N/A") if ok else "N/A"
        delayed = r.get("delayed", False)

        # 품목 컬럼 배지
        badges = _source_badge(src)
        if name == "황산코발트":
            badges += ('<span style="display:inline-block;background:#e2e8f0;color:#64748b;'
                       'font-size:9px;padding:1px 5px;border-radius:3px;margin-left:3px;'
                       'vertical-align:middle;">참고</span>')
        if delayed:
            badges += ('<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                       'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                       'margin-left:3px;vertical-align:middle;">T-1</span>')

        # 단가 컬럼 (USD primary, CNY secondary)
        if ok:
            usd_str = _fmt(r.get("usd_excl"), "$")
            cny_str = _fmt(r.get("cny_excl"), "CNY")
            price_cell = (
                f'<b style="font-size:13px;">{usd_str}</b>'
                f'<br><span style="color:#aaaaaa;font-size:11px;">{cny_str}</span>'
            )
        else:
            price_cell = '<span style="color:#aaaaaa;">—</span>'

        # 추가정보 컬럼 (코발트만 Co금속환산, 나머지 —)
        if ok and name == "황산코발트" and r.get("usd_metal"):
            extra_cell = (
                f'<b style="font-size:12px;">{_fmt(r.get("usd_metal"), "$")}</b>'
                f'<br><span style="color:#aaaaaa;font-size:10px;">Co 금속환산</span>'
            )
        elif ok and src == "LME":
            extra_cell = '<span style="color:#94a3b8;font-size:11px;">직접 금속가</span>'
        else:
            extra_cell = '<span style="color:#d1d5db;">—</span>'

        name_en = r.get("name_en", "")
        # 탄산리튬 label: TG/BG prefix
        label = name.replace("배터리용 ", "BG ").replace("공업용 ", "TG ")

        spot_rows += f"""
        <tr>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;font-family:'Malgun Gothic',Arial,sans-serif;">
            <b style="font-size:13px;color:#0f2744;">{label}</b>{badges}<br>
            <span style="font-size:11px;color:#8f9ba8;">{name_en}</span>
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:right;font-family:'Malgun Gothic',Arial,sans-serif;">
            {price_cell}
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:right;font-family:'Malgun Gothic',Arial,sans-serif;">
            {extra_cell}
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:center;font-weight:700;font-size:13px;color:{_pct_color(pct)};font-family:'Malgun Gothic',Arial,sans-serif;">
            {pct}
          </td>
        </tr>"""

    # ── 선물 행 ─────────────────────────────────────────────────
    fut_rows = ""
    for r in price_data["futures"]:
        ok      = r.get("status") == "OK"
        src     = r.get("source", "")
        is_lme  = r.get("exchange") == "LME"
        pct     = r.get("change_pct", "N/A") if ok else "N/A"
        delayed = r.get("delayed", False)
        ticker  = r.get("ticker", "")
        label   = r.get("name", "").replace(" 선물", "")

        # 품목 배지
        f_badges = ""
        if delayed:
            f_badges += ('<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                         'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                         'margin-left:4px;vertical-align:middle;">T-1</span>')

        # 단가 컬럼
        if ok:
            if is_lme:
                # LME: USD 직접 표시
                usd = r.get("latest")
                cny = r.get("latest_vat_excl")
                price_f = (
                    f'<b style="font-size:13px;">{_fmt(usd, "$")}</b>'
                    f'<br><span style="color:#aaaaaa;font-size:11px;">{_fmt(cny, "CNY")}</span>'
                )
            else:
                # GFEX: CNY 기준 (VAT제외)
                ve  = r.get("latest_vat_excl")
                ue  = round(ve / usd_cny) if ve else None
                price_f = (
                    f'<b style="font-size:13px;">{_fmt(ue, "$")}</b>'
                    f'<br><span style="color:#aaaaaa;font-size:11px;">{_fmt(ve, "CNY")}</span>'
                )
        else:
            price_f = '<span style="color:#aaaaaa;">—</span>'

        # 기준가 컬럼
        if ok:
            if is_lme:
                ref = '<span style="font-size:11px;color:#94a3b8;">LME Official</span>'
            else:
                raw_cny = r.get("latest")
                ref = (
                    f'<span style="font-size:10px;color:#aaaaaa;">고시가(VAT포함)</span><br>'
                    f'<b style="font-size:12px;color:#555;">{_fmt(raw_cny, "CNY")}</b>'
                ) if raw_cny else '<span style="color:#d1d5db;">—</span>'
        else:
            ref = '<span style="color:#d1d5db;">—</span>'

        fut_rows += f"""
        <tr>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;font-family:'Malgun Gothic',Arial,sans-serif;">
            <b style="font-size:13px;color:#0f2744;">{label}</b>{f_badges}<br>
            <span style="font-size:11px;color:#8f9ba8;">{ticker}</span>
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:right;font-family:'Malgun Gothic',Arial,sans-serif;">
            {price_f}
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:right;font-family:'Malgun Gothic',Arial,sans-serif;">
            {ref}
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:center;font-weight:700;font-size:13px;color:{_pct_color(pct)};font-family:'Malgun Gothic',Arial,sans-serif;">
            {pct}
          </td>
        </tr>"""

    return f"""
  <tr>
    <td bgcolor="#1e293b"
        style="background:#1e293b;color:#ffffff;font-size:13px;font-weight:700;
               letter-spacing:0.5px;padding:12px 30px;font-family:'Malgun Gothic',Arial,sans-serif;">
      SECTION 1 &nbsp;<span style="color:#64748b;">/</span>&nbsp; SMM·LME 배터리 소재 시세
    </td>
  </tr>
  <tr>
    <td bgcolor="#ffffff" style="background:#ffffff;padding:20px 6px 16px;">
      <p style="margin:0 0 4px;font-size:12px;color:#64748b;padding:0 8px;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        {today} · SMM 증치세제외 기준 · LME T-1 전일결산가
      </p>
      <p style="margin:0 0 14px;padding:0 8px;">
        {spread_badges if spread_badges else '&nbsp;'}
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0"
             bgcolor="#ffffff"
             style="font-size:13px;background:#ffffff;border:1px solid #e2e8f0;border-collapse:collapse;">
        <thead>
          <tr bgcolor="#f8fafc" style="background:#f8fafc;">
            <td style="padding:10px 14px;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">
              현물 (Spot) · 품목</td>
            <td style="padding:10px 14px;text-align:right;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">
              USD/t<br><span style="font-weight:400;font-size:10px;color:#94a3b8;">CNY/t 환산</span></td>
            <td style="padding:10px 14px;text-align:right;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">
              추가정보</td>
            <td style="padding:10px 14px;text-align:center;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">
              등락</td>
          </tr>
        </thead>
        <tbody>
          {spot_rows}
          <tr>
            <td colspan="4" bgcolor="#f1f5f9"
                style="padding:8px 14px;background:#f1f5f9;font-size:11px;font-weight:700;
                       color:#64748b;text-align:center;font-family:'Malgun Gothic',Arial,sans-serif;">
              선물 (Futures) &nbsp;|&nbsp; USD/CNY {usd_cny:.2f} &nbsp;|&nbsp; GFEX 증치세제외
            </td>
          </tr>
          {fut_rows}
        </tbody>
      </table>
      <p style="margin:10px 8px 0;color:#94a3b8;font-size:11px;text-align:right;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        출처: Co·Li 현물 <b>SMM</b> · Ni 현물/선물 <b>LME</b> via Westmetall (T-1 전일결산가) · LC 선물 <b>GFEX</b> · 증치세제외 = 포함가÷1.13
      </p>
    </td>
  </tr>"""

# ============================================================
# 이메일 HTML 생성
# ============================================================
def build_email(data, price_data: dict = None, usd_cny: float = 7.25):
    today     = datetime.now().strftime("%Y년 %m월 %d일")
    TAG_ORDER = ["원재료 및 시황", "공급망 및 파트너십", "투자 및 M&A", "정책 및 규제", "기술 및 공정"]

    by_tag = {}
    for a in data.get("articles", []):
        by_tag.setdefault(a.get("tag", "기타"), []).append(a)

    def card(a):
        url     = esc(a.get("real_url") or a.get("link", ""))
        summary = esc(a.get("summary", "")).replace('\n', '<br>')
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="border:1px solid #e2e8f0;border-radius:8px;margin-bottom:16px;
                      border-collapse:collapse;background:#ffffff;">
          <tr>
            <td style="padding:22px;">
              <p style="margin:0 0 10px 0;">
                <span style="display:inline-block;font-size:11px;font-weight:700;padding:4px 10px;
                      background:#dcfce7;color:#15803d;border-radius:4px;
                      font-family:'Malgun Gothic',Arial,sans-serif;">
                  {esc(a.get('region', ''))}</span>
                <span style="font-size:12px;color:#94a3b8;margin-left:8px;
                      font-family:'Malgun Gothic',Arial,sans-serif;">
                  {esc(a.get('source', ''))} · {esc(a.get('date', ''))}</span>
              </p>
              <h4 style="font-size:16px;font-weight:700;color:#0f2744;margin:0 0 10px 0;
                         line-height:1.4;font-family:'Malgun Gothic',Arial,sans-serif;">
                <a href="{url}" style="color:#0f2744;text-decoration:none;">{esc(a.get('title', ''))}</a>
              </h4>
              <p style="font-size:14px;color:#475569;line-height:1.6;margin:0 0 18px 0;
                        font-family:'Malgun Gothic',Arial,sans-serif;">
                {summary}</p>
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center" bgcolor="#ffffff"
                      style="border:1px solid #ea580c;border-radius:4px;">
                    <a href="{url}" style="display:inline-block;padding:8px 16px;font-size:12px;
                          font-weight:700;color:#ea580c;text-decoration:none;
                          font-family:'Malgun Gothic',Arial,sans-serif;">
                      원문 기사 보기 &rarr;</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>"""

    articles_html = ""
    for tag in TAG_ORDER:
        if tag not in by_tag:
            continue
        articles_html += (
            f'<h3 style="font-size:15px;font-weight:700;color:#334155;'
            f'border-left:3px solid #2563eb;padding-left:10px;margin:25px 0 12px;'
            f'font-family:\'Malgun Gothic\',Arial,sans-serif;">{esc(tag)}</h3>'
        )
        for a in by_tag[tag]:
            articles_html += card(a)

    trends_html = ""
    for i, t in enumerate(data.get("trends", [])):
        trends_html += f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="margin-bottom:16px;border-collapse:collapse;
                      border:1px solid #e2e8f0;border-radius:6px;background:#ffffff;">
          <tr>
            <td width="4" bgcolor="#2563eb"
                style="background:#2563eb;font-size:1px;line-height:1px;">&nbsp;</td>
            <td style="padding:18px 20px;">
              <p style="font-size:12px;font-weight:800;color:#2563eb;margin:0 0 6px 0;
                        letter-spacing:0.5px;font-family:'Malgun Gothic',Arial,sans-serif;">
                TREND 0{i+1}</p>
              <h4 style="font-size:15px;font-weight:700;color:#0f2744;margin:0 0 8px 0;
                         font-family:'Malgun Gothic',Arial,sans-serif;">
                {esc(t.get('title', ''))}</h4>
              <p style="font-size:14px;color:#475569;line-height:1.6;margin:0;
                        font-family:'Malgun Gothic',Arial,sans-serif;">
                {esc(t.get('body', ''))}</p>
            </td>
          </tr>
        </table>"""

    insights_html = ""
    insights = data.get("insights", [])
    for i, ins in enumerate(insights):
        bb      = "border-bottom:1px dashed #fde047;" if i < len(insights) - 1 else ""
        pad_top = "padding-top:16px;" if i > 0 else ""
        pad_bot = "padding-bottom:16px;" if i < len(insights) - 1 else ""
        insights_html += f"""
        <tr>
          <td valign="top" style="width:20px;color:#d97706;font-size:16px;
                                  line-height:1.6;{pad_top}
                                  font-family:'Malgun Gothic',Arial,sans-serif;">&#9658;</td>
          <td style="{bb}{pad_top}{pad_bot}font-size:14px;color:#451a03;line-height:1.6;
                    font-family:'Malgun Gothic',Arial,sans-serif;">{esc(ins)}</td>
        </tr>"""

    price_rows = build_price_section(price_data, usd_cny) if price_data else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<!--[if mso]>
<xml><o:OfficeDocumentSettings><o:AllowPNG/>
<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml>
<![endif]-->
<style type="text/css">
  body {{ margin:0; padding:0; background-color:#f8fafc;
          -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table {{ border-collapse:collapse; mso-table-lspace:0pt; mso-table-rspace:0pt; }}
  a {{ text-decoration:none; }}
  @media print {{
    * {{
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
      color-adjust: exact !important;
    }}
  }}
</style>
</head>
<body style="margin:0;padding:20px;background-color:#f8fafc;">

<!--[if mso]><table align="center" width="680" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->

<table align="center" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="max-width:680px;margin:0 auto;background-color:#ffffff;
              border:1px solid #e2e8f0;border-collapse:collapse;">

  <!-- 헤더 -->
  <tr>
    <td bgcolor="#0f2744" style="background-color:#0f2744;padding:40px 30px;">
      <h1 style="color:#ffffff;font-size:24px;font-weight:700;margin:0 0 10px 0;
                 letter-spacing:0.5px;font-family:'Malgun Gothic',Arial,sans-serif;">
        BATTERY RECYCLING DAILY BRIEF</h1>
      <p style="color:#94a3b8;font-size:14px;margin:0;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        {today} &nbsp;|&nbsp; Battery Intelligence Report</p>
    </td>
  </tr>

  {price_rows}

  <!-- SECTION 2 -->
  <tr>
    <td bgcolor="#1e293b"
        style="background:#1e293b;color:#ffffff;font-size:13px;font-weight:700;
               letter-spacing:0.5px;padding:12px 30px;font-family:'Malgun Gothic',Arial,sans-serif;">
      SECTION 2 &nbsp;<span style="color:#64748b;">/</span>&nbsp; 분야별 핵심 기사
    </td>
  </tr>
  <tr>
    <td bgcolor="#ffffff" style="background:#ffffff;padding:10px 30px 30px;">
      {articles_html}
    </td>
  </tr>

  <!-- SECTION 3 -->
  <tr>
    <td bgcolor="#1e293b"
        style="background:#1e293b;color:#ffffff;font-size:13px;font-weight:700;
               letter-spacing:0.5px;padding:12px 30px;font-family:'Malgun Gothic',Arial,sans-serif;">
      SECTION 3 &nbsp;<span style="color:#64748b;">/</span>&nbsp; 오늘의 산업 흐름
    </td>
  </tr>
  <tr>
    <td bgcolor="#f8fafc" style="background:#f8fafc;padding:25px 30px 30px;">
      {trends_html}
    </td>
  </tr>

  <!-- SECTION 4 -->
  <tr>
    <td bgcolor="#1e293b"
        style="background:#1e293b;color:#ffffff;font-size:13px;font-weight:700;
               letter-spacing:0.5px;padding:12px 30px;font-family:'Malgun Gothic',Arial,sans-serif;">
      SECTION 4 &nbsp;<span style="color:#64748b;">/</span>&nbsp; 재활용 사업자 관점 시사점
    </td>
  </tr>
  <tr>
    <td bgcolor="#ffffff" style="background:#ffffff;padding:30px;">
      <table width="100%" cellpadding="24" cellspacing="0" border="0"
             bgcolor="#fefce8"
             style="background-color:#fefce8;border:1px solid #fde047;
                    border-radius:8px;border-collapse:collapse;">
        <tr>
          <td>
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="border-collapse:collapse;">
              {insights_html}
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- 푸터 -->
  <tr>
    <td bgcolor="#0f2744"
        style="background-color:#0f2744;padding:30px;text-align:center;">
      <p style="color:#94a3b8;font-size:13px;margin:0 0 10px 0;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        Battery Recycling Daily Brief &nbsp;|&nbsp; {today}</p>
      <p style="color:#64748b;font-size:12px;margin:0;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        &copy; Ben Seo, Sales &amp; Marketing Division / SungEel HiTech</p>
    </td>
  </tr>

</table>

<!--[if mso]></td></tr></table><![endif]-->

</body>
</html>"""

# ============================================================
# Gmail 발송
# ============================================================
def send_email(html_body):
    today = datetime.now().strftime("%Y년 %m월 %d일")
    msg   = MIMEMultipart("alternative")
    msg["Subject"] = f"[배터리 산업 Daily Brief] {today}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        bcc  = [a.strip() for a in BCC_EMAIL.split(',') if a.strip()] if BCC_EMAIL else []
        smtp.sendmail(GMAIL_USER, [TO_EMAIL] + bcc, msg.as_string())
    print(f"발송 완료 -> {TO_EMAIL} (BCC {len(bcc)}명)")

# ============================================================
# 메인
# ============================================================
async def main():
    print("=== BRDB 시작 ===")

    usd_cny    = get_usd_cny_rate()
    price_data = None
    try:
        price_data = await scrape_smm_prices(usd_cny)
    except Exception as e:
        print(f"W SMM 수집 실패({e}) - 시세없이 계속")

    articles = collect_rss()
    if not articles:
        print("기사없음 - 종료")
        return

    articles = await enrich_articles(articles)
    data     = analyze(articles, price_data=price_data, usd_cny=usd_cny)
    html     = build_email(data, price_data=price_data, usd_cny=usd_cny)
    send_email(html)
    print("=== 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
