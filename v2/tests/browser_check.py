"""Playwright check against a running dev server (not part of pytest: needs a browser).
Run: ~/pw-venv/bin/python tests/browser_check.py [base_url]
Uses a throwaway factory it creates; asserts the factory page flow end to end."""
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
        pg.goto(f"{BASE}/factories")
        pg.fill("input[name=name]", f"pw-check-{label}")
        pg.click("text=New factory")
        pg.wait_for_url("**/factory/*")
        assert "Outputs" in pg.inner_text("body")
        pg.fill("input[list=items]", "Iron Plate")
        pg.fill("form.add input[name=rate]", "60")
        pg.click("text=Add output")
        body = pg.inner_text("body")
        assert "Iron Ore" in body and "90.00 / min" in body, body[:500]
        assert pg.locator(".strip .big").first.inner_text().endswith("MW")
        # clock + sloops override on the Iron Plate line
        row = pg.locator("table.lines tr", has_text="Iron Plate").filter(
            has=pg.get_by_label("Clock percent")).first
        row.get_by_label("Clock percent").fill("200")
        row.get_by_role("button", name="Apply").click()
        pg.wait_for_load_state()
        assert "2×" in pg.inner_text("body") or "2×" in pg.content()
        # recipe picker opens and offers a recipe
        pg.locator("summary", has_text="Compare recipes").first.click()
        assert pg.locator("table.cmp").first.is_visible()
        # no page-level horizontal scroll (tables scroll inside their card)
        sw = pg.evaluate("document.documentElement.scrollWidth")
        assert sw <= vp["width"] + 1, (label, sw)
        # touch target size
        h = pg.locator("button", has_text="Add output").bounding_box()["height"]
        assert h >= 40, h
        # export links
        for ext, ct in (("json", "application/json"), ("xlsx", "spreadsheetml")):
            r = pg.request.get(pg.url.replace("/factory/", "/api/factory/") + f"/export.{ext}")
            assert r.status == 200 and ct in r.headers["content-type"]
        pg.screenshot(path=f"/tmp/claude-1000/-home-linadmin-sf-planner/7c2759ad-0a77-412d-9ee8-d5a01a075c6c/scratchpad/factory-{label}.png", full_page=False)
        pg.close()
    b.close()
assert not errors, errors
print("browser check OK")
