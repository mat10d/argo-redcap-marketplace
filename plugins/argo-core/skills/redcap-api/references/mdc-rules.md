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

### date fields (text with any `date*` / `datetime*` validation)
ARGO dates are `date_dmy` (see [[dd-column-spec]]), but the rule is the validation *family*, not
the one type: `date_dmy/mdy/ymd`, `datetime_*` and `datetime_seconds_*` all take date-format MDC.
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
- **Administrative / system fields** — fields like `hospital_site` that are set by the study team, not by the patient, do not need MDC. These are listed in `MDC_EXEMPT_VARS` in `argo-database-manager/skills/build-study/validate_dd.py`.
- **Validated psychometric / Likert instruments** — a published, scored scale is administered as published; adding MDC options changes the instrument. These are exempt, but the exemption has to be **declared**: mark them `@MDC-EXEMPT` (below).

## Declaring an exemption: `@MDC-EXEMPT`

A field that is exempt for a reason the validator cannot infer says so in its own **Field Annotation** column:

```
@MDC-EXEMPT
```

- `validate_dd.py` skips **every** MDC check on an annotated field.
- Put it on **any field of a matrix group** and the whole group is waived — one annotation covers a whole Likert grid (annotating every row is fine too, and clearer).
- `dd_builder.py` writes it for you: build the field with `mdc=False` and the annotation appears in the dictionary. `mdc=False` is the only opt-out, and it is never silent.
- It is an ARGO marker, not a REDCap action tag — it sits in the Field Annotation column, which REDCap treats as free text. Not yet exercised on a live REDCap data-dictionary upload; if an instance ever objects to it, record that here.
- It is for genuinely exempt fields (validated scales, study-team admin fields), not a way to quiet the validator on ordinary clinical fields. A waiver on a field that should carry MDC is an audit finding.

## Prohibited field type: `yesno`

`yesno` cannot hold MDC codes. **Always convert to `radio`** with:
```
1, Yes | 0, No | -666, Patient does not know | -777, Patient refused to answer | -888, Missing in case notes | -999, Other missing (add comment for reason missing)
```

This is checked by `validate_dd.py`, and `dd_builder.py` refuses to build a `yesno` field at all (it names the radio replacement in the error). It is one of the most common audit findings in [[build-study]] Path B.
