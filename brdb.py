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
    {
        "name":          "황산코발트",
        "name_en":       "Cobalt Sulphate",
        "url":           "https://www-old.metal.com/Chemical-Compound/201102250381",
        "metal_content": 0.205,
        "metal_label":   "Co",
    },
    {
        "name":          "배터리용 황산니켈",
        "name_en":       "Battery-Grade Nickel Sulphate",
        "url":           "https://www-old.metal.com/Nickel/201908270001",
        "metal_content": 0.22,
        "metal_label":   "Ni",
    },
    {
        "name":    "공업용 탄산리튬",
        "name_en": "Industrial-Grade Li₂CO₃",
        "url":     "https://www-old.metal.com/lithium/201905160001",
    },
    {
        "name":    "배터리용 탄산리튬",
        "name_en": "Battery-Grade Li₂CO₃",
        "url":     "https://www-old.metal.com/Lithium/201102250059",
    },
]

FUTURES_TARGETS = [
    {
        "name":   "탄산리튬 선물",
        "ticker": "GFEX·LC2609",
        "url":    "https://www-old.metal.com/Lithium/lc2609",
    },
    {
        "name":   "니켈 금속 선물",
        "ticker": "SHFE·NI2606",
        "url":    "https://www-old.metal.com/Nickel/ni2606",
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
    "battery etf", "lithium etf",
    "stocks:",
    "is it too late",
    "stock surges", "stock falls", "stock rises", "stock drops",
    "shares surge", "shares fall",
    "주가 상승", "주가 하락", "주가 급등", "주가 급락",
    "목표가 상향", "목표가 하향",
    "목표 주가",
    "투자의견", "유증", "유상증자",
    "주가 전망", "주가 목표",
    "증권 리포트", "analyst rating", "price target",
    "buy rating", "sell rating",
    "52주 신고가", "52주 신저가",
    "상한가", "하한가",
    "거래량 상위",
    "[ir]", "ir공시", "ir]",
    "뱅크 리포트",
    "리포트 브리핑",
    "투자분석",
    "브랜드 평판",
    "전환사채",
    "share price",
    "fundamentals",
    "dividend",
    "dividen",
    "ferrochrome",
    "shadow fleet",
    "flagship sedan", "driving range", "test drive",
    "0-100km", "top speed", "horsepower",
    "eurekaalert", "전자폐기물",
    "cassava", "agriculture", "crop",
    "petro", "petroleum", "oil refin",
    "dow jones", "s&p 500", "nasdaq",
    "blue whale season", "whale watching", "whale migration",
]

NOISE_SOURCES = [
    "openpr", "prnewswire", "businesswire", "globenewswire", "einpresswire",
    "accesswire", "prnews", "prlog", "marketwired", "newswire", "pr.com", "prweb",
    "discoveryalert", "bravenewcoin", "eurekaalert", "cryptoslate", "coindesk",
    "benzinga", "seekingalpha", "motleyfool", "investopedia", "indexbox",
    "msn", "msn.com",
    "aol.com",
    "simplywall.st",
    "futunn.com",
    "judal.co.kr",
    "investingnews.com",
    "thebull.com.au",
    "marketsmojo.com",
    "switzer.com.au",
    "nai500.com",
    "kalkinemedia.com",
]

NOISE_URL_PATHS = [
    "/stock/",
    "/en/stock/",
    "/stocks/",
    "/share-price/",
    "/equity/",
]

NOISE_PAIRS = [
    ("plastic", "recycl"),
    ("alumin", "recycl"),
    ("bauxite", "recycl"),
    ("fiber", "recycl"),
    ("packaging", "recycl"),
    ("paper", "recycl"),
    ("recycled film", "feedstock"),
    ("scrap", "alumin"),
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
    r'|\[IR\]|\[ir\]'
    r'|IR공시|IR\s*행사'
    , re.IGNORECASE
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
    r'|\d+\.?\d*%\s*(return|gain|rise)\s'
    , re.IGNORECASE
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
    "sungeel", "성일",
    "ascend", "redwood", "cirba", "ecobat", "umicore", "glencore",
    "retriev", "battery resources", "interco", "princeton nuenergy",
    "is eco solution", "fortum", "stena",
    "samsung",
    "sk온", "sk on",
    "lg에너지솔루션", "lg energy solution",
    "삼성sdi",
    "catl", "byd", "panasonic", "northvolt",
    "에코프로비엠", "에코프로", "포스코퓨처엠", "엘앤에프",
    "성일하이텍",
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
            "https://api.frankfurter.app/latest?from=USD&to=CNY",
            timeout=10
        )
        rate = resp.json()["rates"]["CNY"]
        print(f"  환율: 1 USD = {rate:.4f} CNY")
        return rate
    except Exception as e:
        print(f"  ⚠ 환율 조회 실패 ({e}), 기본값 7.25 적용")
        return 7.25


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

        # ★ FIX: findall로 전체 수집 후 0% 제외한 첫 번째 값 선택
        # SMM은 VAT제외 USD 등락에 (0%)를 표시하는 경우가 있음
        # 실제 가격 변동률은 CNY 기준 퍼센트가 의미 있음
        all_pcts = re.findall(r"[+\-][\d,]+\.?\d*\s*\(([+\-]?\d+\.?\d*%)\)", text)
        change_pct = next((p for p in all_pcts if p != "0%"), "N/A")

        date_m = re.search(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})", text)

        usd_excl = float(usd_list[0].replace(",", "")) if usd_list else None
        cny_incl = float(cny_list[0].replace(",", "")) if cny_list else None
        cny_excl = round(cny_incl / VAT_RATE) if cny_incl else None

        mc        = target.get("metal_content")
        ml        = target.get("metal_label")
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


