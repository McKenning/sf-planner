"""Playwright check of the save import page against a dev server with a fresh DB.
Run: ~/pw-venv/bin/python tests/browser_check_import.py [base_url] [--big]
--big also parses the 34 MB stress save and asserts < 30 s and a responsive page (worker)."""
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = next((a for a in sys.argv[1:] if a.startswith("http")), "http://localhost:8043")
SAVES = Path.home() / "sf-inputs/saves"
errors = []

JANK = """
window.__gap = 0; let last = performance.now();
(function tick(){ const n = performance.now(); window.__gap = Math.max(window.__gap, n - last); last = n; requestAnimationFrame(tick); })();
"""


def load(pg, name, timeout=120000):
    t0 = time.time()
    pg.set_input_files("#file", str(SAVES / name))
    pg.wait_for_function("document.querySelector('#status').textContent.startsWith('Grouped') "
                         "|| document.querySelector('#status').textContent.startsWith('Could not')", timeout=timeout)
    txt = pg.inner_text("#status")
    assert txt.startswith("Grouped"), txt
    return time.time() - t0


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/import")
    pg.evaluate(JANK)
    secs = load(pg, "MK1-2i.sav")
    print(f"MK1-2i: parsed+grouped in {secs:.1f}s; worst main-thread gap {pg.evaluate('window.__gap'):.0f} ms")
    assert pg.locator("#list-connection li").count() >= 8 and pg.locator("#list-distance li").count() >= 8
    assert pg.locator("#plot-connection circle").count() > 100
    pg.click("#use-connection")
    assert pg.locator("#rows tr:has(input.nm[value='Heavy Modular Frame factory'])").count() == 1
    row = pg.locator("#rows tr:has(input.nm[value='Heavy Modular Frame factory'])")
    assert row.locator("select.lb").input_value() == "factory"
    # rename + split + merge work
    row.locator("input.nm").fill("Rocky Desert HMF")
    n0 = pg.locator("#rows tr").count()
    row.get_by_role("button", name="Split").click()
    pg.wait_for_function(f"document.querySelectorAll('#rows tr').length > {n0}")
    n1 = pg.locator("#rows tr").count()
    pg.reload()
    pg.evaluate(JANK)
    load(pg, "MK1-2i.sav")
    pg.click("#use-connection")
    pg.locator("#rows tr:has(input.nm[value='Heavy Modular Frame factory'])").locator("input.nm").fill("Rocky Desert HMF")
    pg.click("#save")
    pg.wait_for_selector("#result:not([hidden])")
    assert "Saved" in pg.inner_text("#result"), pg.inner_text("#result")
    pg.goto(BASE + "/factories")
    assert "Rocky Desert HMF" in pg.inner_text("body")
    pg.click("a:text('Rocky Desert HMF')")
    assert "Built vs planned" in pg.inner_text("body")
    assert pg.locator("section:has(h2:text-matches('Built vs planned')) tr").count() >= 5
    pg.goto(BASE + "/import")
    load(pg, "MK1-2i.sav")
    pg.click("#use-connection")
    pg.click("#save")
    pg.wait_for_selector("#result:not([hidden])")
    assert "No changes" in pg.inner_text("#result"), pg.inner_text("#result")
    pg.set_viewport_size({"width": 1024, "height": 768})
    for path in ("/import", "/factories"):
        pg.goto(BASE + path)
        assert pg.evaluate("document.documentElement.scrollWidth") <= 1025, path
    if "--big" in sys.argv:
        pg.goto(BASE + "/import")
        pg.evaluate(JANK)
        t = load(pg, "M1-8m.sav", timeout=300000)
        parse_s = pg.evaluate("window.__parseSeconds")
        gap = pg.evaluate("window.__gap")
        print(f"M1-8m: parse {parse_s:.1f}s, total {t:.1f}s, worst main-thread gap {gap:.0f} ms")
        assert parse_s < 30, parse_s
        assert gap < 1500, gap
    b.close()
assert not errors, errors
print("import browser check OK")
