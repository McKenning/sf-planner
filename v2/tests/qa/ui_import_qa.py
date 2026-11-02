"""QA: save import through the real UI (Chromium). DEV ONLY (writes). Usage: ui_import_qa.py BASE [shots]"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8043"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp")
PHASE = sys.argv[3] if len(sys.argv) > 3 else "all"   # mk | m1 | all  (m1 = the 34 MB save, run on its own to keep Chromium small)
SAVES = Path.home() / "sf-inputs/saves"
res = []


def check(name, cond, detail=""):
    res.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if (detail and not cond) else ""), flush=True)


def load(pg, name, timeout=240000):
    t0 = time.time()
    pg.set_input_files("#file", str(SAVES / name))
    pg.wait_for_function("document.querySelector('#status').textContent.startsWith('Grouped') "
                         "|| document.querySelector('#status').textContent.startsWith('Could not')", timeout=timeout)
    return pg.inner_text("#status"), time.time() - t0


def rows(pg):
    out = []
    for tr in pg.locator("#rows tr").all():
        out.append({"name": tr.locator("input.nm").input_value(), "label": tr.locator("select.lb").input_value(),
                    "machines": tr.locator("td").nth(3).inner_text(), "inc": tr.locator("input.inc").is_checked()})
    return out


def save(pg):
    pg.click("#save")
    pg.wait_for_selector("#result:not([hidden])", timeout=120000)
    return pg.inner_text("#result")


def browser(p):
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    return b, pg, errs


with sync_playwright() as p:
  if PHASE in ("mk", "all"):
    b, pg, errs = browser(p)
    pg.goto(BASE + "/import")
    st, secs = load(pg, "MK1-2i.sav")
    check("MK1-2i parses and groups", st.startswith("Grouped"), st)
    print("   ", st, f"{secs:.1f}s")
    pg.click("#use-connection")
    r0 = rows(pg)
    print("    connection groups:", len(r0), "labels:", {l: sum(1 for r in r0 if r['label'] == l) for l in {r['label'] for r in r0}})
    pg.screenshot(path=SHOTS / "import-review.png")
    # rename (hostile) / relabel / merge / split / attach
    pg.locator("#rows tr").nth(0).locator("input.nm").fill('<script>window.__x=1</script> "QA"')
    outposts = [i for i, r in enumerate(r0) if r["label"] == "outpost"]
    if len(outposts) >= 2:
        for i in outposts[:2]:
            pg.locator("#rows tr").nth(i).locator("input.sel").check()
        pg.click("#merge")
        check("merge reduces group count", len(rows(pg)) == len(r0) - 1, f"{len(r0)} -> {len(rows(pg))}")
    n_before = len(rows(pg))
    big = max(range(n_before), key=lambda i: int(rows(pg)[i]["machines"] or 0))
    pg.locator("#rows tr").nth(big).get_by_role("button", name="Split").click()
    pg.wait_for_timeout(2500)
    n_after = len(rows(pg))
    check("split increases group count (or explains)", n_after > n_before or "one group" in pg.inner_text("#status"), pg.inner_text("#status"))
    pg.locator("#rows tr").nth(1).locator("select.lb").select_option("other")
    pg.locator("#rows tr").nth(2).locator("select.at").select_option(index=1)
    pg.screenshot(path=SHOTS / "import-review-edited.png", full_page=True)
    msg = save(pg)
    print("    save1:", msg.replace("\n", " ")[:300])
    check("save works", "Saved" in msg, msg)
    check("hostile group name not executed", pg.evaluate("window.__x") is None)
    pg.goto(BASE + "/factories")
    check("factories page escapes the hostile name", pg.evaluate("window.__x") is None)
    # re-import same save with default grouping: expect no changes, nothing duplicated
    pg.goto(BASE + "/import")
    count_before = len(pg.context.request.get(BASE + "/factories").text())
    # (the first save was hand-edited, so the first default-grouping import legitimately differs; the second must be a no-op)
    load(pg, "MK1-2i.sav")
    pg.click("#use-connection")
    msg = save(pg)
    check("default-grouping import after hand-edited one is processed (grouping differs)", "No changes" not in msg, msg)
    pg.goto(BASE + "/import")
    load(pg, "MK1-2i.sav")
    pg.click("#use-connection")
    msg = save(pg)
    check("re-import of the same save with the same grouping says No changes", "No changes" in msg, msg)
    # same save, user changes the grouping (distance) -> should not be silently ignored
    pg.goto(BASE + "/import")
    load(pg, "MK1-2i.sav")
    pg.click("#use-distance")
    msg = save(pg)
    print("    same save, distance grouping:", msg.replace("\n", " ")[:200])
    check("same save with DIFFERENT grouping is not reported as 'identical'", "No changes" not in msg, msg)
    errs = [e for e in errs if "400" not in e]
    check("no console errors (MK1-2i)", not errs, str(errs[:3]))
    b.close()
  if PHASE in ("m1", "all"):
    b, pg, errs = browser(p)
    # second, different world
    pg.goto(BASE + "/import")
    st, secs = load(pg, "M1-8m.sav", timeout=300000)
    check("M1-8m parses < 30s", st.startswith("Grouped") and pg.evaluate("window.__parseSeconds") < 30, st)
    pg.click("#use-connection")
    r1 = rows(pg)
    print("    M1-8m groups:", len(r1))
    msg = save(pg)
    print("    save M1-8m:", msg.replace("\n", " ")[:600])
    check("M1-8m saved", "Saved" in msg, msg)
    errs = [e for e in errs if "400" not in e]
    check("no console errors during imports", not errs, str(errs[:3]))
    b.close()
print(f"{sum(res)} passed, {len(res) - sum(res)} failed")