async def _scrape_futures(page, target: dict) -> dict:
    base = {"name": target["name"], "ticker": target["ticker"]}
    try:
        # ★ FIX: domcontentloaded → commit
        # NI2606 등 일부 선물 페이지는 domcontentloaded가 JS 요청 완료까지 대기해
        # 수 분간 hang 걸리는 현상 발생. commit은 첫 바이트 수신 즉시 반환.
        # 가격 데이터는 SSR로 제공되므로 commit + 2s wait으로 충분함.
        await page.goto(target["url"], wait_until="commit", timeout=15000)
        await page.wait_for_timeout(2000)
        text = await page.inner_text("body")

        latest_m = re.search(r"Latest:\s*([\d,]+)", text)

        # ★ FIX: 동일하게 0% 제외
        all_pcts_f = re.findall(r"[+\-][\d,]+\.?\d*\s*\(([+\-]?\d+\.?\d*%)\)", text)
        change_pct = next((p for p in all_pcts_f if p != "0%"), "N/A")

        prev_m = re.search(r"Prev\.Close\s*([\d,]+)", text)
        vol_m  = re.search(r"Volume\s*([\d,]+)", text)
        date_m = re.search(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})", text)

        return {
            **base,
            "date":       date_m.group(1) if date_m else "N/A",
            "latest":     int(latest_m.group(1).replace(",", "")) if latest_m else None,
            "change_pct": change_pct,
            "prev_close": int(prev_m.group(1).replace(",", "")) if prev_m else None,
            "volume":     vol_m.group(1) if vol_m else "N/A",
            "status":     "OK",
        }
    except Exception as e:
        return {**base, "status": f"ERROR: {e}"}


async def scrape_smm_prices() -> dict:
    spot_results, futures_results = [], []
    print("\n[SMM 시세 수집]")
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

        for t in SPOT_TARGETS:
            print(f"  현물: {t['name']} ...", end=" ", flush=True)
            r = await _scrape_spot(page, t)
            spot_results.append(r)
            print("OK" if r["status"] == "OK" else f"⚠ {r['status']}")
            await asyncio.sleep(2)

        for t in FUTURES_TARGETS:
            print(f"  선물: {t['ticker']} ...", end=" ", flush=True)
            r = await _scrape_futures(page, t)
            futures_results.append(r)
            print("OK" if r["status"] == "OK" else f"⚠ {r['status']}")
            await asyncio.sleep(2)

        await browser.close()

    return {"spot": spot_results, "futures": futures_results}


