import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        errors = []
        page.on("console", lambda msg: errors.append(f"Console {msg.type}: {msg.text}"))
        page.on("response", lambda res: errors.append(f"Network {res.status}: {res.url}") if res.status >= 400 else None)

        print("Navigating to dashboard...")
        await page.goto("http://localhost:8081/index.html")
        await page.wait_for_timeout(3000)

        print(f"Errors detected: {errors}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
