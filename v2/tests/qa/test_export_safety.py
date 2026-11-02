"""A factory name must never become a spreadsheet formula in the Excel export (QA-07)."""
import io

import openpyxl

from app import factory_service as fs
from core import solver


def test_xlsx_title_is_text_even_for_formula_names():
    res = solver.solve({"Desc_IronPlate_C": 60})
    for name in ('=HYPERLINK("http://evil","x")', "+1+1", "-2", "@SUM(1)"):
        wb = openpyxl.load_workbook(io.BytesIO(fs.export_xlsx(name, {"Desc_IronPlate_C": 60}, res)))
        for ws in wb:
            for row in ws.iter_rows():
                for c in row:
                    assert c.data_type != "f", (name, ws.title, c.coordinate, c.value)
        assert name in wb["Summary"]["A1"].value