def compute_spreads(price_data: dict) -> dict:
    spot_map    = {r["name"]: r for r in price_data["spot"]    if r["status"] == "OK"}
    futures_map = {r["ticker"]: r for r in price_data["futures"] if r["status"] == "OK"}
    spreads = {}

    lc_s = spot_map.get("공업용 탄산리튬", {}).get("cny_excl")
    lc_f = futures_map.get("GFEX·LC2609", {}).get("latest")
    if lc_s and lc_f:
        diff = lc_s - lc_f
        spreads["탄산리튬"] = {
            "spot": lc_s, "futures": lc_f,
            "spread": diff, "spread_pct": diff / lc_f * 100,
            "structure": "백워데이션(현물>선물)" if diff > 0 else "콘탱고(선물>현물)",
        }

    ni_s = spot_map.get("배터리용 황산니켈", {}).get("cny_metal")
    ni_f = futures_map.get("SHFE·NI2606", {}).get("latest")
    if ni_s and ni_f:
        diff = ni_s - ni_f
        spreads["니켈"] = {
            "spot_metal": ni_s, "futures": ni_f,
            "spread": diff, "spread_pct": diff / ni_f * 100,
        }

    return spreads


def format_price_for_prompt(price_data: dict, usd_cny: float, spreads: dict) -> str:
    lines = [f"수집 시각: {datetime.now().strftime('%H:%M')} KST | USD/CNY: {usd_cny:.2f}"]

    lines.append("\n[현물 Spot]")
    for r in price_data["spot"]:
        if r["status"] != "OK":
            continue
        metal_str = ""
        if r.get("usd_metal"):
            metal_str = f" | {r['metal_label']}금속환산: ${r['usd_metal']:,.0f}(USD) / ¥{r['cny_metal']:,.0f}(CNY)"
        lines.append(
            f"  {r['name']}: ${r['usd_excl']:,.0f}/t (황산염, 증치세제외)"
            f"{metal_str}"
            f" | CNY ¥{r['cny_excl']:,.0f}(증치세제외) / ¥{r['cny_incl']:,.0f}(포함)"
            f" | 등락 {r['change_pct']}"
        )

    lines.append("\n[선물 Futures — CNY/t]")
    for r in price_data["futures"]:
        if r["status"] != "OK":
            continue
        lines.append(
            f"  {r['name']} ({r['ticker']}): ¥{r['latest']:,.0f} ({r['change_pct']})"
            f" | 전일종가 ¥{r.get('prev_close', 0):,.0f} | 거래량 {r.get('volume','N/A')}"
        )

    lines.append("\n[현선물 스프레드]")
    if "탄산리튬" in spreads:
        s = spreads["탄산리튬"]
        lines.append(
            f"  탄산리튬: 현물 ¥{s['spot']:,.0f} vs LC2609 ¥{s['futures']:,.0f}"
            f" → {s['structure']} (차이 {s['spread']:+,.0f} CNY, {s['spread_pct']:+.1f}%)"
        )
    if "니켈" in spreads:
        s = spreads["니켈"]
        sign = "프리미엄" if s["spread"] > 0 else "디스카운트"
        lines.append(
            f"  니켈: 황산니켈 Ni환산 ¥{s['spot_metal']:,.0f} vs NI2606 ¥{s['futures']:,.0f}"
            f" → 황산니켈이 SHFE 대비 {sign} {abs(s['spread_pct']):.1f}%"
            f" (차이 {s['spread']:+,.0f} CNY/t)"
        )
    if not spreads:
        lines.append("  (스프레드 계산 불가 — 데이터 수집 실패)")

    return "\n".join(lines)

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
        is_priority = item.get("priority", False)

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

                if any(s in lower_source or s in lower_link for s in NOISE_SOURCES):
                    continue
                if any(p in lower_link for p in NOISE_URL_PATHS):
                    continue
                if any(k in lower_title for k in NOISE_KEYWORDS):
                    continue
                if any(a in lower_title and b in lower_title for a, b in NOISE_PAIRS):
                    continue
                if is_stock_noise(title):
                    continue
                if source != "SMM Metal":
                    if not any(w in lower_title for w in WHITELIST):
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
        title_lower = a["title"].lower()
        pub_day = a["pub_date"].strftime("%Y-%m-%d") if a.get("pub_date") else "unknown"

        words = {w for w in re.sub(r'[^\w\s]', ' ', a["title"]).split() if len(w) >= 2}
        is_dup = any(
            len(words & {w for w in re.sub(r'[^\w\s]', ' ', b["title"]).split() if len(w) >= 2}) >= 3
            for b in deduped
        )
        if is_dup:
            continue

        for company in ["lg에너지솔루션", "sk온", "삼성sdi", "에코프로비엠", "catl", "byd"]:
            if company in title_lower:
                key = f"{company}_{pub_day}"
                company_day_count[key] = company_day_count.get(key, 0) + 1
                if company_day_count[key] > 3:
                    is_dup = True
                break

        if not is_dup:
            deduped.append(a)

    smm_count = sum(1 for a in deduped if "SMM" in a.get("source", ""))
    priority_count = sum(1 for a in deduped if a.get("priority"))
    print(f"수집: {len(raw)}건 → 중복 제거 후: {len(deduped)}건 (SMM: {smm_count}건, 시황매체: {priority_count}건)")
    return deduped

