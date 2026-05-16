"""
metalradar.com 내부 API 엔드포인트 탐색 (network interception)
"""
import asyncio, re, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="en-US",
        )
        page = await ctx.new_page()

        # 모든 API 응답 캡처
        api_calls = []

        async def on_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            # JSON 응답만 필터
            if "json" in ct and any(k in url for k in ["api", "price", "metal", "nickel", "lme"]):
                try:
                    body = await response.text()
                    api_calls.append({"url": url, "body": body[:300]})
                except:
                    pass

        page.on("response", on_response)

        print("metalradar.com 로딩 + API 캡처...")
        await page.goto(
            "https://metalradar.com/price/nickel/lme/official/3-month/cumulative-volume?includeOrigin=true",
            wait_until="networkidle",
            timeout=30000,
        )
        await page.wait_for_timeout(3000)

        print(f"\n캡처된 JSON API 호출: {len(api_calls)}개")
        for call in api_calls:
            print(f"\n  URL: {call['url']}")
            print(f"  Body: {call['body']}")

        await browser.close()

asyncio.run(main())
