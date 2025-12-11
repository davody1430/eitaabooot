
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(no_viewport=True, java_script_enabled=True)
        page = await context.new_page()

        # Disable cache using CDP
        cdp_session = await context.new_cdp_session(page)
        await cdp_session.send('Network.setCacheDisabled', {'cacheDisabled': True})

        try:
            await page.goto("http://127.0.0.1:5000", wait_until="networkidle")
            # Navigate to the login tab
            await page.click('a[data-bs-toggle="tab"][href="#login"]')
            await page.wait_for_selector("#phoneNumber")
            await page.fill("#phoneNumber", "09123456789")
            await page.click("#loginBtn")
            await page.wait_for_selector("#login-instructions:not(.d-none)", timeout=10000)
            await page.screenshot(path="/home/jules/verification/verification.png")
            print("Screenshot taken successfully.")
        except Exception as e:
            print(f"An error occurred: {e}")
            await page.screenshot(path="/home/jules/verification/error.png")
        finally:
            await cdp_session.detach()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
