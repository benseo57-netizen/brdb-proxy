import os
import json
import glob
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

def now_kst() -> datetime:
    """GitHub Actions는 UTC 서버 → KST(+9h) 보정."""
    return datetime.utcnow() + timedelta(hours=9)

from playwright.async_api import async_playwright
import google.generativeai as genai

# 환경변수
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
GMAIL_USER     = os.environ['GMAIL_USER']
GMAIL_APP_PASS = os.environ['GMAIL_APP_PASSWORD']
TO_EMAIL       = os.environ['TO_EMAIL']
BCC_EMAIL      = os.environ.get('BCC_EMAIL', '')

genai.configure(api_key=GEMINI_API_KEY)

# GitHub Pages
GITHUB_USER = "benseo57-netizen"
REPO_NAME   = "brdb-proxy"
WEB_BASE    = f"https://{GITHUB_USER}.github.io/{REPO_NAME}"

PRICE_JSON = "docs/data/prices.json"

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
    {"name": "탄산리튬 선물", "exchange": "GFEX",
     "url": "https://www.metal.com/gfex", "ticker": "LCM", "method": "playwright"},
    {"name": "니켈 선물", "exchange": "LME",
     "ticker": "LME·3M", "method": "metalradar"},
]

# 날씨 (Open-Meteo, API 키 불필요)
WEATHER_SPOTS = [
    {"name": "새만금", "lat": 35.80,   "lon": 126.62},
    {"name": "전주",   "lat": 35.8242, "lon": 127.1480},
    {"name": "서울",   "lat": 37.5665, "lon": 126.9780},
]

# ============================================================
# 피드 정의 (Inoreader 구독 기반)
# ============================================================

# 배터리/EV 전문지 → 화이트리스트 통과 불필요
PUBLISHER_FEEDS_SPECIAL = [
    {"url": "https://batteriesnews.com/feed/",       "source": "Batteries News",      "lang": "en"},
    {"url": "https://chargedevs.com/feed/",          "source": "Charged EVs",         "lang": "en"},
    {"url": "https://www.electrive.net/feed/",       "source": "electrive",           "lang": "en"},
    {"url": "https://www.energy-storage.news/feed/", "source": "Energy Storage News", "lang": "en"},
]

# 종합 매체 → 화이트리스트 검사 필요
PUBLISHER_FEEDS_GENERAL = [
    {"url": "https://www.theguru.co.kr/data/rss/news.xml", "source": "더구루", "lang": "ko"},
    {"url": "http://www.thelec.kr/rss/allArticle.xml",     "source": "디일렉", "lang": "ko"},
]

