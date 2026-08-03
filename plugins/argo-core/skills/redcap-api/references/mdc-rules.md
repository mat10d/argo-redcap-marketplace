---
name: mdc-rules
description: ARGO's Missing Data Code conventions by REDCap field type. Single source of truth — do not duplicate in downstream skills.
---

# Missing Data Codes (MDC)

ARGO appends a standard set of MDC values to clinical fields across all cohort REDCaps. Every skill that touches the DD references this file rather than restating the rules.

## Standard MDC values

| Code | Meaning |
|---|---|
| -666 | Patient does not know |
| -777 | Patient refused to answer |
| -888 | Missing in case notes |
| -999 | Other missing (add comment for reason missing) |

## Rules by field type

### radio / dropdown / checkbox
Append the four MDC values to the choice list:
```
1, Yes | 0, No | -666, Patient does not know | -777, Patient refused to answer | -888, Missing in case notes | -999, Other missing
```

**Import-CSV caveat for checkbox fields:** REDCap rejects checkbox bit columns named `field___-666` (with hyphen) on data import. Ingest scripts must either (a) omit the MDC bit columns entirely from the import CSV when no record actually has MDC for that checkbox (the common case for retrospective data), or (b) rename to `field___666` (hyphen stripped). Radio/dropdown fields are unaffected — they take the raw value (`-666`) as a single cell.

### date fields (text with `date_dmy` validation)
Use date-format MDC codes in the **Field Note**, not the choices:
```
[06-06-6666, Patient does not know  07-07-7777, Patient refused to answer  08-08-8888, Missing in case notes  09-09-9999, Other missing (add comment for reason missing)]
```

**Important — import vs display format:** the codes above are the DISPLAY form (DD-MM-YYYY) and belong in the DD's Field Note. When **importing** records via the API, the same codes must be reversed to YYYY-MM-DD: `6666-06-06`, `7777-07-07`, `8888-08-08`, `9999-09-09`. REDCap renders them back to display form on the form view. See [[redcap-date-import]] for full detail.

### non-date text / notes fields
Use text-format MDC codes in the **Field Note**:
```
[-666, Patient does not know  -777, Patient refused to answer  -888, Missing in case notes  -999, Other missing (add comment for reason missing)]
```

## Exempt field types

The following field types do NOT need MDC:
- `descriptive` — display-only text
- `calc` — calculated fields (cannot store MDC)
- `file` — file uploads

## Other exemptions

- **Record identifier** (first field in the DD) — does not need MDC
- **Administrative / system fields** — fields like `hospital_site` that are set by the study team, not by the patient, do not need MDC. These are listed in `MDC_EXEMPT_VARS` in `argo-build/skills/redcap-build/validate_dd.py`.

## Prohibited field type: `yesno`

`yesno` cannot hold MDC codes. **Always convert to `radio`** with:
```
1, Yes | 0, No | -666, Patient does not know | -777, Patient refused to answer | -888, Missing in case notes | -999, Other missing (add comment for reason missing)
```

This is checked by `validate_dd.py` and is one of the most common audit findings in [[redcap-build]] Path B.