# ============================================================
# Jina 본문 추출
# ============================================================
def fetch_body(real_url):
    try:
        # ★ FIX: timeout을 (connect, read) 튜플로 분리
        # connect는 10초, read는 45초 — 한국어 뉴스 사이트 응답 지연 대응
        # 로직 자체는 변경 없음
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

# ============================================================
# Playwright URL 추출
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
    "电池", "回收", "锂", "镍", "钴",
    "akkumulátor",
]

def is_battery_relevant(title: str) -> bool:
    lower = title.lower()
    return any(k in lower for k in _BATTERY_RELEVANCE_KW)

async def enrich_articles(articles):
    smm = [a for a in articles if "SMM" in a.get("source", "")][:2]

    sungeel_kw = ["성일하이텍", "sungeel", "성일"]
    sungeel = [a for a in articles
               if "SMM" not in a.get("source", "")
               and any(k in a["title"].lower() for k in sungeel_kw)]

    priority = [a for a in articles
                if a.get("priority") and "SMM" not in a.get("source", "")
                and a not in sungeel
                and is_battery_relevant(a["title"])][:3]

    general_pool = [a for a in articles
                    if "SMM" not in a.get("source", "")
                    and a not in sungeel and a not in priority]
    recycling_boost = [a for a in general_pool
                       if any(k in a["title"].lower()
                              for k in ["battery recycl", "ev recycl", "black mass", "블랙매스",
                                        "배터리 재활용", "폐배터리", "사용후배터리",
                                        "hydromet", "hpal", "이차전지 재활용"])]
    others = [a for a in general_pool if a not in recycling_boost]
    general_pool_sorted = recycling_boost + others

    general_limit = max(0, 15 - len(sungeel) - len(priority))
    general = general_pool_sorted[:general_limit]

    targets = smm + sungeel + priority + general

    print(f"\n본문 추출 대상: SMM {len(smm)}건 + 성일 {len(sungeel)}건 + 시황매체 {len(priority)}건 + 일반 {len(general)}건 = {len(targets)}건")

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
                article["real_url"] = real_url
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
def analyze(articles, price_data: dict = None, usd_cny: float = 7.25):
    today     = datetime.now().strftime("%Y년 %m월 %d일")
    today_str = datetime.now().strftime("%Y-%m-%d")

    smm_articles     = [a for a in articles if "SMM" in a.get("source", "")][:2]
    general_articles = [a for a in articles if "SMM" not in a.get("source", "")]

    def format_article(i, a):
        display_url = a.get("real_url") or a["link"]
        line = (f"{i+1}. [{a['lang'].upper()}] {a['title']}\n"
                f"   출처: {a.get('source','불명')} | 날짜: {a.get('pub','')} | 링크: {display_url}")
        body = a.get("body", "") or a.get("snippet", "")
        if body:
            line += f"\n   [본문]: {body[:2000]}"
        return line

    smm_section     = "\n\n".join(format_article(i, a) for i, a in enumerate(smm_articles))
    general_section = "\n\n".join(format_article(i, a) for i, a in enumerate(general_articles))

    if price_data:
        spreads   = compute_spreads(price_data)
        price_str = format_price_for_prompt(price_data, usd_cny, spreads)
        price_section = f"""
━━━ [당일 SMM 시세 — 분석에 반드시 활용] ━━━
{price_str}
"""
        price_insight_guide = """
[시세-뉴스 통합 분석 — insights에 반드시 포함]
- 탄산리튬 현선물 스프레드 해석: 백워데이션/콘탱고 여부와 시사점 (수급 타이트/완화, 투기 포지션 방향)
- 황산니켈 현물 Ni환산가 vs SHFE NI2606 선물 비교: 프리미엄/디스카운트 해석
- 황산코발트·황산니켈 Co/Ni 금속환산가 동향과 오늘 관련 뉴스 간 연관성
- 성일하이텍의 원료 구매 타이밍 또는 제품 판매 전략에 대한 시사점 (시세 데이터 수치 직접 인용)
- 시세와 뉴스를 연결한 단기 모멘텀 판단 (한 문장으로)
"""
    else:
        price_section       = ""
        price_insight_guide = ""

    prompt = f"""당신은 리튬이온 배터리 재활용 산업 전문 시니어 애널리스트입니다. 아래 시세와 뉴스를 분석하여 JSON만 출력하세요.
오늘 날짜: {today}

{price_section}
━━━ [SMM Metal 시황 기사 — 최우선 포함, 최대 2건] ━━━
{smm_section if smm_section else "오늘 SMM 기사 없음"}

━━━ [일반 뉴스] ━━━
{general_section}

[선별 기준]
- 오늘({today_str}) 기사 최우선. 어제 기사는 오늘 기사 부족 시만 포함
- 동일 기업이라도 주제(실적/투자/정책/기술/시황/M&A)가 다르면 별도 기사로 포함 가능
- 동일 기업·동일 주제인 경우에만 가장 최신 1건으로 제한, 중복 절대 금지
- 성일하이텍 관련 기사는 반드시 포함
- 배터리 재활용, 블랙매스, 원재료(Li/Ni/Co), 공급망, 정책·규제, 투자·M&A 우선
- 아래 유형은 절대 포함 금지:
  · 증권사 목표주가·투자의견·리포트
  · 단순 주가 등락·거래량 기사
  · IR 공시·IR 행사·컨퍼런스콜 전문 기사
  · 유상증자·전환사채 기사
  · ETF 관련 기사
  · 자동차 신차 스펙·리뷰 기사
  · PR 배포·학술 보도자료

[요약 작성 기준]
- 3문장 이내 자유 서술형
- 본문에 등장하는 기관명·기업명·금액·수치·날짜는 빠짐없이 반영
- 수치 없이 "~할 것으로 전망된다" 같은 추상적 요약 절대 금지
- 기업명은 정식 전체 명칭 사용
- 계획 발표 ≠ 실제 시작, MOU ≠ 계약, 검토 ≠ 확정 — 반드시 구분

[트렌드 3개 기준]
- 한국/중국/미국·EU 지역별 균형
- 오늘 기사의 특정 기업명·수치·정책명 직접 인용
- 이 뉴스 없이는 쓸 수 없는 구체적 내용

[시사점 4~5개 기준]
- 성일하이텍(국내 최대 배터리 재활용, 블랙매스→황산니켈·황산코발트·탄산리튬 판매) 관점
- 해외 법인(미국 인디애나, 폴란드, 헝가리, 인도, 말레이시아, 중국) 연계 검토
{price_insight_guide}

[출력: JSON만]
{{
  "articles": [{{
    "title": "원문 제목",
    "source": "출처",
    "date": "날짜",
    "link": "URL",
    "summary": "본문 수치·기관명·기업명 필수 반영, 3문장 이내 자유 서술.",
    "tag": "원재료 및 시황|투자 및 M&A|정책 및 규제|공급망 및 파트너십|기술 및 공정 중 하나",
    "region": "한국|중국|미국|EU|일본|인도네시아|글로벌"
  }}],
  "trends": [{{"title": "트렌드 제목", "body": "구체적 내용 2~3문장"}}],
  "insights": ["시사점"]
}}

articles: SMM 최대 2건 + 일반 기사 합산 총 8~12건.
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
            # ★ FIX: JSON 파싱 실패 시 마크다운 펜스 제거 후 재시도
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                cleaned = re.sub(r"^```json\s*|\s*```$", "", response.text.strip())
                return json.loads(cleaned)

        except Exception as ex:
            print(f"Gemini 오류 (시도 {attempt+1}/3): {ex}")
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f"{wait}초 대기 후 재시도...")
                time.sleep(wait)

    raise Exception("Gemini 분석 3회 모두 실패")

# ============================================================
# 시세 HTML 블록
# ============================================================
def _fmt(val, prefix="") -> str:
    if val is None:
        return "—"
    return f"{prefix}{val:,.0f}"

def _pct_color(pct: str) -> str:
    if not pct or pct == "N/A":
        return "#888"
    return "#c0392b" if "+" in pct else "#2471a3"

def build_price_section(price_data: dict, usd_cny: float) -> str:
    today   = datetime.now().strftime("%Y.%m.%d")
    spreads = compute_spreads(price_data)

    spot_rows = ""
    for r in price_data["spot"]:
        ok  = r["status"] == "OK"
        pct = r.get("change_pct", "N/A")
        ml  = r.get("metal_label")
        metal_cell = (
            f"<b>{_fmt(r.get('usd_metal'), '$')}</b>"
            f"<br><span style='color:#aaa;font-size:10px;'>{_fmt(r.get('cny_metal'), '¥')} CNY</span>"
            if (ok and ml) else "—"
        )
        spot_rows += f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;white-space:nowrap;">
            <b style="font-size:12px;color:#0f2744;">{r['name']}</b><br>
            <span style="font-size:10px;color:#bbb;">{r['name_en']}</span>
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;text-align:right;font-size:12px;color:#333;">
            {_fmt(r.get('usd_excl'), '$') if ok else '—'}<br>
            <span style="color:#aaa;font-size:10px;">{_fmt(r.get('cny_excl'), '¥')} CNY</span>
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;text-align:right;font-size:12px;font-weight:700;color:#0f2744;">
            {metal_cell}
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;text-align:right;font-size:11px;color:#888;">
            {_fmt(r.get('cny_incl'), '¥') if ok else '—'}
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;text-align:center;font-weight:700;font-size:12px;color:{_pct_color(pct)};">
            {pct}
          </td>
        </tr>"""

    fut_rows = ""
    for r in price_data["futures"]:
        ok  = r["status"] == "OK"
        pct = r.get("change_pct", "N/A")
        fut_rows += f"""
        <tr>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;white-space:nowrap;">
            <b style="font-size:12px;color:#0f2744;">{r['name']}</b><br>
            <span style="font-size:10px;color:#bbb;">{r['ticker']}</span>
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;text-align:right;font-size:12px;font-weight:700;color:#0f2744;" colspan="2">
            {_fmt(r.get('latest'), '¥') if ok else '—'}
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;text-align:right;font-size:11px;color:#888;">
            {_fmt(r.get('prev_close'), '¥') if ok else '—'}
          </td>
          <td style="padding:8px 10px;border-bottom:1px solid #e8edf2;text-align:center;font-weight:700;font-size:12px;color:{_pct_color(pct)};">
            {pct}
          </td>
        </tr>"""

    # ★ FIX: display:flex → inline-block (Gmail flex 미지원)
    spread_badges = ""
    if "탄산리튬" in spreads:
        s   = spreads["탄산리튬"]
        clr = "#c0392b" if s["spread"] > 0 else "#2471a3"
        spread_badges += (
            f'<span style="display:inline-block;background:{clr};color:#fff;'
            f'font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;margin-right:6px;">'
            f'LC2609 {s["structure"]} {s["spread_pct"]:+.1f}%</span>'
        )
    if "니켈" in spreads:
        s   = spreads["니켈"]
        lbl = "프리미엄" if s["spread"] > 0 else "디스카운트"
        clr = "#c0392b" if s["spread"] > 0 else "#2471a3"
        spread_badges += (
            f'<span style="display:inline-block;background:{clr};color:#fff;'
            f'font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;">'
            f'NI2606 Ni환산 {lbl} {abs(s["spread_pct"]):.1f}%</span>'
        )

    return f"""
  <div style="background:#1a3a5c;color:#fff;font-size:11px;font-weight:700;
              letter-spacing:1px;padding:7px 28px;">
    SECTION 0 &nbsp;/&nbsp; SMM 배터리 소재 시세
  </div>
  <div style="padding:14px 28px 10px;background:#f5f6f8;">
    <div style="margin-bottom:8px;">
      <span style="font-size:11px;color:#888;">{today} · USD/CNY {usd_cny:.2f} · 증치세 제외 기준</span>
      &nbsp;&nbsp;{spread_badges}
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff;
                  border:1px solid #e0e4ea;border-radius:6px;overflow:hidden;">
      <thead>
        <tr style="background:#0f2744;color:#fff;">
          <th style="padding:7px 10px;text-align:left;font-size:11px;">품목</th>
          <th style="padding:7px 10px;text-align:right;font-size:11px;">
            황산염 USD/t<br><span style="font-weight:400;">(CNY 증치세제외)</span></th>
          <th style="padding:7px 10px;text-align:right;font-size:11px;">
            금속환산 USD/t<br><span style="font-weight:400;">(Co 20.5% / Ni 22%)</span></th>
          <th style="padding:7px 10px;text-align:right;font-size:11px;">
            CNY/t<br><span style="font-weight:400;">(증치세 포함)</span></th>
          <th style="padding:7px 10px;text-align:center;font-size:11px;">등락</th>
        </tr>
      </thead>
      <tbody>
        {spot_rows}
        <tr><td colspan="5" style="padding:4px 10px;background:#f0f4f8;
                font-size:10px;font-weight:700;color:#666;letter-spacing:.5px;">
          선물 (Futures, CNY/t) — 전일종가 기준
        </td></tr>
        {fut_rows}
      </tbody>
    </table>
    <p style="margin:5px 0 0;color:#ccc;font-size:10px;">
      출처: SMM (Shanghai Metals Market) · 증치세 제외 = 포함가 ÷ 1.13 ·
      ※ SHFE NI2606은 니켈 금속 선물 (황산니켈 원가 참고지표)
    </p>
  </div>
"""