# 구글 뉴스 — 단순 키워드로 넓게
GOOGLE_FEEDS = [
    {"q": "battery recycling", "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": "black mass",        "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": "battery scrap",     "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": "lithium",           "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": "nickel",            "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": "cobalt",            "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": "LFP",               "lang": "en", "gl": "US", "ceid": "US:en"},
    {"q": "폐배터리",           "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "사용후배터리",       "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "블랙매스",           "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "배터리 리사이클링",   "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "이차전지",           "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "2차전지",            "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "배터리ON",           "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "전기차 배터리 공급",  "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "리튬",               "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "니켈",               "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "코발트",             "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
    {"q": "성일하이텍",         "lang": "ko", "gl": "KR", "ceid": "KR:ko"},
]

# ============================================================
# 노이즈 필터
# ============================================================
NOISE_KEYWORDS = [
    "crypto", "bitcoin", "ethereum", "nft", "dogecoin",
    "게임", "영화", "드라마", "car review", "smartphone review",
    "xiaomi", "samsung galaxy", "iphone", "smartwatch", "okosóra",
    "stock tip",
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
    "续航有", "续航里程", "驾驶里程", "endurance test", "driving range test",
    "cassava", "agriculture", "crop",
    "petro", "petroleum", "oil refin",
    "dow jones", "s&p 500", "nasdaq",
    "blue whale season", "whale watching", "whale migration",
    "motorola", "ipad", "smartphone launch",
    "foldable phone", "razr", "pixel phone", "snapdragon",
    "launched in india", "goes on sale", "pre-order",
    "playstation", "nintendo", "xbox", "gaming", "konzol", "konsol",
    "redmi", "poco", "iqoo", "oneplus", "nothing phone", "hordozható",
    "oppo", "vivo", "realme", "honor phone",
    "táblagép", "diákoknak", "tablet pc",
    "试驾", "续航里程达成率", "驾驶体验",
    "e-waste leader", "ewaste leader", "e-waste market", "ewaste market",
    "paris saint-germain", "psg sponsor", "byd psg",
    "通病集中爆发", "车子开着",
    # 전기차 쿼리 확대 대응
    "신차 출시", "출시 임박", "사전계약", "시승기", "타보니",
    "디자인 공개", "렌더링", "스파이샷", "풀체인지", "페이스리프트",
    "보조금 신청", "충전소 설치",
    "first drive", "road test", "review:", "hands-on",
    "best electric cars", "buying guide", "deals",
    # 종합매체 대응
    "반도체 장비", "디스플레이 패널", "oled 패널", "메모리 반도체",
    # 지자체 보조금 공고
    "구매보조금", "보조금 추가", "추가 지원", "지원 사업 공고",
    "보급사업", "신청 접수", "접수 시작",
    # 충전 인프라 일반
    "충전요금", "충전비", "충전소 확대", "충전기 설치", "이동식 충전",
    "완속충전", "급속충전기", "ladeinfrastruktur", "ladestation",
    # 신차·판매·시승
    "판매 증가", "판매량", "출고", "가격 인하", "할인 판매",
    "주행거리", "제로백", "인테리어",
    "특징주", "급등", "급락",
    # 수소·태양광 (전문지에 섞여 옴)
    "green hydrogen", "수소차", "수소충전", "태양광", "solar panel",
    "photovoltaic", "wind power", "wasserstoff",
    # 보증·보험
    "보증 연장", "warranty", "versicherung", "garantie",
]

NOISE_SOURCES = [
    "openpr", "prnewswire", "businesswire", "globenewswire", "einpresswire",
    "accesswire", "prnews", "prlog", "marketwired", "newswire", "pr.com", "prweb",
    "discoveryalert", "bravenewcoin", "eurekaalert", "cryptoslate", "coindesk",
    "benzinga", "seekingalpha", "motleyfool", "investopedia", "indexbox",
    "msn", "msn.com", "aol.com", "simplywall.st", "futunn.com", "judal.co.kr",
    "investingnews.com", "thebull.com.au", "marketsmojo.com",
    "switzer.com.au", "nai500.com", "kalkinemedia.com",
    "chartmill", "vozpopuli", "mixvale", "vietnam.vn",
    "ad-hoc-news", "stocktitan",
    "bitget", "belfasttelegraph", "technetbooks", "saudigazette", "techjuice",
    "mexc", "autohome",
    "marketindex.com.au", "harianbasis",
    "newsonair.gov.in", "akashvani", "pib.gov.in", "tradebrains.in",
]

NOISE_URL_PATHS = ["/stock/", "/en/stock/", "/stocks/", "/share-price/", "/equity/"]

NOISE_PAIRS = [
    ("plastic", "recycl"), ("alumin", "recycl"), ("bauxite", "recycl"),
    ("fiber", "recycl"), ("packaging", "recycl"), ("paper", "recycl"),
    ("recycled film", "feedstock"), ("scrap", "alumin"),
    ("e-waste", "phone"), ("e-waste", "electronic"), ("namo", "waste"),
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
    "gigafactory", "kwh", "mwh", "ev ", "electric vehicle", "전기차",
    "ess", "energy storage", "에너지저장",
    "fastmarkets", "benchmark mineral", "s&p global", "smm",
    "sungeel", "성일", "ascend", "redwood", "cirba", "ecobat", "umicore", "glencore",
    "retriev", "battery resources", "interco", "princeton nuenergy",
    "is eco solution", "fortum", "stena",
    "sk온", "sk on", "lg에너지솔루션", "lg energy solution", "삼성sdi",
    "catl", "byd", "panasonic", "northvolt",
    "에코프로비엠", "에코프로", "포스코퓨처엠", "엘앤에프", "성일하이텍",
    "albemarle", "sqm", "ganfeng", "tianqi",
    "pilbara", "liontown", "arcadium", "sigma lithium",
    "circular economy", "생산자책임", "핵심광물", "critical mineral",
    "nikel", "rkef", "ferronickel", "hilirisasi",
    "电池", "回收", "锂", "镍", "钴", "宁德时代", "比亚迪",
    "リサイクル", "電池", "リチウム", "ニッケル", "コバルト",
]

# ============================================================
# 관련도 점수 — 본문 추출 대상 선별용
# ============================================================
_SCORE_CORE = [
    ("블랙매스", 12), ("black mass", 12), ("폐배터리", 10), ("사용후배터리", 10),
    ("배터리 재활용", 12), ("battery recycl", 12), ("스크랩", 8), ("battery scrap", 10),
    ("습식제련", 10), ("hydrometallurg", 10), ("hydromet", 8), ("hpal", 8),
    ("건식제련", 8), ("pyrometallurg", 8), ("direct recycling", 10),
    ("회수율", 6), ("recovery rate", 6), ("지불률", 10), ("payable", 8),
    ("재활용", 6), ("recycl", 6), ("순환이용", 6), ("circular economy", 5),
]

_SCORE_METAL = [
    ("탄산리튬", 8), ("수산화리튬", 8), ("황산니켈", 8), ("황산코발트", 8),
    ("lithium carbonate", 8), ("lithium hydroxide", 8),
    ("nickel sulfate", 8), ("cobalt sulfate", 8),
    ("리튬", 4), ("니켈", 4), ("코발트", 4),
    ("lithium", 4), ("nickel", 4), ("cobalt", 4),
    ("mhp", 6), ("npi", 5), ("ferronickel", 5), ("nickel matte", 6),
    ("양극재", 5), ("전구체", 5), ("cathode", 5), ("precursor", 5),
    ("lfp", 4), ("ncm", 4), ("nca", 4),
    # ESS = 향후 폐배터리 발생원 + 셀 공정 스크랩 발생원
    ("ess 배터리", 7), ("ess용", 7), ("ess 셀", 8), ("ess 수주", 7),
    ("ess 공급", 7), ("ess 증설", 7), ("ess 시장", 5), ("ess 수요", 6),
    ("energy storage battery", 7), ("storage cell", 7), ("lfp ess", 9),
    ("에너지저장장치", 4), ("배터리 셀", 5), ("셀 생산", 5), ("기가팩토리", 5),
]

_SCORE_POLICY = [
    ("수출 규제", 8), ("수입 규제", 8), ("export ban", 8), ("export quota", 8),
    ("바젤", 10), ("basel convention", 10), ("epr", 7),
    ("핵심광물", 7), ("critical mineral", 7),
    ("battery regulation", 7), ("battery passport", 7), ("recycled content", 8),
    ("관세", 5), ("tariff", 5), ("ira", 5), ("rkab", 8), ("quota", 5),
    ("폐기물관리법", 10), ("환경부", 5), ("산업부", 5),
    ("공급망", 5), ("supply chain", 5), ("합작", 6), ("joint venture", 6),
    ("인수", 5), ("acquisition", 5), ("증설", 5), ("착공", 5),
]

_SCORE_COMPANY = [
    ("성일하이텍", 15), ("sungeel", 15),
    ("에코프로씨엔지", 10), ("아이에스티엠씨", 10), ("is에코솔루션", 10),
    ("redwood materials", 10), ("ascend elements", 10), ("cirba", 10),
    ("ecobat", 10), ("umicore", 9), ("glencore", 8), ("fortum", 8),
    ("stena", 8), ("li-cycle", 10), ("altilium", 8), ("tozero", 8),
    ("brunp", 9), ("邦普", 9), ("格林美", 9),
    ("catl", 5), ("byd", 4), ("lg에너지솔루션", 4), ("sk온", 4), ("삼성sdi", 4),
    ("에코프로비엠", 4), ("포스코퓨처엠", 4), ("엘앤에프", 4),
]

_SCORE_PENALTY = [
    ("보조금", -12), ("구매지원", -12), ("충전소", -10), ("충전", -6),
    ("신차", -10), ("시승", -12), ("판매량", -8), ("판매 증가", -8),
    ("주행거리", -10), ("디자인", -8), ("가격 인하", -8),
    ("특징주", -15), ("급등", -12), ("주가", -15),
    ("epc", -10), ("turnkey", -8), ("발전소", -10), ("전력망", -8),
    ("ppa", -8), ("계통연계", -8), ("착공식", -8), ("준공식", -8),
    ("solar farm", -10), ("wind farm", -10), ("인버터", -8),
    ("희토류", -10), ("rare earth", -10), ("prnd", -12), ("네오디뮴", -8),
    ("solar", -10), ("hydrogen", -12), ("수소", -12),
    ("charging", -6), ("charger", -8),
    ("warranty", -8), ("보증", -6),
]

# 성일 사업 구조에 직접 영향을 주는 사건
# ("재활용"이라는 단어가 없어도 원료 조달·거점 운영에 직결되는 것들)
_SCORE_STRUCTURE = [
    # 해외법인 소재지 — 현지 사건은 직접 영향
    ("인디애나", 12), ("indiana", 12),
    ("헝가리", 10), ("hungary", 10), ("ungarn", 10),
    ("폴란드", 10), ("poland", 10), ("polen", 10),
    ("말레이시아", 8), ("malaysia", 8),
    ("인도네시아", 7), ("indonesia", 7),
    ("군산", 4), ("새만금", 4),

    # 셀사 가동 상황 = 스크랩 발생원 변화
    ("가동 중단", 10), ("가동중단", 10), ("생산 차질", 10),
    ("halted", 9), ("suspend", 8), ("shutdown", 9), ("셧다운", 9),
    ("공장 중단", 10), ("감산", 8), ("가동률", 7), ("증산", 6),
    ("공장 신설", 7), ("라인 전환", 7), ("전환 투자", 7),

    # 공급망 재편 — 성일 사업 환경 자체가 바뀌는 사건
    ("중국 의존", 10), ("탈중국", 10), ("de-risking", 8),
    ("현지화", 8), ("내재화", 9), ("수직계열화", 9),
    ("공급망 재편", 10), ("공급망 다변화", 9), ("공급망 안보", 8),
    ("장기 공급", 7), ("장기계약", 7), ("offtake", 8), ("long-term supply", 7),
    ("지분 인수", 7), ("지분 투자", 6), ("합작법인", 7),
    ("정제", 6), ("refining", 6), ("제련", 6), ("smelting", 5),
    ("원료 확보", 8), ("원재료 확보", 8), ("소재 확보", 7),
]

_ALL_SCORES = (_SCORE_CORE + _SCORE_METAL + _SCORE_POLICY +
               _SCORE_COMPANY + _SCORE_STRUCTURE + _SCORE_PENALTY)


def relevance_score(article: dict) -> int:
    """제목+스니펫 기준 관련도. 높을수록 성일 사업과 직결."""
    text  = (article.get("title", "") + " " + article.get("snippet", "")).lower()
    score = sum(pt for kw, pt in _ALL_SCORES if kw in text)

    src = (article.get("source") or "").lower()
    if "smm" in src:
        score += 6
    elif article.get("priority"):
        score += 3

    title = article.get("title", "").lower()
    if any(kw in title for kw, _ in _SCORE_CORE[:8]):
        score += 5

    return score

# 중복 판정 제외 불용어
_STOPWORDS = {
    "the","a","an","to","in","of","on","for","and","or","as","at","by",
    "is","are","be","was","were","it","its","with","from","that","this",
    "has","have","will","not","new","up","down","over","out","after",
    "안","및","등","것","수","위","더","이","그","저","중","해","때","약",
}

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
    except Exception:
        pass
    try:
        return datetime.fromisoformat(pub_str.replace('Z', '').replace('+00:00', ''))
    except Exception:
        return None

def extract_real_url(url):
    if "google.com/url" in url:
        m = re.search(r'[?&]url=([^&]+)', url)
        if m:
            return urllib.parse.unquote(m.group(1))
    return url

def _sig_words(title: str) -> set:
    ws = re.sub(r'[^\w\s]', ' ', title.lower()).split()
    return {w for w in ws if len(w) >= 2 and w not in _STOPWORDS}

def get_cutoff_utc() -> datetime:
    """평일: 어제 00:00 KST / 월요일: 3일 전 (주말 뉴스 포함)"""
    kst_offset = timedelta(hours=9)
    _now_kst   = datetime.utcnow() + kst_offset
    back_days  = 3 if _now_kst.weekday() == 0 else 1
    base_kst   = _now_kst.replace(hour=0, minute=0, second=0, microsecond=0) \
                 - timedelta(days=back_days)
    return base_kst - kst_offset

def _fmt(val, prefix="") -> str:
    if val is None:
        return "—"
    return f"{prefix}{val:,.0f}"

def _pct_color(pct: str) -> str:
    if not pct or pct == "N/A":
        return "#888888"
    return "#c0392b" if "+" in pct else "#2471a3"

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
        change_pct = next((p for p in all_pcts if p != "0%"),
                          ("0.00%" if all_pcts else "N/A"))

        date_m = re.search(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4})", text)

        usd_excl = float(usd_list[0].replace(",", "")) if usd_list else None
        cny_incl = float(cny_list[0].replace(",", "")) if cny_list else None
        cny_excl = round(cny_incl / VAT_RATE) if cny_incl else None

        # 범위 검증 — 파싱 오류로 엉뚱한 값이 들어가는 것 방지
        if usd_excl is not None and not (500 < usd_excl < 200_000):
            return {**base, "status": f"ERROR: 범위 이탈 ({usd_excl})"}

        mc, ml    = target.get("metal_content"), target.get("metal_label")
        usd_metal = round(usd_excl / mc) if (usd_excl and mc) else None
        cny_metal = round(cny_excl / mc) if (cny_excl and mc) else None

        return {
            **base,
            "date":          date_m.group(1) if date_m else "N/A",
            "usd_excl":      usd_excl,  "cny_incl": cny_incl, "cny_excl": cny_excl,
            "usd_metal":     usd_metal, "cny_metal": cny_metal,
            "metal_content": mc, "metal_label": ml,
            "change_pct":    change_pct, "status": "OK",
        }
    except Exception as e:
        return {**base, "status": f"ERROR: {e}"}


_LCM_JS = """
() => {
    const raw = (document.body ? document.body.innerText : '').replace(/[,]/g, '');
    let price = null, pricePos = -1, pos = 0;
    while (pos < raw.length) {
        const m = raw.slice(pos).match(/\\b([1-3]\\d{5})\\b/);
        if (!m) break;
        const n = parseInt(m[1]);
        if (n >= 100000 && n <= 300000) { price = n; pricePos = pos + m.index; break; }
        pos += m.index + m[1].length;
    }
    if (price === null) return { price: null, pct: 'N/A' };
    const win = raw.substring(Math.max(0, pricePos - 80), pricePos + 250);
    const all = [...win.matchAll(/([+\\-]?\\d+\\.\\d+)\\s*%/g)];
    for (const m2 of all) {
        const v = parseFloat(m2[1]);
        if (Math.abs(v) > 0 && Math.abs(v) < 25) {
            return { price: price, pct: (v >= 0 ? '+' : '') + v.toFixed(2) + '%' };
        }
    }
    return { price: price, pct: 'N/A' };
}
"""

