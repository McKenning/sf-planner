# SF Planner 2.0 — QA log (v2-qa1)

## Summary

15 findings: 0 blocker, 6 major (QA-01, 07, 08, 09, 10, 14), 9 minor (QA-02, 03, 04, 05, 06, 11, 12, 13, 15), 0 cosmetic. **All 15 fixed, 0 open**, each with a regression test or a QA script check.

Verified clean (no defects found): numbers vs the independent oracle (UI, 84 browser checks at 1440 and 1024); MK1-2i and M1-8m through the real UI (review edit/merge/split/attach, same-save re-import = "No changes", M1-8m after MK1-2i collides with nothing, 4474/4474 and 449/449 machines, recipes, clocks, Somersloops and per-factory outputs match the independent save reader); migration 001→002 over existing data keeps rows and makes a pre-migration backup; server restart keeps data (621 factories); bad ids are 404; no tracebacks in dev or live logs; no f-string SQL, no `|safe`, export filenames are id-only.
Observation (not a defect): with ~600 factories `/` is 618 KB (it lists every factory); fast (0.3 s) but a future paging candidate.
Browser runs were done one Chromium at a time (peak ~2.7 GB total with M1-8m); node needs `--max-old-space-size=6000` for `save_oracle.mjs` on M1-8m.



Oracle: `v2/tests/qa/oracle.py` reads the Docs file directly (no `core/`). Regression tests: `v2/tests/qa/`.
Severity: blocker / major / minor / cosmetic. Status: fixed / open / wontfix / blocked.

| ID | Area | Sev | What happens | Steps to reproduce | Expected | Status | Fix commit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QA-01 | Input validation | major | A non-finite or absurd rate is stored and breaks pages: `rate=inf` on a world goal makes `/goals` return 500 permanently (solver `OverflowError`); `rate=nan` returns 500 on factory output, goals, flows; `1e308` is accepted everywhere | `POST /goals/add item=Iron Plate rate=inf`, then `GET /goals` | 400 with a message; nothing stored | fixed | (see git log: "Validate numeric form input") |
| QA-02 | Input validation | minor | `POST /goals/assign` with a non-numeric `factory_id` returns 500 | `factory_id=abc` | 400 | fixed | same |
| QA-03 | Flows | minor | `POST /flows/add` with factory ids that do not exist returns 500 (FK error); archived factories accepted | `from_factory=99998 to_factory=99999` | 400 | fixed | same |
| QA-04 | Input validation | minor | `/resources/update` and `/power/add` with a huge integer return 500 (`OverflowError` into SQLite); unknown resource / plant id silently "succeeds" | `pure=99999999999999999999` | 400 / 404 | fixed | same |
| QA-05 | Import API | minor | `/api/import/group` and `/api/import/save` return 500 for non-object JSON, bad building/link shapes, NaN thresholds, empty or unknown-id groups (`ZeroDivisionError`) | see `tests/qa/test_robustness.py` | 400 | fixed | same |
| QA-06 | Error pages | minor | Browser requests that hit a 4xx/5xx got raw JSON (`{"detail": ...}`) instead of a readable page | open any bad URL / submit an invalid form in a browser | Readable HTML page with a way back | fixed | 9ce1f2a (`after-QA06-*.png`) |
| QA-07 | Excel export | major | A factory name starting with `=`, `+`, `-` or `@` became a spreadsheet formula in the .xlsx | name a factory `=1+1`, export Excel | Text cell, never evaluated | fixed | 3c5f6b1 |
| QA-08 | Factory page | major | The inline clock/Somersloop form re-posted the recipe it was rendered with, so a stale tab silently reverted a recipe changed in another tab | two tabs: change recipe in A, press Apply on a line in stale B | Recipe unchanged | fixed | c39dbfa |
| QA-09 | Import | major | Re-importing the same save with a different grouping (distance, merged groups) answered "identical, nothing changed" | import, then re-import with other grouping | Treated as a new import | fixed | 38ddc37 |
| QA-10 | Built vs planned | major | Comparison ignored overclocking and planned with default recipes instead of the recipes actually built | open an imported factory with alternates / clocks | Capacity counts clock; plan uses built recipes | fixed | 287cb76 (`after-QA10-*.png`) |
| QA-11 | Import | minor | Clock rounding left e.g. 0.0002/min of an intermediate as a phantom "0.00/min" output line | import HMF factory | No phantom outputs | fixed | 38ddc37 |
| QA-12 | UI clarity | minor | Links in the main pane were 18–20 px tall at 1024 px | tablet viewport, World/Factories/Goals | ≥ 40 px targets | fixed | 1d0e314 (`after-QA12-*.png`) |
| QA-13 | UI clarity | minor | Goals "Split" form checkbox/select clipped at the card edge at 1024 px | tablet viewport, /goals | Fully visible | fixed | 1d0e314 (`after-QA13-*.png`) |
| QA-14 | Security | major | No cross-site protection: a page on another site could make a visitor's browser POST to the app (no login, so any write was possible) | `curl -H 'Origin: http://evil.example' -d mw=5 /goals/power` | 403; same-origin and Origin-less (curl) requests still work | fixed | 82b75e2 |
| QA-15 | Numbers | minor | Power shown with 1 decimal in overview, factory, goals and compare tables, so values could not match the oracle to 0.01 | Iron Plate 60/min factory | MW shown to 2 decimals | fixed | 642b41b |

_Note: QA-06 … QA-13 were logged retroactively after an interrupted run (the machine ran out of memory); IDs follow the screenshot names and commit messages._