# ============================================================
# 이메일 HTML 생성
# ============================================================
def build_email(data, price_data: dict = None, usd_cny: float = 7.25):
    today    = datetime.now().strftime("%Y년 %m월 %d일")
    TAG_ORDER = ["원재료 및 시황", "공급망 및 파트너십", "투자 및 M&A", "정책 및 규제", "기술 및 공정"]

    by_tag = {}
    for a in data.get("articles", []):
        tag = a.get("tag", "기타")
        by_tag.setdefault(tag, []).append(a)

    def card(a):
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

    price_html = build_price_section(price_data, usd_cny) if price_data else ""

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:16px;background:#eef0f3;">
<div style="max-width:660px;margin:0 auto;background:#fff;font-family:'Malgun Gothic','맑은 고딕',Arial,sans-serif;">
  <div style="background:#0f2744;padding:22px 28px;">
    <p style="color:#fff;font-size:18px;font-weight:700;margin:0 0 4px;">BATTERY RECYCLING DAILY BRIEF</p>
    <p style="color:#90b4d8;font-size:12px;margin:0;">{today}&nbsp;&nbsp;|&nbsp;&nbsp;Battery Intelligence Report</p>
  </div>
  {price_html}
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
        bcc_list   = [addr.strip() for addr in BCC_EMAIL.split(',') if addr.strip()] if BCC_EMAIL else []
        recipients = [TO_EMAIL] + bcc_list
        smtp.sendmail(GMAIL_USER, recipients, msg.as_string())
    print(f"발송 완료 → {TO_EMAIL} (BCC {len(bcc_list)}명)")

# ============================================================
# 메인
# ============================================================
async def main():
    print("=== BRDB 시작 ===")

    usd_cny = get_usd_cny_rate()

    price_data = None
    try:
        price_data = await scrape_smm_prices()
    except Exception as e:
        print(f"⚠ SMM 시세 수집 실패 ({e}) — 시세 없이 계속")

    articles = collect_rss()
    if not articles:
        print("기사 없음 - 종료")
        return

    articles = await enrich_articles(articles)
    data     = analyze(articles, price_data=price_data, usd_cny=usd_cny)
    html     = build_email(data, price_data=price_data, usd_cny=usd_cny)
    send_email(html)
    print("=== 완료 ===")

if __name__ == "__main__":
    asyncio.run(main())
