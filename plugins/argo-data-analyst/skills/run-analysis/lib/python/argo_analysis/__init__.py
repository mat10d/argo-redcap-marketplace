"""argo_analysis — the ARGO analysis library.

Six small modules, one contract, and the same contract again in R next door:

    core      load a study, clear the missing-data codes, read the codebook,
              work out who each field was actually asked of
    table1    the table a clinical paper opens with
    excel     one workbook per analysis, always in the house style
    figures   two charts, print-ready, colour-blind-safe
    survival  planned, not built — it says so and stops

A whole analysis is a handful of lines:

    from argo_analysis import core, table1, excel, figures

    study = core.apply_missing(core.load_study("records.csv", "datadictionary.csv"))
    t1 = table1.table1(study, "redcap_data_access_group", ["age", "sex", "education"])
    excel.write_workbook({"Table 1": t1}, "outputs/table1.xlsx")
    figures.bar_by_group(study, "education", "redcap_data_access_group",
                         "outputs/education.png")

Nothing in here reaches outside this folder: no REDCap, no network, no other
plugin. It reads two CSV files and writes files you can open. pandas is needed
throughout; openpyxl only to write a workbook; matplotlib only to draw a chart —
and each says, in one sentence, how to install itself if it is not there.
"""

from __future__ import annotations

from . import core, excel, figures, survival, table1
from .core import (
    MDC_CODES,
    Study,
    apply_missing,
    applicable,
    denominator,
    field_label,
    field_type,
    labels,
    load_study,
)
from .excel import write_workbook
from .figures import bar_by_group, hist
from .table1 import table1 as make_table1

__all__ = [
    "core", "table1", "excel", "figures", "survival",
    "Study", "load_study", "apply_missing", "labels", "applicable", "denominator",
    "field_label", "field_type", "MDC_CODES",
    "make_table1", "write_workbook", "bar_by_group", "hist",
]
