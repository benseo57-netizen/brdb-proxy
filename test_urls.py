"""
news.metal.com 직접 스크래핑 테스트
"""
import re, requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

urls_to_try = [
    "https://news.metal.com/en/",
    "https://news.metal.com/",
    "https://news.metal.com/en/news/",
    "https://news.metal.com/en/news/battery_recycling/",
    "https://news.metal.com/en/news/nickel/",
    "https://news.metal.com/en/news/cobalt/",
    "https://news.metal.com/en/news/lithium/",
]

for url in urls_to_try:
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        print(f"\n{url}")
        print(f"  Status: {r.status_code}  len={len(r.text)}")
        if r.status_code == 200 and len(r.text) > 500:
            # newscontent 링크 추출
            links = list(dict.fromkeys(
                re.findall(r'/newscontent/(\d+)[^"\']*', r.text)
            ))[:10]
            titles = re.findall(r'<(?:h[1-4]|a)[^>]*title="([^"]{20,120})"', r.text)[:5]
            print(f"  기사 ID: {links[:8]}")
            print(f"  제목: {titles[:3]}")
            if links:
                # 첫 기사 접근 테스트
                test_url = f"https://news.metal.com/newscontent/{links[0]}"
                r2 = requests.get(test_url, timeout=10, headers=HEADERS)
                print(f"  첫 기사 접근: {r2.status_code}  len={len(r2.text)}")
    except Exception as e:
        print(f"  {url} → 오류: {e}")

print("\n=== 완료 ===")
