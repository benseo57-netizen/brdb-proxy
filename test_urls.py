"""
상세 파싱 테스트 - kpi.or.kr / tradingeconomics / westmetall
"""
import requests, re

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HDR = {"User-Agent": UA, "Accept": "text/html,*/*;q=0.8", "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}

# ── 1. kpi.or.kr ─────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("[1] kpi.or.kr 상세 분석")
try:
    r = requests.get("https://www.kpi.or.kr/www/contents/lme.asp?CFG_CD=con_09",
                     headers=HDR, timeout=12)
    print(f"  Status: {r.status_code}")
    html = r.text

    # 니켈 관련 텍스트 주변 추출
    idx = html.lower().find('nickel')
    if idx < 0:
        idx = html.find('니켈')
    if idx >= 0:
        print(f"  니켈 위치 주변:\n{html[max(0,idx-100):idx+400]}")
    else:
        print("  '니켈/nickel' 텍스트 없음 — 앞 500자:")
        print(html[:500])

    # 18,000~20,000 범위 숫자 전체
    prices = re.findall(r'1[789],\d{3}(?:\.\d+)?', html)
    print(f"  가격 범위 숫자들: {prices[:20]}")

    # 테이블 행에서 가격 찾기
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for row in rows:
        nums = re.findall(r'1[789],\d{3}', row)
        if nums:
            clean = re.sub(r'<[^>]+>', ' ', row).strip()
            clean = re.sub(r'\s+', ' ', clean)
            print(f"  행: {clean[:200]}")

except Exception as e:
    print(f"  ❌ 오류: {e}")


# ── 2. tradingeconomics.com ──────────────────────────────────────────────────
print("\n" + "="*60)
print("[2] tradingeconomics.com 메타 파싱")
try:
    r = requests.get("https://tradingeconomics.com/commodity/nickel",
                     headers=HDR, timeout=12)
    print(f"  Status: {r.status_code}")

    # meta description 전체 추출 (두 가지 패턴 시도)
    m = re.search(r'name=["\']description["\'][^>]*content=["\']([^"\']{20,})["\']', r.text, re.I)
    if not m:
        m = re.search(r'content=["\']([^"\']*Nickel[^"\']*)["\']', r.text, re.I)
    if m:
        desc = m.group(1)
        print(f"  meta description:\n  {desc[:300]}")
        pm = re.search(r'(?:fell|rose|traded)[^\d]*([\d,]+)\s*USD', desc, re.I)
        pct = re.search(r'([\+\-]?[\d.]+)%', desc)
        print(f"  → 가격: {pm.group(1) if pm else '❌'}")
        print(f"  → 등락: {pct.group(1) if pct else '❌'}%")
    else:
        print("  meta description 못 찾음 — 앞 800자:")
        print(r.text[:800])

except Exception as e:
    print(f"  ❌ 오류: {e}")


# ── 3. westmetall.com ─────────────────────────────────────────────────────────
print("\n" + "="*60)
print("[3] westmetall.com 파싱")
try:
    r = requests.get(
        "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Ni_cash",
        headers=HDR, timeout=12)
    print(f"  Status: {r.status_code}")

    if r.status_code == 200:
        html = r.text
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        print(f"  총 행 수: {len(rows)}")
        for row in rows[:8]:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            cells_clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells_clean = [c for c in cells_clean if c]
            if cells_clean:
                print(f"  {cells_clean}")

except Exception as e:
    print(f"  ❌ 오류: {e}")

print("\n=== 완료 ===")
