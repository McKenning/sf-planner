# SF Planner 2.0 — QA log (v2-qa1)

_Summary is filled in at the end of the run._

Oracle: `v2/tests/qa/oracle.py` reads the Docs file directly (no `core/`). Regression tests: `v2/tests/qa/`.
Severity: blocker / major / minor / cosmetic. Status: fixed / open / wontfix / blocked.

| ID | Area | Sev | What happens | Steps to reproduce | Expected | Status | Fix commit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QA-01 | Input validation | major | A non-finite or absurd rate is stored and breaks pages: `rate=inf` on a world goal makes `/goals` return 500 permanently (solver `OverflowError`); `rate=nan` returns 500 on factory output, goals, flows; `1e308` is accepted everywhere | `POST /goals/add item=Iron Plate rate=inf`, then `GET /goals` | 400 with a message; nothing stored | fixed | (see git log: "Validate numeric form input") |
| QA-02 | Input validation | minor | `POST /goals/assign` with a non-numeric `factory_id` returns 500 | `factory_id=abc` | 400 | fixed | same |
| QA-03 | Flows | minor | `POST /flows/add` with factory ids that do not exist returns 500 (FK error); archived factories accepted | `from_factory=99998 to_factory=99999` | 400 | fixed | same |
| QA-04 | Input validation | minor | `/resources/update` and `/power/add` with a huge integer return 500 (`OverflowError` into SQLite); unknown resource / plant id silently "succeeds" | `pure=99999999999999999999` | 400 / 404 | fixed | same |
| QA-05 | Import API | minor | `/api/import/group` and `/api/import/save` return 500 for non-object JSON, bad building/link shapes, NaN thresholds, empty or unknown-id groups (`ZeroDivisionError`) | see `tests/qa/test_robustness.py` | 400 | fixed | same |
