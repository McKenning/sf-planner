"""Playwright check of the World workflow against a dev server: Project Assembly goal -> budget -> split
into factories -> auto flows -> ledger deficits -> power plant. Run: ~/pw-venv/bin/python tests/browser_check_world.py"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8043"
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for label, vp in (("desktop", {"width": 1440, "height": 900}), ("tablet", {"width": 1024, "height": 768})):
        pg = b.new_page(viewport=vp)
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        for path in ("/", "/goals", "/flows", "/power", "/resources", "/factories"):
            r = pg.goto(BASE + path)
            assert r.status == 200, (path, r.status)
            assert pg.evaluate("document.documentElement.scrollWidth") <= vp["width"] + 1, (label, path)
        if label == "desktop":
            pg.goto(BASE + "/goals")
            for item, rate in (("Smart Plating", "5"), ("Modular Engine", "2.5")):
                pg.fill("form[action='/goals/add'] input[name=item]", item)
                pg.fill("form[action='/goals/add'] input[name=rate]", rate)
                pg.click("text=Add goal")
            assert "Raw totals vs budget" in pg.inner_text("body")
            assert "Iron Ore" in pg.inner_text("body")
            # split: Smart Plating -> new factory 'PW Plating'
            row = pg.locator("table.lines > tbody > tr", has=pg.locator("td:first-child", has_text="Smart Plating")).first
            row.locator("input[name=new_name]").fill("PW Plating")
            row.get_by_role("button", name="Assign").click()
            pg.wait_for_url("**/factory/*")
            pg.goto(BASE + "/goals")
            row = pg.locator("table.lines > tbody > tr", has=pg.locator("td:first-child", has_text="Modular Engine")).first
            row.locator("input[name=new_name]").fill("PW Engines")
            row.get_by_role("button", name="Assign").click()
            pg.wait_for_url("**/factory/*")
            pg.goto(BASE + "/flows")
            assert "PW Plating → PW Engines" in pg.inner_text("body"), pg.inner_text("body")[:600]
            pg.goto(BASE + "/")
            assert "Item ledger" in pg.inner_text("body")
            pg.screenshot(path="/tmp/claude-1000/-home-linadmin-sf-planner/7c2759ad-0a77-412d-9ee8-d5a01a075c6c/scratchpad/world.png")
        pg.close()
    b.close()
assert not errors, errors
print("world browser check OK")
