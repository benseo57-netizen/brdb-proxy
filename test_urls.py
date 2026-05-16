"""
metalradar.com T-2 날짜 파라미터 테스트
"""
import asyncio, re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

async def main():
    # T-2 날짜 계산 (주말 건너뜀)
    today = datetime.now()
    offset = 1
    if today.weekday() == 0:    # 월요일 → 금요일
        offset = 3
    elif today.weekday() == 6:  # 일요일 → 금요일
        offset = 2
    t2_date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
    print(f"오늘: {today.strftime('%Y-%m-%d')} ({['월','화','수','목','금','토','일'][today.weekday()]})")
    print(f"T-2 날짜: {t2_date}")

    BASE = "https://metalradar.com/price/nickel/lme/official/3-month/cumulative-volume?includeOrigin=true"

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

        async def fetch(url, label):
            print(f"\n[{label}] {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(6000)
            body = await page.inner_text("body")
            m_ask = re.search(r'Ask\s*\$?([\d,]+\.?\d*)', body)
            m_bid = re.search(r'Bid\s*\$?([\d,]+\.?\d*)', body)
            print(f"  Bid: {m_bid.group(1) if m_bid else '❌'}")
            print(f"  Ask: {m_ask.group(1) if m_ask else '❌'}")
            nums = re.findall(r'1[89]\d?,\d{3}(?:\.\d+)?', body)
            print(f"  범위 숫자: {nums[:8]}")
            return float(m_ask.group(1).replace(",","")) if m_ask else None

        t1 = await fetch(BASE, "T-1 (최신)")
        t2 = await fetch(f"{BASE}&date={t2_date}", f"T-2 ({t2_date})")

        if t1 and t2:
            pct = (t1 - t2) / t2 * 100
            print(f"\n✅ 등락률 계산: ({t1:,.0f} - {t2:,.0f}) / {t2:,.0f} = {pct:+.2f}%")
        else:
            print("\n❌ 계산 불가")

        await browser.close()

asyncio.run(main())
