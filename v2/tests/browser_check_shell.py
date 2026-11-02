"""Phase 5 polish check: theme toggle, Ctrl+K search, item/recipe pages, and a touch-target scan
(every visible control >= 40 px high) on every page at 1024 px. Run: ~/pw-venv/bin/python tests/browser_check_shell.py"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8043"
PAGES = ["/", "/goals", "/factories", "/flows", "/power", "/resources", "/import", "/factory/1"]
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1024, "height": 768})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    for path in PAGES:
        assert pg.goto(BASE + path).status == 200, path
        assert pg.evaluate("document.documentElement.scrollWidth") <= 1025, path
        small = pg.evaluate("""() => [...document.querySelectorAll('button, select, input:not([type=hidden]):not([type=checkbox]):not([type=range]), summary, nav.side a, a.btn')]
            .filter(e => e.offsetParent !== null && !e.closest('#palette'))
            .map(e => [e.tagName + (e.name ? '[' + e.name + ']' : ''), Math.round(e.getBoundingClientRect().height)])
            .filter(([n, h]) => h < 40)""")
        assert not small, (path, small[:5])
    # theme: system -> light -> dark, persisted
    pg.goto(BASE + "/")
    pg.click("#theme")
    assert pg.evaluate("document.documentElement.dataset.theme") == "light"
    pg.click("#theme")
    assert pg.evaluate("document.documentElement.dataset.theme") == "dark"
    bg_dark = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    pg.reload()
    assert pg.evaluate("document.documentElement.dataset.theme") == "dark"
    pg.click("#theme")
    assert pg.evaluate("document.documentElement.dataset.theme") is None
    pg.click("#theme")                               # system -> light
    assert pg.evaluate("getComputedStyle(document.body).backgroundColor") != bg_dark
    pg.evaluate("localStorage.clear()")
    # Ctrl+K search
    pg.goto(BASE + "/")
    pg.keyboard.press("Control+k")
    assert pg.locator("#palette").is_visible()
    pg.fill("#q", "heavy modular")
    pg.wait_for_function("document.querySelector('#results').textContent.includes('Heavy Modular') && !document.querySelector('#results').textContent.includes('Plutonium')")
    first = pg.inner_text("#results li:first-child")
    assert "Heavy Modular Frame" in first, first  # factory "Heavy Modular Frames" ranks first
    pg.keyboard.press("ArrowDown")
    pg.keyboard.press("Escape")
    assert not pg.locator("#palette").is_visible()
    pg.keyboard.press("Control+k")
    pg.fill("#q", "iron plate")
    pg.wait_for_function("document.querySelector('#results li a span').textContent.startsWith('Iron Plate')")
    pg.keyboard.press("Enter")
    pg.wait_for_url("**/item/*")
    assert "Iron Plate" in pg.inner_text("h1") and "Made by" in pg.inner_text("body")
    pg.click("section a[href^='/recipe/']")
    pg.wait_for_url("**/recipe/*")
    assert "Power per machine" in pg.inner_text("body")
    b.close()
assert not errors, errors
print("shell browser check OK")
