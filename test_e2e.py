import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        errors = []
        page.on("console", lambda msg: errors.append(f"Console {msg.type}: {msg.text}") if msg.type == "error" else None)
        page.on("response", lambda res: errors.append(f"Network {res.status}: {res.url}") if res.status >= 400 else None)

        print("Navigating to dashboard...")
        await page.goto("http://localhost:8888/")
        await page.wait_for_timeout(2000)

        # STEP 0
        total = await page.locator("#stat-total-val").inner_text()
        incidents = await page.locator("#stat-incidents-val").inner_text()
        schema = await page.locator("#stat-schema-val").inner_text()
        resolved = await page.locator("#stat-resolved-val").inner_text()
        print(f"STEP 0 - Stats: Total={total}, Incidents={incidents}, Schema={schema}, Resolved={resolved}")

        # STEP 1: Detect
        print("STEP 1: Detect")
        await page.evaluate("window.location.hash='#view-detect'")
        await page.wait_for_timeout(500)
        await page.fill("#detect-urn", "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)")
        await page.click("#detect-btn")
        await page.wait_for_selector("#detect-result.success", timeout=15000)
        detect_res = await page.locator("#detect-result").inner_text()
        print(f"Detect result: {detect_res[:100]}...")
        
        # Dashboard stats check
        await page.evaluate("window.location.hash='#view-dashboard'")
        await page.wait_for_timeout(1000)
        new_total = await page.locator("#stat-total-val").inner_text()
        print(f"STEP 1 - Dashboard check: Total Memories before={total}, after={new_total}")

        # STEP 2: Diagnose
        print("STEP 2: Diagnose")
        await page.evaluate("window.location.hash='#view-detect'")
        await page.wait_for_timeout(500)
        await page.fill("#diagnose-urn", "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.order_entry_db.order_entry.orders,PROD)")
        await page.click("#diagnose-btn")
        await page.wait_for_selector("#diagnose-result:not(.hidden)", timeout=15000)
        diag_res = await page.locator("#diagnose-result").inner_text()
        print(f"Diagnose result: {diag_res[:100]}...")

        # STEP 3: Detect + Diagnose
        print("STEP 3: Full Analysis")
        await page.fill("#combo-urn", "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)")
        await page.click("#combo-btn")
        await page.wait_for_selector("#combo-result:not(.hidden)", timeout=20000)
        combo_res = await page.locator("#combo-result").inner_text()
        print(f"Combo result: {combo_res[:100]}...")

        # STEP 4: Full Loop (No recall)
        print("STEP 4: Full Loop (No Recall)")
        await page.fill("#fullloop-urn", "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.accounts,PROD)") # Non-seeded URN
        await page.click("#fullloop-btn")
        await page.wait_for_selector("#fullloop-result:not(.hidden)", timeout=30000)
        await page.wait_for_timeout(5000) # Wait for stages to complete
        loop_res = await page.locator("#fullloop-result").inner_text()
        print(f"Loop 1 result: {loop_res[:200]}...")

        await page.evaluate("window.location.hash='#view-dashboard'")
        await page.wait_for_timeout(1000)
        loop1_total = await page.locator("#stat-total-val").inner_text()
        print(f"STEP 4 - Dashboard check: Total Memories={loop1_total}")

        # STEP 5: Full Loop (Recall Expected)
        print("STEP 5: Full Loop (Recall Expected)")
        await page.evaluate("window.location.hash='#view-detect'")
        await page.wait_for_timeout(500)
        await page.fill("#fullloop-urn", "urn:li:dataset:(urn:li:dataPlatform:postgres,b2fd91.crm_db.customers,PROD)")
        await page.click("#fullloop-btn")
        await page.wait_for_selector("#fullloop-result:not(.hidden)", timeout=30000)
        await page.wait_for_timeout(8000) # Wait for stages to complete
        loop2_res = await page.locator("#fullloop-result").inner_text()
        print(f"Loop 2 result: {loop2_res[:200]}...")

        # STEP 6: Memory view
        print("STEP 6: Memory View")
        await page.evaluate("window.location.hash='#view-memories'")
        await page.wait_for_timeout(1000)
        rows = await page.locator("#memories-tbody tr").count()
        print(f"Memory table rows: {rows}")

        # STEP 7: Row actions
        print("STEP 7: Row actions")
        # Click view
        await page.click("#memories-tbody tr:nth-child(1) button[title='View details']")
        await page.wait_for_timeout(500)
        modal_res = await page.locator("#memory-modal-content").inner_text()
        print(f"Modal content: {modal_res[:50]}...")
        await page.click(".modal-close")
        await page.wait_for_timeout(500)

        # Click resolve
        await page.click("#memories-tbody tr:nth-child(1) button[title='Mark resolved']")
        await page.wait_for_timeout(1000)
        
        # Click delete
        await page.click("#memories-tbody tr:nth-child(1) button[title='Delete memory']")
        await page.wait_for_timeout(1000)

        # STEP 8: Stat cards navigation
        print("STEP 8: Stat cards")
        await page.evaluate("window.location.hash='#view-dashboard'")
        await page.wait_for_timeout(1000)
        await page.click("#stat-incidents")
        await page.wait_for_timeout(500)
        hash_val = await page.evaluate("window.location.hash")
        print(f"Navigated to: {hash_val}")

        # STEP 9: Timeline
        print("STEP 9: Timeline")
        await page.evaluate("window.location.hash='#view-timeline'")
        await page.wait_for_timeout(1000)
        timeline_items = await page.locator(".timeline-item").count()
        print(f"Timeline items: {timeline_items}")

        # STEP 10: Graph
        print("STEP 10: Graph")
        await page.evaluate("window.location.hash='#view-dashboard'")
        await page.wait_for_timeout(1000)
        nodes = await page.locator("circle.node").count()
        print(f"Graph nodes: {nodes}")

        # STEP 11: About Page
        print("STEP 11: About Page")
        await page.evaluate("window.location.hash='#view-about'")
        await page.wait_for_timeout(1000)
        cards = await page.locator(".about-stage-card").count()
        print(f"About cards: {cards}")

        # STEP 13: Errors
        print(f"STEP 13: Console/Network Errors: {errors}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