async def _scrape_lcm_playwright(page, target: dict) -> dict:
    display = f"{target['exchange']}·{target['ticker']}"
    base    = {"name": target["name"], "exchange": target["exchange"], "ticker": display}
    try:
        await page.goto(target["url"], wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(4000)
        try:
            await page.evaluate("window.stop()")
        except Exception:
            pass

        result     = await page.evaluate(_LCM_JS)
        price      = result.get("price") if result else None
        change_pct = result.get("pct", "N/A") if result else "N/A"
        print(f"  metal.com/gfex LCM: price={price}, pct={change_pct}")

        if price:
            return {
                **base,
                "date":            now_kst().strftime("%b %d, %Y"),
                "latest":          price,
                "latest_vat_excl": round(price / VAT_RATE),
                "change_pct":      change_pct,
                "prev_close":      None,
                "status":          "OK",
            }
    except Exception as e:
        print(f"  metal.com/gfex 오류: {e}")
    return {**base, "status": "ERROR: 가격 파싱 실패"}


def _fetch_smm_rss(max_fetch: int = 5, cutoff: datetime = None,
                   existing_titles: list = None) -> list:
    RSS_URL = "https://rss.metal.com/news/the_latest.xml"
    RELEVANT_METALS = {
        "new energy", "lithium battery", "nickel", "cobalt",
    }
    SMM_KEYWORDS = {
        "nickel", "cobalt", "lithium", "battery", "recycl", "black mass",
        "cathode", "precursor", "sulfate", "hydroxide", "carbonate",
        "mhp", "npi", "lfp", "ncm", "nca", "black mass", "battery scrap",
    }
    existing_titles = existing_titles or []

    def _parse_pubdate(s: str):
        try:
            return datetime.strptime(s.strip(), "%H:%M:%S %b %d, %Y")
        except Exception:
            return None

    def _title_dup(title: str) -> bool:
        wn = _sig_words(title)
        return any(len(wn & _sig_words(t)) >= 4 for t in existing_titles)

    try:
        resp = requests.get(RSS_URL, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code != 200:
            print(f"  SMM RSS: HTTP {resp.status_code}")
            return []

        root = ET.fromstring(resp.content)
        articles = []
        sk_metal = sk_date = sk_dup = 0

        for item in root.findall(".//item"):
            metal_el   = item.find("metal")
            metal_text = (metal_el.text or "").lower() if metal_el is not None else ""
            metals     = {m.strip() for m in metal_text.split(",")}
            if not (metals & RELEVANT_METALS):
                sk_metal += 1
                continue

            title_el = item.find("title")
            title    = (title_el.text or "").strip() if title_el is not None else ""
            if not title:
                continue

            pub_el   = item.find("pubDate")
            pub_str  = (pub_el.text or "").strip() if pub_el is not None else ""
            pub_date = _parse_pubdate(pub_str)
            if pub_date is None:
                sk_date += 1
                continue
            smm_cutoff = (cutoff - timedelta(hours=8)) if cutoff else None
            if smm_cutoff and pub_date < smm_cutoff:
                sk_date += 1
                continue

            link_el = item.find("link")
            link    = (link_el.text or "").strip() if link_el is not None else ""
            if not link:
                continue

            desc_el = item.find("description")
            snippet = (desc_el.text or "").strip()[:400] if desc_el is not None else ""

            combined = (title + " " + snippet).lower()
            if not any(k in combined for k in SMM_KEYWORDS):
                sk_metal += 1
                continue

            if _title_dup(title):
                sk_dup += 1
                continue

            articles.append({
                "title": title, "link": link, "snippet": snippet,
                "source": "SMM Metal", "priority": False,
                "pub_date": pub_date, "pub": pub_date.strftime("%Y-%m-%d"),
                "lang": "en",
            })
            existing_titles.append(title)
            if len(articles) >= max_fetch:
                break

        print(f"  SMM RSS: {len(articles)}건 (제외 {sk_metal}/{sk_date}/{sk_dup})")
        return articles
    except Exception as e:
        print(f"  SMM RSS 오류: {e}")
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

        date_t1 = rows[0][0].strip()
        cash_t1, cash_t2 = p(rows[0][1]), p(rows[1][1])
        m3_t1,   m3_t2   = p(rows[0][2]), p(rows[1][2])

        if not (10_000 < cash_t1 < 30_000 and 10_000 < m3_t1 < 30_000):
            return {}

        cash_pct = (cash_t1 - cash_t2) / cash_t2 * 100
        m3_pct   = (m3_t1 - m3_t2) / m3_t2 * 100
        print(f"  westmetall Cash ${cash_t1:,.0f} ({cash_pct:+.2f}%) 3M ${m3_t1:,.0f}")
        return {"cash": cash_t1, "cash_pct": f"{cash_pct:+.2f}%",
                "m3": m3_t1, "m3_pct": f"{m3_pct:+.2f}%", "date": date_t1}
    except Exception as e:
        print(f"  westmetall 오류: {e}")
        return {}


async def _scrape_metalradar_ni3m(page) -> dict:
    result = _fetch_westmetall_ni3m()
    if result:
        return result
    print("  westmetall 실패 → metalradar 시도...")
    try:
        await page.goto(
            "https://metalradar.com/price/nickel/lme/official/3-month/cumulative-volume?includeOrigin=true",
            wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)
        body  = await page.inner_text("body")
        m_ask = re.search(r'Ask\s*\$?([\d,]+\.?\d*)', body)
        if not m_ask:
            return {}
        ask = float(m_ask.group(1).replace(",", ""))
        if not (15_000 < ask < 25_000):
            return {}
        return {"m3": ask, "m3_pct": "N/A", "date": now_kst().strftime("%d. %b %Y")}
    except Exception as e:
        print(f"  metalradar 오류: {e}")
        return {}


def _fetch_lme_nickel_kpi() -> dict:
    try:
        r = requests.get(
            "https://www.kpi.or.kr/www/contents/lme.asp?CFG_CD=con_09",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                     "Accept": "text/html,*/*;q=0.8",
                     "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
            timeout=10)
        r.encoding = "euc-kr"
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.DOTALL):
            cells = [re.sub(r"<[^>]+>", "", c).strip()
                     for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)]
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
                cash, prev = nums[0], nums[1]
                return {"cash": cash, "cash_pct": f"{(cash-prev)/prev*100:+.2f}%",
                        "date": now_kst().strftime("%d. %b %Y")}
    except Exception as e:
        print(f"  LME 니켈 오류(kpi): {e}")
    return {}


async def scrape_smm_prices(usd_cny: float = 7.25) -> dict:
    spot_results, futures_results = [], []
    print("\n[SMM·LME 시세 수집]")

    print("  LME 니켈 수집 중...", end=" ", flush=True)
    wm = _fetch_westmetall_ni3m()
    if wm:
        lme_ni        = {"cash": wm["cash"], "cash_pct": wm["cash_pct"], "date": wm["date"]}
        ni3m_prefetch = wm
        print("OK (westmetall)")
    else:
        lme_ni        = _fetch_lme_nickel_kpi()
        ni3m_prefetch = None
        print("OK (kpi)" if lme_ni else "W 실패")

    CHROMIUM_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    BROWSER_UA    = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

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
                    spot_results.append({
                        "name": "니켈", "name_en": "LME Nickel", "source": "LME",
                        "date": lme_ni["date"], "usd_excl": lme_ni["cash"],
                        "cny_incl": None, "cny_excl": round(lme_ni["cash"] * usd_cny),
                        "usd_metal": None, "cny_metal": None,
                        "metal_content": None, "metal_label": None,
                        "change_pct": lme_ni["cash_pct"], "delayed": True, "status": "OK",
                    })
                else:
                    spot_results.append({"name": "니켈", "name_en": "LME Nickel",
                                         "source": "LME", "status": "ERROR: 수집 실패"})
            await asyncio.sleep(2)

        if ni3m_prefetch:
            ni3m = ni3m_prefetch
        else:
            print("  LME 3M 수집 중...", end=" ", flush=True)
            ni3m = await _scrape_metalradar_ni3m(page)
        if not ni3m:
            print("W 3M 실패")

        for t in FUTURES_EM:
            print(f"  선물: {t['name']}({t['exchange']}) ...", end=" ", flush=True)
            if t.get("method") == "playwright":
                r = await _scrape_lcm_playwright(page, t)
                futures_results.append(r)
                print("OK" if r["status"] == "OK" else f"W {r['status']}")
                try:
                    await asyncio.wait_for(browser.close(), timeout=8.0)
                except Exception:
                    pass
                browser = await p.chromium.launch(headless=True, args=CHROMIUM_ARGS)
                ctx     = await browser.new_context(user_agent=BROWSER_UA, locale="en-US")
                page    = await ctx.new_page()
            elif t.get("method") == "metalradar":
                if ni3m:
                    r = {"name": t["name"], "exchange": "LME", "ticker": "LME·3M",
                         "source": "metalradar.com", "date": ni3m["date"],
                         "latest": round(ni3m["m3"]),
                         "latest_vat_excl": round(ni3m["m3"] * usd_cny),
                         "change_pct": ni3m["m3_pct"], "delayed": True, "status": "OK"}
                    print("OK")
                else:
                    r = {"name": t["name"], "exchange": "LME", "ticker": "LME·3M",
                         "status": "ERROR: 수집 실패"}
                    print("W 실패")
                futures_results.append(r)

        await browser.close()

    return {"spot": spot_results, "futures": futures_results}


def compute_spreads(price_data: dict) -> dict:
    spot_map    = {r["name"]: r for r in price_data["spot"] if r.get("status") == "OK"}
    futures_map = {r["exchange"]: r for r in price_data["futures"] if r.get("status") == "OK"}
    spreads     = {}

    lc_data = futures_map.get("GFEX", {})
    lc_s    = spot_map.get("공업용 탄산리튬", {}).get("cny_excl")
    lc_f    = lc_data.get("latest_vat_excl")
    if lc_s and lc_f:
        diff = lc_s - lc_f
        spreads["탄산리튬"] = {
            "spot": lc_s, "futures": lc_f,
            "ticker": lc_data.get("ticker", "GFEX·LC").split("·")[-1],
            "spread": diff, "spread_pct": diff / lc_f * 100,
            "structure": "백워데이션" if diff > 0 else "콘탱고"}

    ni_f = futures_map.get("LME", {}).get("latest")
    ni_s = spot_map.get("니켈", {}).get("usd_excl")
    if ni_s and ni_f:
        diff = ni_s - ni_f
        spreads["니켈"] = {
            "spot_metal": ni_s, "futures": ni_f, "ticker": "3M",
            "spread": diff, "spread_pct": diff / ni_f * 100,
            "structure": "백워데이션" if diff > 0 else "콘탱고", "unit": "USD"}

    return spreads


def format_price_for_prompt(price_data: dict, usd_cny: float, spreads: dict) -> str:
    lines = [f"수집: {now_kst().strftime('%H:%M')} KST | USD/CNY: {usd_cny:.2f}"]
    lines.append("\n[현물 - 증치세제외 기준]")
    for r in price_data["spot"]:
        if r.get("status") != "OK":
            continue
        ms = ""
        if r.get("usd_metal"):
            ms = f" | {r['metal_label']}금속환산: ${r['usd_metal']:,.0f}"
        lines.append(f"  {r['name']}: ${r['usd_excl']:,.0f}/t{ms}"
                     f" | CNY{r.get('cny_excl') or 0:,.0f} | {r['change_pct']}")

    lines.append("\n[선물 - 증치세제외 환산]")
    for r in price_data["futures"]:
        if r.get("status") != "OK":
            continue
        ve = r.get("latest_vat_excl")
        ue = round(ve / usd_cny) if ve else None
        lines.append(f"  {r['name']}({r.get('ticker','')}): ${ue:,.0f} / CNY{ve:,.0f}"
                     f" | {r['change_pct']}")

    lines.append("\n[현선물 스프레드]")
    if "탄산리튬" in spreads:
        s = spreads["탄산리튬"]
        lines.append(f"  탄산리튬({s['ticker']}): 현물CNY{s['spot']:,.0f} vs 선물CNY{s['futures']:,.0f}"
                     f" -> {s['structure']} ({s['spread']:+,.0f}, {s['spread_pct']:+.1f}%)")
    if "니켈" in spreads:
        s = spreads["니켈"]
        lines.append(f"  니켈LME(3M): Cash${s['spot_metal']:,.0f} vs 3M${s['futures']:,.0f}"
                     f" -> {s['structure']} ({s['spread']:+,.0f}, {s['spread_pct']:+.1f}%) [T-1]")
    return "\n".join(lines)


