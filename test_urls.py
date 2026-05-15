"""
metalradar.com LME 니켈 3M Official Ask 가격 Playwright 테스트
"""
import asyncio, re
from playwright.async_api import async_playwright

async def main():
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

        print("metalradar.com 로딩 중...")
        await page.goto(
            "https://metalradar.com/price/nickel/lme/official/3-month/cumulative-volume?includeOrigin=true",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(6000)

        body = await page.inner_text("body")

        # 1) Ask 가격 파싱 (19,075 범위)
        print(f"\n[body 앞 300자]\n{body[:300]}")

        # 2) Bid/Ask 패턴
        m_ask = re.search(r'Ask\s*\$?([\d,]+\.?\d*)', body)
        m_bid = re.search(r'Bid\s*\$?([\d,]+\.?\d*)', body)
        print(f"\nBid: {m_bid.group(1) if m_bid else '❌'}")
        print(f"Ask: {m_ask.group(1) if m_ask else '❌'}")

        # 3) 19,000~21,000 범위 숫자 전체
        nums = re.findall(r'1[89]\d?,\d{3}(?:\.\d+)?', body)
        print(f"\n가격 범위 숫자: {nums[:10]}")

        # 4) 등락률
        pct = re.search(r'([\-\+]?\d+\.\d+)%', body)
        print(f"등락률: {pct.group(0) if pct else '❌'}")

        await browser.close()

asyncio.run(main())

