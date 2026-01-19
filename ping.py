import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://mac-npi-sequencer-lfjkucxeaoczm3uwy7e6k2.streamlit.app/")
        # Wait for the app to load
        await page.wait_for_timeout(5000) 
        await browser.close()

asyncio.run(run())
