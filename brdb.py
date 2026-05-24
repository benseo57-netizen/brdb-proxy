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

FUTURES_EM = [
    {
        "name":      "탄산리튬 선물",
        "exchange":  "GFEX",
        "url":       "https://www.metal.com/gfex",
        "ticker":    "LCM",
        "method":    "playwright",
    },
    {
        "name":      "니켈 선물",
        "exchange":  "LME",
        "ticker":    "LME·3M",
        "method":    "metalradar",
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
    # 인도네시아어: 니켈 제련·시황 전용 (tambang 단독 쿼리 제거)
    {"q": '("nikel" OR "HPAL" OR "RKEF") ("smelter" OR "hilirisasi nikel" OR "ferronickel" OR "nickel matte" OR "pemurnian")',
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
    # 헝가리어: akkumulátor 단독 제거(소비자 가전 오염), 복합어+법인 위치명으로 교체
    {"q": '"SungEel" OR "Batonyterenye" OR "akkumulátor-újrahasznosítás" OR "akkumulátor visszagyűjtés" OR "akkuhulladék"',
     "lang": "hu", "gl": "HU", "ceid": "HU:hu"},
    {"q": '"news.metal.com" (nickel OR cobalt OR lithium OR "black mass" OR recycling)',
     "lang": "en", "gl": "US", "ceid": "US:en"},
]

# ============================================================
# 노이즈 필터
# ============================================================
NOISE_KEYWORDS = [
    "crypto", "bitcoin", "ethereum", "nft", "dogecoin",
    "게임", "영화", "드라마", "리뷰", "car review", "smartphone review",
    "xiaomi", "samsung galaxy", "iphone", "smartwatch", "okosóra",
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
    # ★ 추가: 스마트폰/태블릿/자동차 시승 노이즈
    "oppo", "vivo", "realme", "honor phone",
    "táblagép", "diákoknak", "tablet pc",
    "试驾", "续航里程达成率", "驾驶体验",
]

NOISE_SOURCES = [
    "openpr", "prnewswire", "businesswire", "globenewswire", "einpresswire",
    "accesswire", "prnews", "prlog", "marketwired", "newswire", "pr.com", "prweb",
    "discoveryalert", "bravenewcoin", "eurekaalert", "cryptoslate", "coindesk",
    "benzinga", "seekingalpha", "motleyfool", "investopedia", "indexbox",
    "msn", "msn.com", "aol.com", "simplywall.st", "futunn.com", "judal.co.kr",
    "investingnews.com", "thebull.com.au", "marketsmojo.com",
    "switzer.com.au", "nai500.com", "kalkinemedia.com",
    # ★ 추가: 투자분석·일반매체 오염 소스
    "chartmill", "vozpopuli", "mixvale", "vietnam.vn",
    "ad-hoc-news", "stocktitan",
    "bitget", "belfasttelegraph", "technetbooks", "saudigazette", "techjuice",
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
    # 인도네시아어: 니켈 제련 특화
    "nikel", "rkef", "hpal", "ferronickel", "hilirisasi",
    "akkumulátor", "akkuhulladék",
    "电池", "回收", "锂", "镍", "钴", "宁德时代", "比亚迪",
    "リサイクル", "電池", "リチウム", "ニッケル", "コバルト",
]

# 인도네시아어 기사 strict 필터 (WHITELIST "nikel" 단독 통과 방지)
_ID_NICKEL_STRICT = [
    "nikel", "rkef", "hpal", "ferronickel", "nickel matte",
    "hilirisasi nikel", "pemurnian nikel", "smelter nikel",
    "nickel pig iron", "npi", "matte nikel",
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

def get_cutoff_utc() -> datetime:
    """KST 기준 '어제 00:00' → UTC 변환.
    오늘이 5/19 KST → 5/18 00:00 KST = 5/17 15:00 UTC.
    이 시각 이전 기사는 모두 제외.
    """
    kst_offset    = timedelta(hours=9)
    now_kst       = datetime.utcnow() + kst_offset
    yesterday_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    return yesterday_kst - kst_offset

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

        all_pcts   = re.findall(r"[+\-][\d,]+\.?\d*\s*\(([+\-]?\d+\.?\d*%)\)", text)
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




def _fetch_exchange_settlement(target: dict) -> tuple:
    """GFEX 탄산리튬 결산가 API — 최근 거래일 롤백."""
    exchange = target["exchange"]

    if exchange == "GFEX":
        # 최근 거래일 롤백: 오늘 → 어제 → 그제 (주말·공휴일 대응, 최대 5일 탐색)
        trade_dates = []
        d = datetime.now()
        for _ in range(7):
            if d.weekday() < 5:  # 월~금
                trade_dates.append(d.strftime("%Y%m%d"))
            d -= timedelta(days=1)
            if len(trade_dates) >= 3:
                break

        gfex_urls = []
        for td in trade_dates:
            gfex_urls.append(f"https://www.gfex.com.cn/u/interfacesWebTyre/getSettlementInfo?variety=lc&trade_date={td}")
            gfex_urls.append(f"http://www.gfex.com.cn/u/interfacesWebTyre/getSettlementInfo?variety=lc&trade_date={td}")
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
                try:
                    data      = resp.json()
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
                nums = re.findall(r'\b(1[0-9]{4,5}|[5-9][0-9]{4})\b', raw)
                if nums:
                    settle = int(nums[0])
                    print(f"  GFEX fallback LC: {settle:,}")
                    return settle, "N/A"
            except Exception as e:
                print(f"  GFEX API 오류 ({url[:50]}): {e}")
        print("  GFEX API 전체 실패 → N/A")
        return None, "N/A"

    return None, "N/A"


async def _scrape_lcm_playwright(page, target: dict) -> dict:
    """www.metal.com/gfex — GFEX 탄산리튬 선물 주계약 수집.
    [PATCH] pct 추출: 4단계 fallback, 부호 없는 퍼센트도 변동폭 부호로 추론.
    """
    display = f"{target['exchange']}·{target['ticker']}"
    base    = {"name": target["name"], "exchange": target["exchange"], "ticker": display}

    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4000)

        try:
            await page.evaluate("window.stop()")
        except Exception:
            pass

        # ── 가격 추출 ───────────────────────────────────────────
        price = await page.evaluate("""
            () => {
                const text = (document.body ? document.body.innerText : '')
                             .replace(/[,，]/g, '');
                const nums = text.match(/[1-9]\\d{4,5}/g) || [];
                for (const s of nums) {
                    const n = parseInt(s);
                    if (n >= 100000 && n <= 300000) return n;
                }
                return null;
            }
        """)

        # ── 등락률: GFEX 결산가 API (SMM·LME와 동일 원리)
        # 최근 거래일 롤백으로 주말/장중 모두 안정적으로 수집
        _, change_pct = _fetch_exchange_settlement(target)
        if change_pct == "N/A":
            # API 실패 시 JS evaluate fallback
            change_pct = await page.evaluate("""
                () => {
                    const text = document.body ? document.body.innerText : '';
                    const combo = text.match(/([+\\-][\\d,]+)\\s*\\(\\s*([+\\-]?\\d+\\.?\\d*)\\s*%\\s*\\)/);
                    if (combo) {
                        const sign   = combo[1].trim().startsWith('-') ? '-' : '+';
                        const digits = combo[2].replace(/[+\\-]/, '').trim();
                        if (parseFloat(digits) !== 0) return sign + digits + '%';
                    }
                    const direct = text.match(/([+\\-]\\d+\\.\\d+%)/);
                    if (direct && parseFloat(direct[1]) !== 0) return direct[1];
                    return 'N/A';
                }
            """)
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



def _fetch_smm_articles(max_fetch: int = 8, cutoff: datetime = None,
                        existing_titles: list = None) -> list:
    """news.metal.com 직접 스크래핑.
    [PATCH]
    - 날짜 파싱 3단계 fallback
    - pub_date=None → 무조건 제외 (오래된 기사 반복 방지 핵심)
    - existing_titles: RSS dedup 후 기사 목록 → title 중복 체크
    """
    SMM_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    SMM_KEYWORDS = {
        "nickel", "cobalt", "lithium", "battery", "recycl", "black mass",
        "cathode", "precursor", "lme", "sulfate", "hydroxide", "carbonate",
    }
    existing_titles = existing_titles or []

    def _title_dup(new_title: str) -> bool:
        words_new = {w for w in re.sub(r'[^\w\s]', ' ', new_title).split() if len(w) >= 3}
        for t in existing_titles:
            words_t = {w for w in re.sub(r'[^\w\s]', ' ', t).split() if len(w) >= 3}
            if len(words_new & words_t) >= 4:
                return True
        return False

    try:
        r = requests.get("https://news.metal.com/en/", timeout=12, headers=SMM_HEADERS)
        if r.status_code != 200:
            print(f"  SMM 직접: 목록 {r.status_code}")
            return []
        ids = list(dict.fromkeys(re.findall(r'/newscontent/(\d{8,})', r.text)))[:max_fetch * 3]
        if not ids:
            return []

        articles      = []
        fetched       = 0
        skipped_date  = 0
        skipped_dup   = 0

        for article_id in ids:
            if fetched >= max_fetch:
                break
            try:
                url = f"https://news.metal.com/newscontent/{article_id}"
                r2  = requests.get(url, timeout=10, headers=SMM_HEADERS)
                if r2.status_code != 200:
                    continue

                # ── 날짜 파싱 3단계 ──────────────────────────────
                pub_date = None

                # 1단계: article:published_time 또는 datePublished 메타태그
                m_date = (
                    re.search(r'property="article:published_time"\s+content="([^"]+)"', r2.text) or
                    re.search(r'content="([^"]+)"\s+property="article:published_time"', r2.text) or
                    re.search(r'"datePublished"\s*:\s*"([^"]+)"', r2.text) or
                    re.search(r'"publishedAt"\s*:\s*"([^"]+)"', r2.text)
                )
                if m_date:
                    pub_date = parse_date(m_date.group(1))

                # 2단계: ISO datetime 패턴 검색
                if not pub_date:
                    iso_m = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', r2.text[:8000])
                    if iso_m:
                        pub_date = parse_date(iso_m.group(1))

                # 3단계: "May 18, 2026" 또는 "2026-05-18" 텍스트 패턴
                if not pub_date:
                    date_text_m = re.search(
                        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}'
                        r'|\b\d{4}-\d{2}-\d{2}\b',
                        r2.text[:8000]
                    )
                    if date_text_m:
                        pub_date = parse_date(date_text_m.group(0))

                # ── pub_date 불명 → 오늘자 간주 (포함) ──────────
                # news.metal.com 날짜 파싱 실패가 정상 (메타태그 미지원)
                # 목록 최신순 기사라 날짜불명이어도 오늘자로 처리
                if pub_date is None:
                    pub_date = datetime.utcnow()

                # ── cutoff 필터 ──────────────────────────────────
                if cutoff and pub_date < cutoff:
                    print(f"  SMM 날짜제외: {pub_date.strftime('%Y-%m-%d')} {url[-25:]}")
                    skipped_date += 1
                    continue

                # ── 제목 파싱 ────────────────────────────────────
                m_t = (re.search(r'property="og:title"\s+content="([^"]+)"', r2.text) or
                       re.search(r'content="([^"]+)"\s+property="og:title"', r2.text))
                if not m_t:
                    continue
                title = html_lib.unescape(m_t.group(1))
                title = re.sub(r'\s*[-|]\s*Shanghai Metals Market.*$', '', title).strip()

                if not any(k in title.lower() for k in SMM_KEYWORDS):
                    continue

                # ── title 중복 체크 (RSS dedup 기사와 비교) ───────
                if _title_dup(title):
                    print(f"  SMM title중복 제외: {title[:40]}")
                    skipped_dup += 1
                    continue

                m_d = (re.search(r'property="og:description"\s+content="([^"]+)"', r2.text) or
                       re.search(r'content="([^"]+)"\s+property="og:description"', r2.text))
                snippet = html_lib.unescape(m_d.group(1))[:200] if m_d else ""

                articles.append({
                    "title":    title,
                    "link":     url,
                    "snippet":  snippet,
                    "source":   "SMM Metal",
                    "priority": False,
                    "pub_date": pub_date,
                    "pub":      pub_date.strftime("%Y-%m-%d"),
                    "lang":     "en",
                })
                existing_titles.append(title)
                fetched += 1
                time.sleep(0.3)

            except Exception:
                continue

        print(f"  SMM 직접: {len(articles)}건 (날짜확인:{fetched - skipped_dup}건 / 중복제외:{skipped_dup}건)")
        return articles

    except Exception as e:
        print(f"  SMM 직접 오류: {e}")
        return []


def _fetch_westmetall_ni3m() -> dict:
    try:
        url  = "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Ni_cash"
        resp = requests.get(url, timeout=12,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code != 200:
            return {}

        rows = re.findall(
            r'<td[^>]*>\s*(\d{1,2}\.\s*\w+\s*\d{4})\s*</td>'
            r'\s*<td[^>]*>\s*([\d,]+\.?\d*)\s*</td>'
            r'\s*<td[^>]*>\s*([\d,]+\.?\d*)\s*</td>',
            resp.text
        )
        if len(rows) < 2:
            print(f"  westmetall: 행 부족 ({len(rows)}개)")
            return {}

        def p(s): return float(s.replace(",", ""))

        date_t1  = rows[0][0].strip()
        cash_t1  = p(rows[0][1]);  cash_t2 = p(rows[1][1])
        m3_t1    = p(rows[0][2]);  m3_t2   = p(rows[1][2])

        if not (10_000 < cash_t1 < 30_000 and 10_000 < m3_t1 < 30_000):
            return {}

        cash_pct = (cash_t1 - cash_t2) / cash_t2 * 100
        m3_pct   = (m3_t1   - m3_t2)   / m3_t2   * 100
        print(f"  westmetall Cash: ${cash_t1:,.0f} ({cash_pct:+.2f}%)  3M: ${m3_t1:,.0f} ({m3_pct:+.2f}%)")
        return {
            "cash":     cash_t1,  "cash_pct": f"{cash_pct:+.2f}%",
            "m3":       m3_t1,    "m3_pct":   f"{m3_pct:+.2f}%",
            "date":     date_t1,
        }

    except Exception as e:
        print(f"  westmetall 오류: {e}")
        return {}


async def _scrape_metalradar_ni3m(page) -> dict:
    result = _fetch_westmetall_ni3m()
    if result:
        return result

    print("  westmetall 실패 → metalradar.com 시도...")
    try:
        await page.goto(
            "https://metalradar.com/price/nickel/lme/official/3-month/cumulative-volume?includeOrigin=true",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(6000)
        body  = await page.inner_text("body")
        m_ask = re.search(r'Ask\s*\$?([\d,]+\.?\d*)', body)
        if not m_ask:
            return {}
        ask = float(m_ask.group(1).replace(",", ""))
        if not (15_000 < ask < 25_000):
            return {}
        print(f"  metalradar 3M: ${ask:,.0f} (pct=N/A)")
        return {"m3": ask, "m3_pct": "N/A", "date": datetime.now().strftime("%d. %b %Y")}
    except Exception as e:
        print(f"  metalradar 3M 오류: {e}")
        return {}


def _fetch_lme_nickel_kpi() -> dict:
    try:
        r = requests.get(
            "https://www.kpi.or.kr/www/contents/lme.asp?CFG_CD=con_09",
            headers={
                "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept":          "text/html,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            },
            timeout=10,
        )
        r.encoding = "euc-kr"
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.DOTALL):
            cells = [
                re.sub(r"<[^>]+>", "", c).strip()
                for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            ]
            cells = [c for c in cells if c]
            if not any("니켈" in c or "(Ni)" in c for c in cells):
                continue
            nums = []
            for c in cells:
                m = re.search(r"([\d,]+\.?\d*)", c)
                if m:
                    try:
                        v = float(m.group(1).replace(",", ""))
                        if 15_000 < v < 25_000:
                            nums.append(v)
                    except ValueError:
                        pass
            if len(nums) >= 2:
                cash, cash_prev = nums[0], nums[1]
                pct = (cash - cash_prev) / cash_prev * 100
                return {"cash": cash, "cash_pct": f"{pct:+.2f}%",
                        "date": datetime.now().strftime("%d. %b %Y")}
    except Exception as e:
        print(f"  LME 니켈 오류 (kpi.or.kr): {e}")
    return {}


async def scrape_smm_prices(usd_cny: float = 7.25) -> dict:
    spot_results, futures_results = [], []
    print("\n[SMM·LME 시세 수집]")

    print("  LME 니켈 수집 중...", end=" ", flush=True)
    wm = _fetch_westmetall_ni3m()
    if wm:
        lme_ni        = {"cash": wm["cash"], "cash_pct": wm["cash_pct"], "date": wm["date"]}
        ni3m_prefetch = wm
        print(f"OK (westmetall) ${wm['cash']:,.0f} ({wm['cash_pct']})")
    else:
        lme_ni        = _fetch_lme_nickel_kpi()
        ni3m_prefetch = None
        print(f"OK (kpi) ${lme_ni['cash']:,.0f} ({lme_ni['cash_pct']})" if lme_ni else "W 실패")

    CHROMIUM_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    BROWSER_UA    = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        ctx     = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
        page    = await ctx.new_page()

        for t in SPOT_TARGETS:
            print(f"  현물: {t['name']} ...", end=" ", flush=True)
            r = await _scrape_spot(page, t)
            spot_results.append(r)
            print("OK" if r["status"] == "OK" else f"W {r['status']}")

            if t["name"] == "황산코발트":
                if lme_ni:
                    ni_entry = {
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
                else:
                    ni_entry = {"name": "니켈", "name_en": "LME Nickel",
                                "source": "LME", "status": "ERROR: 수집 실패"}
                spot_results.append(ni_entry)
                status_str = f"${lme_ni['cash']:,.0f} ({lme_ni['cash_pct']})" if lme_ni else "ERROR"
                print(f"  현물: 니켈(LME) ... {status_str}")

            await asyncio.sleep(2)

        if ni3m_prefetch:
            ni3m = ni3m_prefetch
            print(f"  LME 3M: ${ni3m['m3']:,.0f} ({ni3m['m3_pct']}) ← westmetall")
        else:
            print("  LME 3M 수집 중 (metalradar.com)...", end=" ", flush=True)
            ni3m = await _scrape_metalradar_ni3m(page)
        if not ni3m:
            print("W 실패")

        for t in FUTURES_EM:
            print(f"  선물: {t['name']}({t['exchange']}) ...", end=" ", flush=True)
            if t.get("method") == "playwright":
                r = await _scrape_lcm_playwright(page, t)
                futures_results.append(r)
                print(f"OK ({r.get('ticker','?')})" if r["status"] == "OK" else f"W {r['status']}")
                try:
                    await asyncio.wait_for(browser.close(), timeout=8.0)
                except (asyncio.TimeoutError, Exception):
                    pass
                browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
                ctx     = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
                page    = await ctx.new_page()
            elif t.get("method") == "metalradar":
                if ni3m:
                    r = {
                        "name":            t["name"],
                        "exchange":        "LME",
                        "ticker":          "LME·3M",
                        "source":          "metalradar.com",
                        "date":            ni3m["date"],
                        "latest":          round(ni3m["m3"]),
                        "latest_vat_excl": round(ni3m["m3"] * usd_cny),
                        "change_pct":      ni3m["m3_pct"],
                        "delayed":         True,
                        "status":          "OK",
                    }
                    print(f"OK (3M ${ni3m['m3']:,.0f})")
                else:
                    r = {"name": t["name"], "exchange": "LME",
                         "ticker": "LME·3M", "status": "ERROR: 수집 실패"}
                    print("W 실패")
                futures_results.append(r)


        await browser.close()

    return {"spot": spot_results, "futures": futures_results}


def compute_spreads(price_data: dict) -> dict:
    spot_map    = {r["name"]: r for r in price_data["spot"]    if r["status"] == "OK"}
    futures_map = {r["exchange"]: r for r in price_data["futures"] if r["status"] == "OK"}
    spreads     = {}

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

    ni_data   = futures_map.get("LME", {})
    ni_spot_r = spot_map.get("니켈", {})
    ni_s      = ni_spot_r.get("usd_excl")
    ni_f      = ni_data.get("latest")
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

    lines.append("\n[현물 - 증치세제외 기준]")
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
# pre-clustering — collect_rss() 위에 위치
# ============================================================
def _pre_cluster_articles(articles: list) -> list:
    """동일 이슈 기사 사전 클러스터링.
    [PATCH] 같은 언어 내 제목 단어 5개 이상 겹치면 body가 더 긴 1건만 유지.
    다른 언어끼리(한국어+영어 등)는 각각 독립 취급.
    예: 재생원료 인증제 관련 한국어 기사 5건 → 1건으로 축소.
    """
    kept = []

    for a in articles:
        lang_a  = a.get("lang", "")
        words_a = {w for w in re.sub(r'[^\w\s]', ' ', a["title"]).split() if len(w) >= 2}
        len_a   = len(a.get("body", "") or a.get("snippet", ""))

        merged = False
        for i, b in enumerate(kept):
            if b.get("lang", "") != lang_a:
                continue
            words_b = {w for w in re.sub(r'[^\w\s]', ' ', b["title"]).split() if len(w) >= 2}
            if len(words_a & words_b) >= 5:
                # body가 더 긴 쪽으로 교체
                len_b = len(b.get("body", "") or b.get("snippet", ""))
                if len_a > len_b:
                    kept[i] = a
                merged = True
                break

        if not merged:
            kept.append(a)

    removed = len(articles) - len(kept)
    if removed > 0:
        print(f"  pre-clustering: {removed}건 통합 → {len(kept)}건 유지")
    return kept

# ============================================================
# RSS 수집
# ============================================================
def collect_rss():
    now    = datetime.utcnow()

    # KST 어제 자정 기준 cutoff (UTC)
    cutoff     = get_cutoff_utc()
    cutoff_kst = cutoff + timedelta(hours=9)
    print(f"  [날짜 필터] {cutoff_kst.strftime('%Y-%m-%d %H:%M')} KST 이후 기사만 수집")

    raw  = []
    seen = set()

    for item in QUERIES:
        is_priority = item.get("priority", False)

        try:
            q   = item["q"] + " when:2d"
            url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}"
                   f"&hl={item['lang']}&gl={item['gl']}&ceid={item['ceid']}&num=10"
                   f"&cb={int(now.timestamp())}")
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)

            for entry in root.findall(".//item"):
                title     = decode_entities((entry.findtext("title") or "").strip())
                link      = (entry.findtext("link") or "").strip()
                link      = extract_real_url(link)
                pub_str   = (entry.findtext("pubDate") or "").strip()
                source_el = entry.find("source")
                source    = source_el.text.strip() if source_el is not None else ""
                # ★ source 태그의 url 속성도 체크 (Google News 우회 방지)
                source_url = (source_el.get("url", "") or "").lower() if source_el is not None else ""
                snippet   = decode_entities(
                    re.sub(r'<[^>]+>', '', entry.findtext("description") or "")
                )[:200]

                if not title or not link or link in seen:
                    continue

                pub_date = parse_date(pub_str)

                # KST 어제 자정 이전 기사 제외
                if pub_date and pub_date < cutoff:
                    continue

                if "metal.com" in link.lower():
                    source = "SMM Metal"

                lt = title.lower()
                ls = source.lower()
                ll = link.lower()

                if any(s in ls or s in ll or s in source_url for s in NOISE_SOURCES):
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

                # 인도네시아어 strict 필터
                if item.get("lang") == "id":
                    if not any(k in lt for k in _ID_NICKEL_STRICT):
                        continue

                seen.add(link)
                raw.append({
                    "title":    title,
                    "link":     link,
                    "source":   source,
                    "pub":      pub_str,
                    "pub_date": pub_date,
                    "lang":     item.get("lang", "en"),
                    "snippet":  snippet,
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

    # SMM 직접 수집 — existing_titles 전달로 title dedup 적용
    existing_titles_for_smm = [a["title"] for a in deduped]
    smm_direct = _fetch_smm_articles(cutoff=cutoff, existing_titles=existing_titles_for_smm)
    for a in smm_direct:
        if not any(a["link"] == x.get("link") for x in deduped):
            deduped.append(a)

    # pre-clustering: 동일 이슈 기사 Python 레벨 통합
    deduped = _pre_cluster_articles(deduped)

    sc = sum(1 for a in deduped if "SMM" in a.get("source", ""))
    pc = sum(1 for a in deduped if a.get("priority"))
    print(f"수집: {len(raw)}건 -> 클러스터링후: {len(deduped)}건 (SMM:{sc}건, 시황매체:{pc}건)")
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
    try:
        await page.goto(cbm_url, wait_until="commit", timeout=15000)
    except Exception:
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
            if browser:
                await browser.close()

    return targets

# ============================================================
# Gemini 분석
# ============================================================
def analyze(articles, price_data: dict = None, usd_cny: float = 7.25):
    today = datetime.now().strftime("%Y년 %m월 %d일")

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
        spreads   = compute_spreads(price_data)
        price_str = format_price_for_prompt(price_data, usd_cny, spreads)
        price_sec = f"\n[당일 SMM 시세]\n{price_str}\n"
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
- articles는 반드시 8건 이상 12건 이하로 선택.
- 위 뉴스 목록에서 최대한 많이 선택. 관련도 낮아도 배터리/소재/공급망이면 포함.
- 성일하이텍 기사 반드시 포함.
- 태그: 반드시 아래 5개 중 정확히 하나 선택 → 원재료 및 시황 / 투자 및 M&A / 정책 및 규제 / 공급망 및 파트너십 / 기술 및 공정
- 금지: 증권리포트/주가기사/IR공시/유상증자/ETF/신차리뷰/PR배포/스마트폰기사

★ [유사 기사 통합 규칙]
- 동일 이슈 기사가 2건 이상이면 가장 정보가 풍부한 1건만 선택.
  summary에서 "○○·△△ 등 복수 매체 보도" 방식으로 통합 언급.
- 언어/관점이 다른 경우(한국어+영어)는 각 1건 허용.

[요약기준] 3문장이내. 기관명·기업명·금액·수치·날짜 필수. 추상적요약금지.
계획≠실행, MOU≠계약, 검토≠확정.

[트렌드3개] 한국/중국/미국EU 균형. 오늘 기사 수치·정책명 직접인용.
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

    spot_rows = ""
    for r in price_data["spot"]:
        ok      = r.get("status") == "OK"
        name    = r.get("name", "")
        src     = r.get("source", "SMM")
        pct     = r.get("change_pct", "N/A") if ok else "N/A"
        delayed = r.get("delayed", False)

        badges = _source_badge(src)
        if name == "황산코발트":
            badges += ('<span style="display:inline-block;background:#e2e8f0;color:#64748b;'
                       'font-size:9px;padding:1px 5px;border-radius:3px;margin-left:3px;'
                       'vertical-align:middle;">참고</span>')
        if delayed:
            badges += ('<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                       'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                       'margin-left:3px;vertical-align:middle;">T-1</span>')

        if ok:
            usd_str    = _fmt(r.get("usd_excl"), "$")
            cny_str    = _fmt(r.get("cny_excl"), "CNY")
            price_cell = (
                f'<b style="font-size:13px;">{usd_str}</b>'
                f'<br><span style="color:#aaaaaa;font-size:11px;">{cny_str}</span>'
            )
        else:
            price_cell = '<span style="color:#aaaaaa;">—</span>'

        if ok and name == "황산코발트" and r.get("usd_metal"):
            extra_cell = (
                f'<b style="font-size:12px;">{_fmt(r.get("usd_metal"), "$")}</b>'
                f'<br><span style="color:#aaaaaa;font-size:10px;">Co 금속환산</span>'
            )
        elif ok and src == "LME":
            extra_cell = '<span style="color:#94a3b8;font-size:11px;">직접 금속가</span>'
        else:
            extra_cell = '<span style="color:#d1d5db;">—</span>'

        label   = name.replace("배터리용 ", "BG ").replace("공업용 ", "TG ")
        name_en = r.get("name_en", "")

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

    fut_rows = ""
    for r in price_data["futures"]:
        ok      = r.get("status") == "OK"
        is_lme  = r.get("exchange") == "LME"
        pct     = r.get("change_pct", "N/A") if ok else "N/A"
        delayed = r.get("delayed", False)
        ticker  = r.get("ticker", "")
        label   = r.get("name", "").replace(" 선물", "")

        f_badges = ""
        if delayed:
            f_badges += ('<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                         'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                         'margin-left:4px;vertical-align:middle;">T-1</span>')

        if ok:
            if is_lme:
                usd     = r.get("latest")
                cny     = r.get("latest_vat_excl")
                price_f = (
                    f'<b style="font-size:13px;">{_fmt(usd, "$")}</b>'
                    f'<br><span style="color:#aaaaaa;font-size:11px;">{_fmt(cny, "CNY")}</span>'
                )
            else:
                ve      = r.get("latest_vat_excl")
                ue      = round(ve / usd_cny) if ve else None
                price_f = (
                    f'<b style="font-size:13px;">{_fmt(ue, "$")}</b>'
                    f'<br><span style="color:#aaaaaa;font-size:11px;">{_fmt(ve, "CNY")}</span>'
                )
        else:
            price_f = '<span style="color:#aaaaaa;">—</span>'

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
            <td style="padding:10px 14px;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">현물 (Spot) · 품목</td>
            <td style="padding:10px 14px;text-align:right;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">USD/t<br><span style="font-weight:400;font-size:10px;color:#94a3b8;">CNY/t 환산</span></td>
            <td style="padding:10px 14px;text-align:right;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">추가정보</td>
            <td style="padding:10px 14px;text-align:center;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">등락</td>
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
