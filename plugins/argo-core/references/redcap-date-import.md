---
name: redcap-date-import
description: REDCap's record-import API requires dates in YYYY-MM-DD or M/D/Y format, regardless of the field's display validation (date_dmy, date_mdy, etc.). Use YYYY-MM-DD for all import CSVs.
---

# REDCap import date format

**The rule:** REDCap's `content=record action=import` API rejects any date value not in `YYYY-MM-DD` or `M/D/Y` format, even if the field is configured with `date_dmy` validation for display.

**Symptom when you get it wrong:**
```
Record 1  date_diagnosis  01-08-2015  Invalid date format. (NOTE: Dates must be
                                       imported here only in M/D/Y format or Y-M-D
                                       format, regardless of the specific date
                                       format designated for this field.)
```

This is a REDCap design choice — the display format is for UI rendering, the import format is canonical. Same data, two representations.

## What this means for ingest scripts

When producing an `import_ready.csv`:
- All date values: **YYYY-MM-DD** (e.g., `2015-08-01`, never `01-08-2015` or `08/01/2015`)
- Standardize on YYYY-MM-DD throughout — unambiguous, ISO 8601, sorts correctly as a string.

## MDC date codes in import format

The display-format MDC date codes (`06-06-6666`, `07-07-7777`, `08-08-8888`, `09-09-9999`) must be **reversed** for import:

| MDC meaning | Display form (DD-MM-YYYY) | Import form (YYYY-MM-DD) |
|---|---|---|
| Patient does not know | `06-06-6666` | `6666-06-06` |
| Patient refused to answer | `07-07-7777` | `7777-07-07` |
| Missing in case notes | `08-08-8888` | `8888-08-08` |
| Other missing | `09-09-9999` | `9999-09-09` |

REDCap will display these as `06-06-6666` etc. on the form (because the field is `date_dmy`), even though they were imported as `6666-06-06`.

## Boilerplate for ingest scripts

```python
def parse_date(v):
    """Return YYYY-MM-DD string if parseable, '' if blank, None if unparseable."""
    if v is None or str(v).strip() == "":
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if s.lower() in ("none", "n/a", "na", "-", "nil"):
        return ""
    # DD-MM-YYYY or DD/MM/YYYY source
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # YYYY-MM-DD already
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None

DATE_MDC_MISSING = "8888-08-08"   # Import form of "Missing in case notes"
```

## See also
- [[mdc-rules]] — display-format MDC codes (used in the DD's Field Note column)
- [[record-id-safety]] — first-field naming for imports
- [[token-confirmation]] — always confirm target project before import
