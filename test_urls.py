"""
cnyes.com LME 3M 니켈 Playwright 테스트
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
            locale="zh-TW",
        )
        page = await ctx.new_page()

        print("cnyes.com nd3m 로딩 중...")
        await page.goto(
            "https://www.cnyes.com/futures/html5chart/nd3m.html",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(6000)  # JS 렌더링 대기

        # 1) body 텍스트에서 가격 탐색
        body = await page.inner_text("body")
        print(f"\n[body 앞 500자]\n{body[:500]}")

        # 2) 18,000~20,000 범위 숫자 탐색
        nums = re.findall(r'1[89]\s*[,.]?\s*\d{3}', body)
        print(f"\n가격 범위 숫자: {nums[:20]}")

        # 3) JS 전역 변수에서 가격 탐색
        try:
            price_js = await page.evaluate("""
                () => {
                    // 페이지 전체 텍스트 노드에서 숫자 탐색
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_TEXT
                    );
                    const texts = [];
                    let node;
                    while (node = walker.nextNode()) {
                        const t = node.textContent.trim();
                        if (/1[89][,.]?\d{3}/.test(t)) texts.push(t);
                    }
                    return texts.slice(0, 20);
                }
            """)
            print(f"\nJS 텍스트 노드 가격: {price_js}")
        except Exception as e:
            print(f"JS 평가 오류: {e}")

        # 4) 페이지 title 확인
        title = await page.title()
        print(f"\nPage title: {title}")

        await browser.close()

asyncio.run(main())

