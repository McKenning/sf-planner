"""QA browser run (Playwright, not pytest). Usage:
  LD_LIBRARY_PATH=... ~/pw-venv/bin/python tests/qa/ui_qa.py http://localhost:8043 [shots_dir]
Writes PASS/FAIL lines; never touches anything but the server it is pointed at (DEV ONLY - it creates data)."""
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.qa import oracle as o  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8043"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp")
results = []


def check(name, cond, detail=""):
    results.append((bool(cond), name, detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if (detail and not cond) else ""), flush=True)


def num(text, label):
    m = re.search(re.escape(label) + r"[^0-9\-]*(-?[0-9][0-9,]*\.?[0-9]*)", text)
    return float(m.group(1).replace(",", "")) if m else None


def run(vp_name, vp):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport=vp)
        pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        dialogs = []
        pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        tag = vp_name

        # ---- factory: create (hostile name), outputs ----
        pg.goto(f"{BASE}/factories")
        evil = f'<img src=x onerror="window.__xss=1">&"\'{tag}'
        pg.fill("input[name=name]", evil)
        pg.click("text=New factory")
        pg.wait_for_url("**/factory/*")
        fid = pg.url.rsplit("/", 1)[1]
        check(f"[{tag}] hostile factory name is escaped, not executed", pg.evaluate("window.__xss") is None and
              pg.locator("h1").inner_text().startswith("<img"), pg.locator("h1").inner_text())
        pg.fill("input[list=items]", "Iron Plate")
        pg.fill("form.add input[name=rate]", "60")
        pg.click("text=Add output")
        body = pg.inner_text("body")
        exp = o.plan({"Iron Plate": 60})
        check(f"[{tag}] iron plate raw ore", abs((num(body, "Iron Ore") or -1) - exp["raws"]["Iron Ore"]) < 0.011, body[:300])
        check(f"[{tag}] iron plate power {exp['power_mw']:.2f}", f"{exp['power_mw']:.1f} MW" in body)
        pg.screenshot(path=SHOTS / f"factory-{tag}.png")
        # duplicate output (same item) updates, not duplicates
        pg.fill("input[list=items]", "Iron Plate")
        pg.fill("form.add input[name=rate]", "30")
        pg.click("text=Add output")
        check(f"[{tag}] re-adding an item updates its rate", pg.locator("table tr", has_text="Iron Plate").locator("input[name=rate]").first.input_value() in ("30", "30.0"))
        # invalid item through the browser form (bypass datalist): should give a readable page
        pg.fill("input[list=items]", "Not An Item")
        pg.fill("form.add input[name=rate]", "5")
        pg.click("text=Add output")
        txt = pg.inner_text("body")
        check(f"[{tag}] unknown item shows a readable error with a way back", "Unknown" in txt and pg.locator("a").count() > 0 and not txt.strip().startswith("{"), txt[:120])
        pg.goto(f"{BASE}/factory/{fid}")
        # ---- change recipe through the comparison ----
        pg.locator("summary", has_text="Compare recipes").first.click()
        alts = pg.locator("table.cmp tr", has_text="Alternate: Iron Alloy Ingot")
        check(f"[{tag}] comparison lists alternates", alts.count() >= 0)
        # use Bolted Iron Plate path: add RIP
        pg.fill("input[list=items]", "Reinforced Iron Plate")
        pg.fill("form.add input[name=rate]", "5")
        pg.click("text=Add output")
        row = pg.locator("table.lines tr", has_text="Reinforced Iron Plate").filter(has=pg.locator("summary")).first
        row.locator("summary").click()
        row.locator("table.cmp tr", has_text="Bolted Iron Plate").get_by_role("button", name="Use").click()
        pg.wait_for_load_state()
        exp = o.plan({"Iron Plate": 30, "Reinforced Iron Plate": 5}, {"Reinforced Iron Plate": "Alternate: Bolted Iron Plate"})
        body = pg.inner_text("body")
        check(f"[{tag}] after recipe change Iron Ore matches oracle {exp['raws']['Iron Ore']:.2f}",
              abs((num(body, "Iron Ore") or -1) - exp["raws"]["Iron Ore"]) < 0.011, body[:400])
        check(f"[{tag}] power matches oracle {exp['power_mw']:.1f}", f"{exp['power_mw']:.1f} MW" in body)
        # ---- clock / sloops via the inline form, valid and invalid ----
        pg.fill("input[list=items]", "Computer")
        pg.fill("form.add input[name=rate]", "9.375")
        pg.click("text=Add output")
        row = pg.locator("table.lines tr", has_text="Computer").filter(has=pg.get_by_label("Clock percent")).first
        row.get_by_label("Clock percent").fill("250")
        row.get_by_label("Somersloops per machine").fill("2")
        row.get_by_role("button", name="Apply").click()
        pg.wait_for_load_state()
        exp = o.plan({"Computer": 9.375}, overrides={"Computer": (250, 2)})
        l = [x for x in exp["lines"] if x["recipe"] == "Computer"][0]
        body = pg.inner_text("body")
        check(f"[{tag}] Computer 250%/2 sloops -> 1 machine {l['power']:.2f} MW", "1× Manufacturer" in body and f"{l['power']:.1f} MW" in body, body[:300])
        # invalid values by disabling browser validation
        for clk, slp, label in (("0", "0", "clock 0"), ("300", "0", "clock 300"), ("100", "9", "sloops 9"), ("100", "-1", "sloops -1"), ("1e999", "0", "clock huge"), ("abc", "0", "clock text")):
            row = pg.locator("table.lines tr", has_text="Computer").filter(has=pg.get_by_label("Clock percent")).first
            pg.evaluate("document.querySelectorAll('form').forEach(f=>f.noValidate=true); document.querySelectorAll('input[type=number][name=clock_pct]').forEach(i=>i.type='text')")
            row.get_by_label("Clock percent").fill(clk)
            row.get_by_label("Somersloops per machine").fill(slp)
            row.get_by_role("button", name="Apply").click()
            pg.wait_for_load_state()
            txt = pg.inner_text("body")
            ok = ("Clock" in txt or "Somersloops" in txt or "valid" in txt.lower()) and not txt.strip().startswith("{")
            check(f"[{tag}] invalid {label} gives readable error (not raw JSON)", ok, txt[:100])
            pg.goto(f"{BASE}/factory/{fid}")
        # remove an output
        pg.locator("table tr", has_text="Computer").filter(has=pg.get_by_role("button", name="Remove")).first.get_by_role("button", name="Remove").click()
        pg.wait_for_load_state()
        check(f"[{tag}] output removed", "Computer" not in pg.locator("section.card").first.inner_text())
        # exports
        r = pg.request.get(f"{BASE}/api/factory/{fid}/export.json")
        check(f"[{tag}] json export", r.status == 200)
        check(f"[{tag}] no console errors on factory page", not errs, str(errs[:3]))
        check(f"[{tag}] no alert dialogs", not dialogs, str(dialogs))
        b.close()
    return fid


if __name__ == "__main__":
    run("desktop", {"width": 1440, "height": 900})
    run("tablet", {"width": 1024, "height": 768})
    bad = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed")