def append_price_history(price_data: dict, usd_cny: float) -> list:
    """당일 시세를 JSON에 누적하고 전체 이력 반환"""
    os.makedirs(os.path.dirname(PRICE_JSON), exist_ok=True)
    hist = []
    if os.path.exists(PRICE_JSON):
        try:
            with open(PRICE_JSON, encoding="utf-8") as f:
                hist = json.load(f)
        except Exception as e:
            print(f"  시세 이력 읽기 실패({e}) - 새로 시작")

    spot = {r["name"]: r for r in (price_data or {}).get("spot", [])
            if r.get("status") == "OK"}
    fut  = {r["exchange"]: r for r in (price_data or {}).get("futures", [])
            if r.get("status") == "OK"}

    lc_ve = fut.get("GFEX", {}).get("latest_vat_excl")
    row = {
        "date":     now_kst().strftime("%Y-%m-%d"),
        "usd_cny":  round(usd_cny, 4),
        "ni":       spot.get("니켈", {}).get("usd_excl"),
        "ni_3m":    fut.get("LME", {}).get("latest"),
        "co":       spot.get("황산코발트", {}).get("usd_excl"),
        "co_metal": spot.get("황산코발트", {}).get("usd_metal"),
        "li_ind":   spot.get("공업용 탄산리튬", {}).get("usd_excl"),
        "li_bat":   spot.get("배터리용 탄산리튬", {}).get("usd_excl"),
        "lc_fut":   round(lc_ve / usd_cny) if lc_ve else None,
    }

    hist = [h for h in hist if h.get("date") != row["date"]]
    hist.append(row)
    hist.sort(key=lambda x: x["date"])

    with open(PRICE_JSON, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    print(f"  시세 이력 저장: {len(hist)}일치")
    return hist

# ============================================================
# 기사 수집
# ============================================================
_CROSS_LANG_COMPANIES = [
    "sqm", "albemarle", "ganfeng", "tianqi", "pilbara", "liontown",
    "arcadium", "sigma lithium", "glencore", "umicore", "northvolt",
    "catl", "byd", "panasonic", "ascend elements", "redwood materials",
    "cirba", "ecobat", "sungeel", "성일",
]

def _pre_cluster_articles(articles: list) -> list:
    kept = []

    def _key_numbers(title: str) -> set:
        return set(re.findall(r'\d+\.?\d*%|\$[\d,]+[BMK]?|\d{2,}', title))

    for a in articles:
        lang_a  = a.get("lang", "")
        words_a = _sig_words(a["title"])
        nums_a  = _key_numbers(a["title"])
        lt_a    = a["title"].lower()
        len_a   = len(a.get("body", "") or a.get("snippet", ""))

        merged = False
        for i, b in enumerate(kept):
            lt_b    = b["title"].lower()
            words_b = _sig_words(b["title"])
            len_b   = len(b.get("body", "") or b.get("snippet", ""))

            if b.get("lang", "") == lang_a and len(words_a & words_b) >= 5:
                if len_a > len_b:
                    kept[i] = a
                merged = True
                break

            nums_b = _key_numbers(b["title"])
            if nums_a and nums_b and len(nums_a & nums_b) >= 2:
                if any(co in lt_a and co in lt_b for co in _CROSS_LANG_COMPANIES):
                    if len_a > len_b:
                        kept[i] = a
                    merged = True
                    break

        if not merged:
            kept.append(a)

    removed = len(articles) - len(kept)
    if removed > 0:
        print(f"  pre-clustering: {removed}건 통합 → {len(kept)}건")
    return kept


def _parse_feed(url: str, source_fixed: str = None, lang: str = "en",
                is_special: bool = False, cutoff: datetime = None,
                seen: set = None, max_items: int = 40) -> list:
    """RSS 피드 하나를 읽어 기사 리스트 반환"""
    out = []
    try:
        resp = requests.get(url, timeout=20,
                            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if resp.status_code != 200:
            print(f"  [{source_fixed or url[:40]}] HTTP {resp.status_code}")
            return out
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as pe:
            # 일부 매체는 XML이 깨진 채로 옴 → 유효한 <item> 구간만 복구
            raw   = resp.content.decode("utf-8", errors="ignore")
            items = re.findall(r"<item[\s>].*?</item>", raw, re.DOTALL)
            if not items:
                print(f"  [{source_fixed or url[:40]}] XML 파싱 실패: {pe}")
                return out
            patched = "<rss><channel>" + "".join(items) + "</channel></rss>"
            try:
                root = ET.fromstring(patched.encode("utf-8"))
                print(f"  [{source_fixed or url[:40]}] XML 복구 ({len(items)}개 item)")
            except ET.ParseError:
                print(f"  [{source_fixed or url[:40]}] XML 복구 실패")
                return out

        for entry in root.findall(".//item")[:max_items]:
            title = decode_entities((entry.findtext("title") or "").strip())
            link  = extract_real_url((entry.findtext("link") or "").strip())
            if not title or not link or (seen is not None and link in seen):
                continue

            pub_date = parse_date((entry.findtext("pubDate") or "").strip())
            if not pub_date or (cutoff and pub_date < cutoff):
                continue

            snippet = decode_entities(
                re.sub(r'<[^>]+>', '', entry.findtext("description") or ""))[:400]

            if source_fixed:
                source = source_fixed
            else:
                src_el = entry.find("source")
                source = src_el.text.strip() if src_el is not None else ""
                if "metal.com" in link.lower():
                    source = "SMM Metal"

            lt, ls, ll = title.lower(), source.lower(), link.lower()
            combined   = (title + " " + snippet).lower()

            if any(k in lt for k in NOISE_KEYWORDS):              continue
            if any(x in lt and y in lt for x, y in NOISE_PAIRS):  continue
            if is_stock_noise(title):                             continue

            if not is_special:
                if any(s in ls or s in ll for s in NOISE_SOURCES): continue
                if any(p in ll for p in NOISE_URL_PATHS):          continue

            # electrive=EV충전, Energy Storage News=ESS 전문지라
            # 전문지도 화이트리스트를 통과해야 함
            if not any(w in combined for w in WHITELIST):
                continue

            if seen is not None:
                seen.add(link)
            out.append({
                "title": title, "link": link, "source": source,
                "pub": (entry.findtext("pubDate") or "").strip(),
                "pub_date": pub_date, "lang": lang,
                "snippet": snippet, "priority": is_special,
            })
    except Exception as e:
        print(f"  [{source_fixed or url[:40]}] 오류: {e}")
    return out


def collect_rss():
    now        = datetime.utcnow()
    cutoff     = get_cutoff_utc()
    cutoff_kst = cutoff + timedelta(hours=9)
    print(f"  [날짜 필터] {cutoff_kst.strftime('%Y-%m-%d %H:%M')} KST 이후")

    raw, seen = [], set()

    print("\n[전문 매체 수집]")
    for f in PUBLISHER_FEEDS_SPECIAL:
        got = _parse_feed(f["url"], f["source"], f["lang"],
                          is_special=True, cutoff=cutoff, seen=seen)
        print(f"  {f['source']}: {len(got)}건")
        raw += got
        time.sleep(0.2)

    for f in PUBLISHER_FEEDS_GENERAL:
        got = _parse_feed(f["url"], f["source"], f["lang"],
                          is_special=False, cutoff=cutoff, seen=seen)
        print(f"  {f['source']}: {len(got)}건")
        raw += got
        time.sleep(0.2)

    print("\n[구글 뉴스 수집]")
    g_total = 0
    for item in GOOGLE_FEEDS:
        q   = urllib.parse.quote(item["q"] + " when:3d")
        url = (f"https://news.google.com/rss/search?q={q}"
               f"&hl={item['lang']}&gl={item['gl']}&ceid={item['ceid']}"
               f"&num=50&cb={int(now.timestamp())}")
        got = _parse_feed(url, None, item["lang"],
                          is_special=False, cutoff=cutoff, seen=seen, max_items=50)
        g_total += len(got)
        raw += got
        time.sleep(0.15)
    print(f"  구글 뉴스 합계: {g_total}건")

    raw.sort(key=lambda x: x.get("pub_date") or datetime.min, reverse=True)

    company_day_count, deduped = {}, []
    for a in raw:
        words = _sig_words(a["title"])
        if any(len(words & _sig_words(b["title"])) >= 5 for b in deduped):
            continue
        tl      = a["title"].lower()
        pub_day = a["pub_date"].strftime("%Y-%m-%d") if a.get("pub_date") else "unknown"
        is_dup  = False
        for co in ["lg에너지솔루션", "sk온", "삼성sdi", "에코프로비엠", "catl", "byd"]:
            if co in tl:
                k = f"{co}_{pub_day}"
                company_day_count[k] = company_day_count.get(k, 0) + 1
                if company_day_count[k] > 3:
                    is_dup = True
                break
        if not is_dup:
            deduped.append(a)

    smm_direct = _fetch_smm_rss(cutoff=cutoff,
                                existing_titles=[a["title"] for a in deduped])
    for a in smm_direct:
        if not any(a["link"] == x.get("link") for x in deduped):
            deduped.append(a)

    deduped = _pre_cluster_articles(deduped)

    sc = sum(1 for a in deduped if "SMM" in a.get("source", ""))
    pc = sum(1 for a in deduped if a.get("priority"))
    print(f"\n수집: {len(raw)}건 → 최종 {len(deduped)}건 (SMM:{sc} / 전문지:{pc})")
    return deduped

# ============================================================
# 본문 추출
# ============================================================
def fetch_body(real_url):
    try:
        resp = requests.get(f"https://r.jina.ai/{real_url}",
                            timeout=(10, 45), headers={"User-Agent": "Mozilla/5.0"})
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
        await page.wait_for_url(lambda url: "news.google.com" not in url, timeout=10000)
    except Exception:
        pass
    final_url = page.url
    return final_url if "news.google.com" not in final_url else None


TARGET_TOTAL = 80   # 본문 추출 상한 (실제로는 후보 수만큼)
MIN_SCORE    = 6    # 이 점수 미만은 제외

async def enrich_articles(articles):
    for a in articles:
        a["score"] = relevance_score(a)

    # SMM도 점수 기준을 통과해야 함 (알루미늄·철스크랩 등 유입 차단)
    smm = sorted([a for a in articles
                  if "SMM" in a.get("source", "") and a["score"] >= MIN_SCORE + 6],
                 key=lambda x: -x["score"])[:4]

    sk      = ["성일하이텍", "sungeel", "성일"]
    sungeel = [a for a in articles
               if a not in smm and any(k in a["title"].lower() for k in sk)]

    pool = [a for a in articles if a not in smm and a not in sungeel]
    pool = [a for a in pool if a["score"] >= MIN_SCORE]
    pool.sort(key=lambda x: (-x["score"],
                             -(x.get("pub_date") or datetime.min).timestamp()))

    remain  = max(0, TARGET_TOTAL - len(smm) - len(sungeel))
    general = pool[:remain]
    targets = smm + sungeel + general

    print(f"\n본문추출: SMM{len(smm)}+성일{len(sungeel)}+선별{len(general)}"
          f"={len(targets)}건 ({MIN_SCORE}점 이상 후보 {len(pool)}건)")
    if general:
        print(f"  점수 범위: {general[0]['score']} ~ {general[-1]['score']}")

    browser = None
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
            page = await browser.new_page()
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

            ok = sn = 0
            for i, article in enumerate(targets):
                print(f"[{i+1}/{len(targets)}] ({article.get('score', 0):>3}점) "
                      f"{article['title'][:50]}")
                link = article["link"]

                if "news.google.com" not in link:
                    body = fetch_body(link)
                    if body:
                        article["body"] = body; ok += 1
                        print(f"  OK ({len(body)}자)")
                    else:
                        sn += 1; print("  W 스니펫")
                    continue

                real_url = await get_real_url(page, link)
                if real_url:
                    article["real_url"] = real_url
                    body = fetch_body(real_url)
                    article["body"] = body
                    if body:
                        ok += 1; print(f"  OK {real_url[:55]}")
                    else:
                        sn += 1; print("  W 본문없음")
                else:
                    sn += 1; print("  W 리다이렉트 실패")

            print(f"\n본문결과: 성공{ok} / 스니펫{sn}")
        finally:
            if browser:
                await browser.close()

    return targets

# ============================================================
# Gemini 분석
# ============================================================
def analyze(articles, price_data: dict = None, usd_cny: float = 7.25):
    today = now_kst().strftime("%Y년 %m월 %d일")

    smm_articles = [a for a in articles if "SMM" in a.get("source", "")][:3]
    gen_articles = [a for a in articles if "SMM" not in a.get("source", "")]

    def fmt_article(i, a):
        du   = a.get("real_url") or a["link"]
        line = (f"{i+1}. [{a['lang'].upper()}] {a['title']}\n"
                f"   출처:{a.get('source','불명')} | 날짜:{a.get('pub','')} | {du}")
        body = a.get("body", "") or a.get("snippet", "")
        if body:
            line += f"\n   [본문]: {body[:1500]}"
        return line

    smm_sec = "\n\n".join(fmt_article(i, a) for i, a in enumerate(smm_articles))
    gen_sec = "\n\n".join(fmt_article(i, a) for i, a in enumerate(gen_articles))

    if price_data:
        spreads   = compute_spreads(price_data)
        price_sec = f"\n[당일 SMM 시세]\n{format_price_for_prompt(price_data, usd_cny, spreads)}\n"
        price_guide = """
[시사점 4~6개 — 아래 구성 참고]
① 시세 종합 (1개, 필수): 탄산리튬·니켈·코발트 스프레드를 묶어
   원료 매입/제품 판매 전략 시사점. 구체적 수치 인용.
② 기사 기반 (2~4개, 필수): 오늘 뉴스에서 직접 도출.
   공급망/M&A/정책·규제/경쟁사/기술 중 실제 움직임이 있었던 것만.
③ 해외법인 연계 (관련이 실제로 있을 때만): 인디애나/폴란드/헝가리/
   인도/말레이시아/중국 법인과 오늘 뉴스가 직접 연결될 때만 작성.
   억지로 연결하지 말 것. 없으면 ②를 하나 더 쓸 것.
④ 단기 모멘텀 (1개, 필수, 마지막): 향후 1~2주 전망 한 문장.

[금지] 시세 관련 2개 이상. 근거 없는 추측. 매일 반복되는 일반론.
"""
    else:
        price_sec = ""
        price_guide = ""

    prompt = f"""당신은 배터리 재활용 산업 전문 시니어 애널리스트입니다. JSON만 출력하세요.
오늘: {today}
{price_sec}
[SMM Metal 기사 최우선]
{smm_sec if smm_sec else "없음"}

[일반 뉴스]
{gen_sec}

[성일하이텍 사업 맥락 — 선별 기준]
성일하이텍은 한국 최대 리튬이온배터리 재활용 업체로, 블랙매스에서
황산코발트·황산니켈·탄산리튬을 습식제련으로 생산한다.
- 업스트림: SK온·LG에너지솔루션·삼성SDI·CATL·BYD → 폐배터리·스크랩 공급처
- 다운스트림: 에코프로비엠·포스코퓨처엠·엘앤에프 등 양극재·전구체 업체
- 시장 지표: 이차전지·전기차·ESS 시장 → 미래 폐배터리 발생량 결정.
  특히 ESS는 최근 전기차를 능가하는 성장세로, LFP 기반 대형 ESS 확대는
  중장기 원료 발생원이자 셀 공정 스크랩 발생원. 셀 제조사의 ESS 수주·
  증설은 중요. 단, 발전소 EPC·시공·계통연계 등 전력 인프라 사업은 무관.
- 해외법인: 인디애나(미국), 헝가리, 폴란드, 인도, 말레이시아, 중국.
  해당 국가의 배터리·소재 산업 사건은 현지 법인 운영에 직접 영향.
- ★ "재활용"이라는 단어가 없어도 아래는 핵심 기사로 취급할 것:
  · 셀 제조사 공장 가동중단·감산·증설 (스크랩 발생량 변동)
  · 공급망 재편·중국 의존 탈피·소재 내재화 (사업 환경 변화)
  · 원료 장기공급 계약·offtake·지분 인수
  · 성일 해외법인 소재국의 배터리 산업 동향

[필수 선별 규칙]
- 오늘 실제로 중요한 기사만 선택. 8건이면 8건, 40건이면 40건. (최대 40건)
  분야별 균등 배분을 강제하지 말 것. 정책이 많은 날은 정책이 많아도 됨.
  건수를 채우기 위해 관련도 낮은 기사를 넣지 말 것.
- 전문지(Batteries News, Charged EVs, electrive, Energy Storage News,
  SMM, 디일렉, 더구루) 기사를 우선 검토할 것.
- 성일하이텍 관련 기사가 있으면 반드시 포함.
- 배터리 밸류체인과 무관한 기사 제외 (LNG·석유·태양전지·반도체·디스플레이).
- 태그 판별 (반드시 하나만):
  · 원재료 및 시황 — 가격·수급·재고·생산량 변동이 기사의 핵심일 때
  · 정책 및 규제 — 법령·행정조치·수출입 제한·인허가가 핵심.
                   가격이 언급돼도 제도가 주제면 여기
  · 공급망 및 파트너십 — 계약·MOU·JV·공급 개시·수주·턴키
  · 투자 및 M&A — 지분 인수·자금 조달·펀딩·증설 투자 결정
  · 기술 및 공정 — 신공법·수율·설비·소재 개발
  ※ 수주·계약은 M&A가 아니라 공급망. 자금 조달은 정책이 아니라 투자.
  ※ 시장 통계·판매 실적은 정책이 아님. 해당 없으면 선별에서 제외.
- 금지: 증권리포트/주가/IR공시/유상증자/ETF/신차리뷰/PR배포/스마트폰
- 금지: 본문에 언급된 발표일이 14일 이상 지난 기사

★ [유사 기사 통합]
- 동일 이슈가 2건 이상이면 가장 정보가 풍부한 1건만.
  summary에 "○○·△△ 등 복수 보도"로 통합 언급.
- 한국어판과 영어판은 관점이 다르면 각 1건 허용.

[요약기준] 3문장 이내. 기관명·기업명·금액·수치·날짜 필수. 추상적 요약 금지.
계획≠실행, MOU≠계약, 검토≠확정.

[트렌드 2~3개] 오늘 기사에서 실제로 흐름이 보인 것만.
억지로 3개를 채우지 말 것. 기사 수치·정책명 직접 인용.
배터리 재활용·원료 공급망과 무관한 주제(발전소 EPC·시공, 충전 인프라,
신차 출시, 수소, 태양광)는 트렌드로 쓰지 말 것.
단, ESS·전기차 시장 규모와 셀 수주·증설은 향후 폐배터리 발생량을
결정하므로 중요한 트렌드로 다룰 것.
{price_guide}

JSON:
{{"articles":[{{"title":"","source":"","date":"","link":"","summary":"3문장이내 수치포함","tag":"원재료 및 시황|투자 및 M&A|정책 및 규제|공급망 및 파트너십|기술 및 공정","region":"한국|중국|미국|EU|일본|인도네시아|글로벌"}}],"trends":[{{"title":"","body":"2~3문장"}}],"insights":[""]}}
articles 최대 40건. trends 2~3개. insights 4~6개. 모든 텍스트 한국어."""

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
# 웹 페이지 생성
# ============================================================
TAG_ORDER = ["원재료 및 시황", "공급망 및 파트너십", "투자 및 M&A",
             "정책 및 규제", "기술 및 공정"]

_WEB_CSS = """
  body { margin:0;background:#f8fafc;font-family:'Apple SD Gothic Neo',
         'Malgun Gothic',Arial,sans-serif;color:#0f2744;-webkit-text-size-adjust:100%; }
  .wrap { max-width:760px;margin:0 auto;padding:0 16px 60px; }
  details summary::-webkit-details-marker { display:none; }
  details summary { list-style:none; }
  details[open] summary { color:#64748b; }
  a:hover { text-decoration:underline !important; }
  h2.sec { font-size:16px;margin:34px 0 10px;font-weight:700; }
  @media (max-width:600px) { .wrap { padding:0 12px 40px; } }
"""

_WEATHER_JS = """
const spots = __SPOTS__;
const CODE = {0:"맑음",1:"대체로 맑음",2:"구름 조금",3:"흐림",
  45:"안개",48:"안개",51:"이슬비",53:"이슬비",55:"이슬비",
  56:"어는 이슬비",57:"어는 이슬비",61:"약한 비",63:"비",65:"강한 비",
  66:"어는 비",67:"어는 비",71:"약한 눈",73:"눈",75:"강한 눈",77:"싸락눈",
  80:"소나기",81:"소나기",82:"강한 소나기",85:"눈소나기",86:"눈소나기",
  95:"뇌우",96:"뇌우",99:"뇌우"};
Promise.all(spots.map(s =>
  fetch("https://api.open-meteo.com/v1/forecast?latitude=" + s.lat
      + "&longitude=" + s.lon
      + "&current=temperature_2m,weather_code"
      + "&daily=temperature_2m_max,temperature_2m_min"
      + "&timezone=Asia%2FSeoul&forecast_days=1")
    .then(r => r.json())
    .then(d => {
      const c = d.current, dy = d.daily;
      return '<span><b style="color:#fff;">' + s.name + '</b> '
           + (CODE[c.weather_code] || "") + " "
           + Math.round(c.temperature_2m) + "\\u00B0 "
           + '<span style="color:#94a3b8;">'
           + Math.round(dy.temperature_2m_min[0]) + "/"
           + Math.round(dy.temperature_2m_max[0]) + "\\u00B0</span></span>";
    })
    .catch(() => '<span>' + s.name + ' —</span>')
)).then(h => { document.getElementById('wx').innerHTML = h.join(''); });
"""

_CHART_JS = """
(function() {
  const D = __CD__;
  const solid = D.labels.length > 20 ? 0 : 3;

  const ds = (label, data, color, dash) => ({
    label, data, borderColor: color, backgroundColor: color,
    borderDash: dash ? [5, 4] : [],
    tension: .25, borderWidth: 2, pointRadius: solid, spanGaps: false
  });

  const opts = () => ({
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { boxWidth: 12, font: { size: 11 } } },
      tooltip: { callbacks: { label: c => c.dataset.label + ': '
        + (c.parsed.y == null ? '—' : '$' + c.parsed.y.toLocaleString()) } }
    },
    scales: {
      y: { ticks: { font: { size: 10 },
           callback: v => '$' + (v/1000).toFixed(0) + 'k' } },
      x: { ticks: { maxRotation: 0, autoSkipPadding: 20, font: { size: 10 } } }
    }
  });

  const draw = (id, sets) => {
    const el = document.getElementById(id);
    if (!el) return;
    new Chart(el, { type:'line', data:{ labels: D.labels, datasets: sets }, options: opts() });
  };

  draw('ch_ni', [
    ds('현물 (Cash)', D.ni,    '#1d4ed8', false),
    ds('선물 (3M)',   D.ni_3m, '#93c5fd', true)
  ]);
  draw('ch_co', [
    ds('황산코발트',  D.co,       '#b45309', false),
    ds('Co 금속환산', D.co_metal, '#fbbf24', true)
  ]);
  draw('ch_li', [
    ds('현물 BG',   D.li_bat, '#059669', false),
    ds('현물 TG',   D.li_ind, '#6ee7b7', false),
    ds('GFEX 선물', D.lc_fut, '#94a3b8', true)
  ]);
})();
"""

_CSV_JS = """
function dlCsv() {
  const H = ['날짜','LME니켈현물','LME니켈3M','황산코발트','Co금속환산',
             'TG탄산리튬','BG탄산리튬','GFEX선물','USD/CNY'];
  const K = ['date','ni','ni_3m','co','co_metal','li_ind','li_bat','lc_fut','usd_cny'];
  fetch('__DATA__').then(r => r.json()).then(rows => {
    const csv = '\\uFEFF' + [H.join(',')]
      .concat(rows.map(r => K.map(k => (r[k] == null ? '' : r[k])).join(','))).join('\\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
    a.download = 'brdb_prices.csv';
    a.click();
  }).catch(() => alert('시세 데이터를 불러오지 못했습니다.'));
}
"""


def build_price_web(price_data: dict, usd_cny: float, hist: list,
                    data_path: str = "data/prices.json") -> str:
    if not price_data:
        return ""

    today   = now_kst().strftime("%Y.%m.%d")
    spreads = compute_spreads(price_data)

    badges = ""
    for k, label in [("탄산리튬", "LC"), ("니켈", "Ni")]:
        if k in spreads:
            s   = spreads[k]
            clr = "#c0392b" if s["spread"] > 0 else "#2563eb"
            badges += (f'<span style="background:{clr};color:#fff;font-size:11px;'
                       f'font-weight:700;padding:4px 10px;border-radius:4px;'
                       f'margin-right:8px;">{label} {s["structure"]} '
                       f'{s["spread_pct"]:+.1f}%</span>')

    def row(label, sub, usd, cny, pct, tag=""):
        color = _pct_color(pct)
        return f"""
        <tr>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;">
            <b style="font-size:13px;">{esc(label)}</b>{tag}<br>
            <span style="font-size:11px;color:#8f9ba8;">{esc(sub)}</span></td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:right;">
            <b style="font-size:13px;">{usd}</b><br>
            <span style="color:#aaa;font-size:11px;">{cny}</span></td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;
                     text-align:center;font-weight:700;font-size:13px;color:{color};">
            {pct or '—'}</td>
        </tr>"""

    FAIL_TAG = (' <span style="background:#fee2e2;color:#b91c1c;font-size:9px;'
                'padding:1px 5px;border-radius:3px;">수집실패</span>')
    T1_TAG   = (' <span style="background:#fef3c7;color:#92400e;font-size:9px;'
                'font-weight:700;padding:1px 5px;border-radius:3px;">T-1</span>')

    rows = ""
    for r in price_data.get("spot", []):
        if r.get("status") != "OK":
            rows += row(r.get("name", ""), r.get("name_en", ""), "—", "", "N/A", FAIL_TAG)
            continue
        tag   = T1_TAG if r.get("delayed") else ""
        extra = f" · {r['metal_label']} 환산 ${r['usd_metal']:,.0f}" if r.get("usd_metal") else ""
        rows += row(
            r["name"].replace("배터리용 ", "BG ").replace("공업용 ", "TG "),
            (r.get("name_en") or "") + extra,
            _fmt(r.get("usd_excl"), "$"), _fmt(r.get("cny_excl"), "CNY"),
            r.get("change_pct"), tag)

    rows += ('<tr><td colspan="3" style="padding:8px 14px;background:#f1f5f9;'
             'font-size:11px;font-weight:700;color:#64748b;text-align:center;">'
             f'선물 · USD/CNY {usd_cny:.2f}</td></tr>')

    for r in price_data.get("futures", []):
        if r.get("status") != "OK":
            rows += row(r.get("name", ""), r.get("ticker", ""), "—", "", "N/A", FAIL_TAG)
            continue
        if r.get("exchange") == "LME":
            usd, cny = r.get("latest"), r.get("latest_vat_excl")
        else:
            cny = r.get("latest_vat_excl")
            usd = round(cny / usd_cny) if cny else None
        rows += row(r["name"].replace(" 선물", ""), r.get("ticker", ""),
                    _fmt(usd, "$"), _fmt(cny, "CNY"), r.get("change_pct"),
                    T1_TAG if r.get("delayed") else "")

    # --- 차트 ---
    recent = hist[-30:] if hist else []
    n_days = len(recent)
    CD = {
        "labels":   [h["date"][5:]     for h in recent],
        "ni":       [h.get("ni")       for h in recent],
        "ni_3m":    [h.get("ni_3m")    for h in recent],
        "co":       [h.get("co")       for h in recent],
        "co_metal": [h.get("co_metal") for h in recent],
        "li_ind":   [h.get("li_ind")   for h in recent],
        "li_bat":   [h.get("li_bat")   for h in recent],
        "lc_fut":   [h.get("lc_fut")   for h in recent],
    }

    def canvas(cid, title, sub):
        return f"""
      <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;
                  padding:16px 18px;margin-bottom:14px;">
        <div style="font-size:13px;font-weight:700;">{title}</div>
        <div style="font-size:11px;color:#94a3b8;margin-bottom:10px;">{sub}</div>
        <div style="position:relative;height:230px;"><canvas id="{cid}"></canvas></div>
      </div>"""

    note = ("데이터가 하루치입니다. 며칠 누적되면 추세가 보입니다."
            if n_days < 3 else f"최근 {n_days}일 · 실선 현물 / 점선 선물")

    chart_block = f"""
      <div style="font-size:13px;font-weight:700;margin:24px 0 4px;">시세 추이</div>
      <div style="font-size:11px;color:#94a3b8;margin-bottom:12px;">{note}</div>
      {canvas("ch_ni", "니켈",   "LME Cash · 3M 선물")}
      {canvas("ch_co", "코발트", "SMM 황산코발트 · Co 금속환산")}
      {canvas("ch_li", "리튬",   "SMM 공업용(TG) · 배터리용(BG) · GFEX 선물")}
      <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
      <script>{_CHART_JS.replace("__CD__", json.dumps(CD, ensure_ascii=False))}</script>"""

    return f"""
  <h2 class="sec">SMM · LME 배터리 소재 시세</h2>
  <div style="display:flex;justify-content:space-between;align-items:center;
              flex-wrap:wrap;gap:8px;margin-bottom:10px;">
    <span style="font-size:12px;color:#64748b;">
      {today} · SMM 증치세 제외 · LME T-1 전일결산</span>
    <button onclick="dlCsv()" style="font-size:11px;padding:5px 12px;
            border:1px solid #cbd5e1;border-radius:5px;background:#fff;
            cursor:pointer;color:#475569;">CSV 받기</button>
  </div>
  <div style="margin-bottom:12px;">{badges or '&nbsp;'}</div>
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#fff;border:1px solid #e2e8f0;border-collapse:collapse;">
    <thead><tr style="background:#f8fafc;">
      <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#475569;
                 border-bottom:2px solid #e2e8f0;">품목</td>
      <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#475569;
                 text-align:right;border-bottom:2px solid #e2e8f0;">USD/t · CNY/t</td>
      <td style="padding:10px 14px;font-size:11px;font-weight:700;color:#475569;
                 text-align:center;border-bottom:2px solid #e2e8f0;">등락</td>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  {chart_block}
  <script>{_CSV_JS.replace("__DATA__", data_path)}</script>"""


def build_web(data, price_data=None, usd_cny=7.25, hist=None, in_archive=False):
    today        = now_kst().strftime("%Y년 %m월 %d일")
    archive_href = "index.html" if in_archive else "archive/index.html"
    data_path    = "../data/prices.json" if in_archive else "data/prices.json"
    price_web    = build_price_web(price_data, usd_cny, hist or [], data_path)

    by_tag = {}
    for a in data.get("articles", []):
        by_tag.setdefault(a.get("tag", "기타"), []).append(a)

    def card(a, compact=False):
        url = esc(a.get("real_url") or a.get("link", ""))
        pad = "16px 18px" if compact else "20px"
        fs  = "15px" if compact else "16px"
        summary = (
            f'<p style="font-size:14px;color:#475569;line-height:1.65;margin:8px 0 0;">'
            f'{esc(a.get("summary",""))}</p>')
        return f"""
        <div style="border:1px solid #e2e8f0;border-radius:8px;
                    padding:{pad};margin-bottom:10px;background:#fff;">
          <div style="font-size:11px;color:#94a3b8;margin-bottom:6px;">
            <span style="background:#dcfce7;color:#15803d;padding:2px 8px;
                         border-radius:4px;font-weight:700;">{esc(a.get('region',''))}</span>
            &nbsp;{esc(a.get('source',''))} · {esc(a.get('date',''))}</div>
          <a href="{url}" target="_blank" rel="noopener"
             style="font-size:{fs};font-weight:700;color:#0f2744;
                    text-decoration:none;line-height:1.4;">{esc(a.get('title',''))}</a>
          {summary}
        </div>"""

    sections = ""
    for tag in TAG_ORDER:
        arts = by_tag.get(tag)
        if not arts:
            continue
        head, rest = arts[:3], arts[3:]
        rest_html = ""
        if rest:
            rest_html = f"""
            <details style="margin-top:4px;">
              <summary style="cursor:pointer;font-size:13px;color:#2563eb;
                              font-weight:600;padding:8px 0;">
                ▽ 나머지 {len(rest)}건 보기</summary>
              <div style="margin-top:10px;">{''.join(card(a, True) for a in rest)}</div>
            </details>"""
        sections += f"""
        <h3 style="font-size:15px;font-weight:700;color:#334155;
                   border-left:3px solid #2563eb;padding-left:10px;margin:26px 0 12px;">
          {esc(tag)} <span style="color:#94a3b8;font-weight:400;">({len(arts)})</span></h3>
        {''.join(card(a) for a in head)}{rest_html}"""

    trends = ""
    for i, t in enumerate(data.get("trends", [])):
        trends += f"""
        <div style="border-left:4px solid #2563eb;background:#fff;padding:16px 18px;
                    margin-bottom:12px;border-radius:0 6px 6px 0;">
          <div style="font-size:11px;font-weight:800;color:#2563eb;">TREND 0{i+1}</div>
          <div style="font-size:15px;font-weight:700;color:#0f2744;margin:6px 0 8px;">
            {esc(t.get('title',''))}</div>
          <div style="font-size:14px;color:#475569;line-height:1.65;">
            {esc(t.get('body',''))}</div>
        </div>"""

    insights = ""
    for ins in data.get("insights", []):
        insights += f"""
        <tr>
          <td valign="top" style="width:22px;color:#d97706;font-size:15px;
                                  line-height:1.7;padding-top:2px;">&#9658;</td>
          <td style="font-size:14px;color:#451a03;line-height:1.7;
                     padding-bottom:14px;">{esc(ins)}</td>
        </tr>"""

    weather_js = _WEATHER_JS.replace("__SPOTS__",
                                     json.dumps(WEATHER_SPOTS, ensure_ascii=False))

    return f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Battery Recycling Daily Brief — {today}</title>
<style>{_WEB_CSS}</style></head><body>

<div style="background:#0f2744;color:#fff;padding:26px 0;">
  <div class="wrap">
    <div style="font-size:20px;font-weight:700;letter-spacing:.5px;">
      BATTERY RECYCLING DAILY BRIEF</div>
    <div style="color:#94a3b8;font-size:13px;margin-top:6px;">{today}</div>
    <div id="wx" style="margin-top:14px;display:flex;gap:18px;flex-wrap:wrap;
                        font-size:13px;color:#cbd5e1;">불러오는 중…</div>
    <div style="margin-top:12px;">
      <a href="{archive_href}" style="font-size:12px;color:#93c5fd;
         text-decoration:none;">지난 브리핑 보기 &rarr;</a></div>
  </div>
</div>

<div class="wrap">
  {price_web}

  <h2 class="sec">분야별 기사</h2>
  <div style="font-size:12px;color:#94a3b8;margin-bottom:8px;">
    분야별 상위 3건 표시 · 4번째부터는 펼쳐서 확인</div>
  {sections or '<p style="color:#94a3b8;font-size:13px;">기사 없음</p>'}

  <h2 class="sec">오늘의 산업 흐름</h2>
  {trends}

  <h2 class="sec">재활용 사업자 관점 시사점</h2>
  <div style="background:#fefce8;border:1px solid #fde047;
              border-radius:8px;padding:20px 22px;">
    <table width="100%" cellpadding="0" cellspacing="0">{insights}</table>
  </div>

  <div style="margin-top:44px;padding-top:18px;border-top:1px solid #e2e8f0;
              font-size:12px;color:#94a3b8;line-height:1.6;">
    Battery Recycling Daily Brief · {today}<br>
    &copy; Ben Seo · Sales &amp; Marketing Division / SungEel HiTech
  </div>
</div>

<script>{weather_js}</script>
</body></html>"""


def build_archive_index():
    files = sorted(glob.glob("docs/archive/*.html"), reverse=True)
    dates = [os.path.basename(f)[:-5] for f in files
             if os.path.basename(f) != "index.html"]

    by_month = {}
    for d in dates:
        by_month.setdefault(d[:7], []).append(d)

    body = ""
    for month in sorted(by_month, reverse=True):
        links = "".join(
            f'<a href="{d}.html" style="display:inline-block;padding:7px 12px;'
            f'margin:0 6px 6px 0;background:#fff;border:1px solid #e2e8f0;'
            f'border-radius:6px;font-size:13px;color:#0f2744;'
            f'text-decoration:none;">{d[8:]}일</a>'
            for d in sorted(by_month[month], reverse=True))
        body += (f'<h3 style="font-size:14px;color:#334155;margin:26px 0 10px;">'
                 f'{month[:4]}년 {int(month[5:])}월</h3><div>{links}</div>')

    html = f"""<!DOCTYPE html><html lang="ko"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Daily Brief 아카이브</title>
</head><body style="margin:0;background:#f8fafc;font-family:'Apple SD Gothic Neo',
'Malgun Gothic',Arial,sans-serif;color:#0f2744;">
<div style="background:#0f2744;color:#fff;padding:24px 0;">
  <div style="max-width:760px;margin:0 auto;padding:0 16px;">
    <div style="font-size:18px;font-weight:700;">DAILY BRIEF 아카이브</div>
    <div style="color:#94a3b8;font-size:12px;margin-top:5px;">총 {len(dates)}건</div>
  </div></div>
<div style="max-width:760px;margin:0 auto;padding:10px 16px 60px;">
  <a href="../index.html" style="display:inline-block;margin:18px 0 6px;
     font-size:13px;color:#2563eb;text-decoration:none;">← 오늘 브리핑</a>
  {body or '<p style="color:#94a3b8;font-size:13px;">아직 없습니다.</p>'}
</div></body></html>"""

    with open("docs/archive/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  아카이브 인덱스: {len(dates)}건")

# ============================================================
# 이메일 (시세 + 시사점 + 웹 링크)
# ============================================================
def _source_badge(source: str) -> str:
    colors = {"LME": ("#dbeafe", "#1d4ed8"), "SMM": ("#f0fdf4", "#15803d")}
    bg, fg = colors.get(source, ("#f1f5f9", "#64748b"))
    return (f'<span style="display:inline-block;background:{bg};color:{fg};'
            f'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
            f'margin-left:4px;vertical-align:middle;">{source}</span>')


def build_price_section(price_data: dict, usd_cny: float) -> str:
    today   = now_kst().strftime("%Y.%m.%d")
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
                f'{label} {s["structure"]} {s["spread_pct"]:+.1f}%</span>')

    def trow(label, sub, badges, price_cell, extra_cell, pct):
        return f"""
        <tr>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;font-family:'Malgun Gothic',Arial,sans-serif;">
            <b style="font-size:13px;color:#0f2744;">{esc(label)}</b>{badges}<br>
            <span style="font-size:11px;color:#8f9ba8;">{esc(sub)}</span></td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:right;font-family:'Malgun Gothic',Arial,sans-serif;">{price_cell}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:right;font-family:'Malgun Gothic',Arial,sans-serif;">{extra_cell}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #e8edf2;text-align:center;font-weight:700;font-size:13px;color:{_pct_color(pct)};font-family:'Malgun Gothic',Arial,sans-serif;">{pct or '—'}</td>
        </tr>"""

    spot_rows = ""
    for r in price_data["spot"]:
        ok   = r.get("status") == "OK"
        name = r.get("name", "")
        src  = r.get("source", "SMM")
        pct  = r.get("change_pct", "N/A") if ok else "N/A"

        badges = _source_badge(src)
        if r.get("delayed"):
            badges += ('<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                       'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                       'margin-left:3px;vertical-align:middle;">T-1</span>')
        if not ok:
            badges += ('<span style="display:inline-block;background:#fee2e2;color:#b91c1c;'
                       'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                       'margin-left:3px;vertical-align:middle;">수집실패</span>')

        if ok:
            price_cell = (f'<b style="font-size:13px;">{_fmt(r.get("usd_excl"), "$")}</b>'
                          f'<br><span style="color:#aaaaaa;font-size:11px;">'
                          f'{_fmt(r.get("cny_excl"), "CNY")}</span>')
        else:
            price_cell = '<span style="color:#aaaaaa;">—</span>'

        if ok and r.get("usd_metal"):
            extra_cell = (f'<b style="font-size:12px;">{_fmt(r.get("usd_metal"), "$")}</b>'
                          f'<br><span style="color:#aaaaaa;font-size:10px;">'
                          f'{r.get("metal_label")} 금속환산</span>')
        elif ok and src == "LME":
            extra_cell = '<span style="color:#94a3b8;font-size:11px;">직접 금속가</span>'
        else:
            extra_cell = '<span style="color:#d1d5db;">—</span>'

        spot_rows += trow(
            name.replace("배터리용 ", "BG ").replace("공업용 ", "TG "),
            r.get("name_en", ""), badges, price_cell, extra_cell, pct)

    fut_rows = ""
    for r in price_data["futures"]:
        ok  = r.get("status") == "OK"
        pct = r.get("change_pct", "N/A") if ok else "N/A"
        badges = ""
        if r.get("delayed"):
            badges = ('<span style="display:inline-block;background:#fef3c7;color:#92400e;'
                      'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                      'margin-left:4px;vertical-align:middle;">T-1</span>')
        if not ok:
            badges += ('<span style="display:inline-block;background:#fee2e2;color:#b91c1c;'
                       'font-size:9px;font-weight:700;padding:1px 5px;border-radius:3px;'
                       'margin-left:3px;vertical-align:middle;">수집실패</span>')

        if ok:
            if r.get("exchange") == "LME":
                usd, cny = r.get("latest"), r.get("latest_vat_excl")
            else:
                cny = r.get("latest_vat_excl")
                usd = round(cny / usd_cny) if cny else None
            price_f = (f'<b style="font-size:13px;">{_fmt(usd, "$")}</b>'
                       f'<br><span style="color:#aaaaaa;font-size:11px;">'
                       f'{_fmt(cny, "CNY")}</span>')
            if r.get("exchange") == "LME":
                ref = '<span style="font-size:11px;color:#94a3b8;">LME Official</span>'
            else:
                ref = (f'<span style="font-size:10px;color:#aaaaaa;">고시가(VAT포함)</span><br>'
                       f'<b style="font-size:12px;color:#555;">{_fmt(r.get("latest"), "CNY")}</b>')
        else:
            price_f = '<span style="color:#aaaaaa;">—</span>'
            ref     = '<span style="color:#d1d5db;">—</span>'

        fut_rows += trow(r.get("name", "").replace(" 선물", ""),
                         r.get("ticker", ""), badges, price_f, ref, pct)

    return f"""
  <tr>
    <td bgcolor="#1e293b" style="background:#1e293b;color:#ffffff;font-size:13px;
        font-weight:700;letter-spacing:0.5px;padding:12px 30px;
        font-family:'Malgun Gothic',Arial,sans-serif;">
      SMM · LME 배터리 소재 시세</td>
  </tr>
  <tr>
    <td bgcolor="#ffffff" style="background:#ffffff;padding:20px 6px 16px;">
      <p style="margin:0 0 4px;font-size:12px;color:#64748b;padding:0 8px;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        {today} · SMM 증치세제외 기준 · LME T-1 전일결산가</p>
      <p style="margin:0 0 14px;padding:0 8px;">{spread_badges or '&nbsp;'}</p>
      <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff"
             style="font-size:13px;background:#ffffff;border:1px solid #e2e8f0;border-collapse:collapse;">
        <thead><tr bgcolor="#f8fafc" style="background:#f8fafc;">
          <td style="padding:10px 14px;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">현물 · 품목</td>
          <td style="padding:10px 14px;text-align:right;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">USD/t<br><span style="font-weight:400;font-size:10px;color:#94a3b8;">CNY/t</span></td>
          <td style="padding:10px 14px;text-align:right;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">추가정보</td>
          <td style="padding:10px 14px;text-align:center;font-size:11px;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0;font-family:'Malgun Gothic',Arial,sans-serif;">등락</td>
        </tr></thead>
        <tbody>
          {spot_rows}
          <tr><td colspan="4" bgcolor="#f1f5f9" style="padding:8px 14px;background:#f1f5f9;
              font-size:11px;font-weight:700;color:#64748b;text-align:center;
              font-family:'Malgun Gothic',Arial,sans-serif;">
            선물 &nbsp;|&nbsp; USD/CNY {usd_cny:.2f} &nbsp;|&nbsp; GFEX 증치세제외</td></tr>
          {fut_rows}
        </tbody>
      </table>
      <p style="margin:10px 8px 0;color:#94a3b8;font-size:11px;text-align:right;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        Co·Li 현물 <b>SMM</b> · Ni <b>LME</b> via Westmetall (T-1) · LC 선물 <b>GFEX</b></p>
    </td>
  </tr>"""


def build_email(data, price_data=None, usd_cny=7.25, web_url=""):
    today = now_kst().strftime("%Y년 %m월 %d일")

    insights_html = ""
    ins_list = data.get("insights", [])
    for i, ins in enumerate(ins_list):
        bb      = "border-bottom:1px dashed #fde047;" if i < len(ins_list) - 1 else ""
        pad_top = "padding-top:16px;" if i > 0 else ""
        pad_bot = "padding-bottom:16px;" if i < len(ins_list) - 1 else ""
        insights_html += f"""
        <tr>
          <td valign="top" style="width:20px;color:#d97706;font-size:16px;line-height:1.6;
              {pad_top}font-family:'Malgun Gothic',Arial,sans-serif;">&#9658;</td>
          <td style="{bb}{pad_top}{pad_bot}font-size:14px;color:#451a03;line-height:1.6;
              font-family:'Malgun Gothic',Arial,sans-serif;">{esc(ins)}</td>
        </tr>"""

    n_art      = len(data.get("articles", []))
    price_rows = build_price_section(price_data, usd_cny) if price_data else ""

    link_row = f"""
  <tr>
    <td bgcolor="#ffffff" style="background:#ffffff;padding:26px 30px;text-align:center;">
      <table cellpadding="0" cellspacing="0" border="0" align="center">
        <tr><td bgcolor="#1d4ed8" style="border-radius:6px;">
          <a href="{web_url}" style="display:inline-block;padding:14px 30px;font-size:14px;
             font-weight:700;color:#ffffff;text-decoration:none;
             font-family:'Malgun Gothic',Arial,sans-serif;">
            분야별 기사 {n_art}건 · 산업 흐름 · 시세 차트 &rarr;</a>
        </td></tr>
      </table>
      <p style="margin:12px 0 0;font-size:12px;color:#94a3b8;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        분야별 상위 3건 + 펼쳐보기 · 30일 시세 추이</p>
    </td>
  </tr>"""

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
</style>
</head>
<body style="margin:0;padding:20px;background-color:#f8fafc;">
<!--[if mso]><table align="center" width="680" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
<table align="center" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="max-width:680px;margin:0 auto;background-color:#ffffff;
              border:1px solid #e2e8f0;border-collapse:collapse;">
  <tr>
    <td bgcolor="#0f2744" style="background-color:#0f2744;padding:36px 30px;">
      <h1 style="color:#ffffff;font-size:23px;font-weight:700;margin:0 0 10px 0;
                 letter-spacing:0.5px;font-family:'Malgun Gothic',Arial,sans-serif;">
        BATTERY RECYCLING DAILY BRIEF</h1>
      <p style="color:#94a3b8;font-size:14px;margin:0;
                font-family:'Malgun Gothic',Arial,sans-serif;">{today}</p>
    </td>
  </tr>

  {price_rows}

  <tr>
    <td bgcolor="#1e293b" style="background:#1e293b;color:#ffffff;font-size:13px;
        font-weight:700;letter-spacing:0.5px;padding:12px 30px;
        font-family:'Malgun Gothic',Arial,sans-serif;">
      재활용 사업자 관점 시사점</td>
  </tr>
  <tr>
    <td bgcolor="#ffffff" style="background:#ffffff;padding:26px 30px 6px;">
      <table width="100%" cellpadding="22" cellspacing="0" border="0" bgcolor="#fefce8"
             style="background-color:#fefce8;border:1px solid #fde047;
                    border-radius:8px;border-collapse:collapse;">
        <tr><td>
          <table width="100%" cellpadding="0" cellspacing="0" border="0"
                 style="border-collapse:collapse;">{insights_html}</table>
        </td></tr>
      </table>
    </td>
  </tr>

  {link_row}

  <tr>
    <td bgcolor="#0f2744" style="background-color:#0f2744;padding:26px 30px;text-align:center;">
      <p style="color:#94a3b8;font-size:13px;margin:0 0 8px 0;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        Battery Recycling Daily Brief &nbsp;|&nbsp; {today}</p>
      <p style="color:#64748b;font-size:12px;margin:0;
                font-family:'Malgun Gothic',Arial,sans-serif;">
        &copy; Ben Seo, Sales &amp; Marketing Division / SungEel HiTech</p>
    </td>
  </tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</body></html>"""

# ============================================================
# Gmail 발송
# ============================================================
def send_email(html_body):
    today = now_kst().strftime("%Y년 %m월 %d일")
    msg   = MIMEMultipart("alternative")
    msg["Subject"] = f"[배터리 산업 Daily Brief] {today}"
    msg["From"]    = GMAIL_USER
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        bcc = [a.strip() for a in BCC_EMAIL.split(',') if a.strip()] if BCC_EMAIL else []
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

    from collections import Counter
    arts = data.get("articles", [])
    print(f"\n[선별 결과] {len(arts)}건")
    for t, n in Counter(a.get("tag", "?") for a in arts).most_common():
        print(f"  {t}: {n}건")
    for a in arts:
        print(f"  [{a.get('tag','?')[:8]:<8}] {a.get('title','')[:50]}")
    print(f"[트렌드] {len(data.get('trends', []))}개  "
          f"[시사점] {len(data.get('insights', []))}개")

    hist = append_price_history(price_data, usd_cny)

    os.makedirs("docs/archive", exist_ok=True)
    open("docs/.nojekyll", "w").close()   # Jekyll 처리 건너뛰기
    stamp = now_kst().strftime("%Y-%m-%d")

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_web(data, price_data, usd_cny, hist, in_archive=False))
    with open(f"docs/archive/{stamp}.html", "w", encoding="utf-8") as f:
        f.write(build_web(data, price_data, usd_cny, hist, in_archive=True))
    build_archive_index()
    print(f"웹 저장 완료: docs/index.html, docs/archive/{stamp}.html")

    web_url = f"{WEB_BASE}/archive/{stamp}.html"
    send_email(build_email(data, price_data=price_data,
                           usd_cny=usd_cny, web_url=web_url))
    print("=== 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
