"""
news.metal.com 기사 파싱 테스트 - __NEXT_DATA__ 추출
"""
import re, json, requests
from datetime import datetime, timedelta, timezone

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# 1) 목록 페이지에서 기사 ID 추출
r = requests.get("https://news.metal.com/en/", timeout=15, headers=HEADERS)
ids = list(dict.fromkeys(re.findall(r'/newscontent/(\d{8,})', r.text)))[:5]
print(f"기사 ID 추출: {ids}")

# 2) 첫 기사 페이지에서 __NEXT_DATA__ 파싱
article_url = f"https://news.metal.com/newscontent/{ids[0]}"
r2 = requests.get(article_url, timeout=15, headers=HEADERS)
print(f"\n기사 페이지: {r2.status_code}  len={len(r2.text)}")

m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', r2.text)
if m:
    data = json.loads(m.group(1))
    # 구조 탐색
    props = data.get("props", {}).get("pageProps", {})
    print(f"\n__NEXT_DATA__ pageProps keys: {list(props.keys())[:10]}")
    # 기사 정보 찾기
    for key in props:
        val = props[key]
        if isinstance(val, dict):
            sub = list(val.keys())[:5]
            print(f"  {key}: {sub}")
        elif isinstance(val, str) and len(val) > 10:
            print(f"  {key}: {val[:80]}")
else:
    print("__NEXT_DATA__ 없음 → 다른 패턴 탐색")
    # og:title 메타태그 시도
    og_title = re.search(r'<meta property="og:title" content="([^"]+)"', r2.text)
    og_date  = re.search(r'<meta[^>]+(?:pubdate|publish_date|article:published_time)[^>]+content="([^"]+)"', r2.text)
    print(f"  og:title = {og_title.group(1) if og_title else '없음'}")
    print(f"  pubdate  = {og_date.group(1) if og_date else '없음'}")

    # JSON-LD 탐색
    ld = re.search(r'<script type="application/ld\+json">(.+?)</script>', r2.text, re.DOTALL)
    if ld:
        try:
            ld_data = json.loads(ld.group(1))
            print(f"  JSON-LD: {list(ld_data.keys())}")
            print(f"    headline: {ld_data.get('headline','')[:80]}")
            print(f"    datePublished: {ld_data.get('datePublished','')}")
        except: pass

print("\n=== 완료 ===")
