"""
GitHub Actions에서 실행 → 각 URL 접근 가능 여부 + 가격 파싱 테스트
"""
import requests, re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def test(name, url, price_pattern=None, referer=None):
    headers = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"}
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"\n{'='*50}")
        print(f"[{name}]")
        print(f"  Status : {r.status_code}")
        print(f"  앞200자: {r.text[:200].replace(chr(10), ' ')}")
        if price_pattern and r.status_code == 200:
            m = re.search(price_pattern, r.text)
            print(f"  가격파싱: {m.group(0) if m else '❌ 패턴 매칭 실패'}")
    except Exception as e:
        print(f"\n[{name}] ❌ 오류: {e}")

# ── 테스트 대상 ──────────────────────────────────────────
test(
    "한국물가정보 LME",
    "https://www.kpi.or.kr/www/contents/lme.asp?CFG_CD=con_09",
    price_pattern=r'1[6-9]\s*[,.]?\s*\d{3}'
)

test(
    "nonferrous.or.kr LME 시세",
    "https://www.nonferrous.or.kr/stats/?act=sub3",
    price_pattern=r'1[6-9]\s*[,.]?\s*\d{3}'
)

test(
    "biggo.com LME_NI",
    "https://finance.biggo.com/quote/LME_NI",
    price_pattern=r'Previous Close.*?(\d{2},\d{3})'
)

test(
    "tradingeconomics.com nickel",
    "https://tradingeconomics.com/commodity/nickel",
    price_pattern=r'Nickel (?:fell|rose|traded).*?(\d{2},\d{3}) USD'
)

test(
    "westmetall.com (참고: 현재 차단됨)",
    "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Ni_cash",
    price_pattern=r'1[6-9]\.\s*\w+\s*202\d.*?\|\s*([\d,]+\.?\d*)'
)

print("\n\n=== 완료 ===")
