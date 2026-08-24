---
name: dd-column-spec
description: REDCap data dictionary CSV column reference — 18 columns, field types, validation, branching syntax, annotation tags.
---

# REDCap DD CSV reference

## Column specifications

| # | Column Name | Description | Example |
|---|---|---|---|
| 1 | Variable / Field Name | Unique snake_case identifier | `pi_first_name` |
| 2 | Form Name | Instrument name (lowercase, underscores) | `awardee_details` |
| 3 | Section Header | Groups fields visually | `Payment Information` |
| 4 | Field Type | Input type | `text`, `dropdown`, `radio` |
| 5 | Field Label | Display text for field | `"Principal Investigator First Name"` |
| 6 | Choices/Calculations | Options or calc formula | `1, Yes \| 0, No` |
| 7 | Field Note | Helper text below field | `"Enter in format: XXX-XXX-XXXX"` |
| 8 | Text Validation Type | Validation rule | `email`, `date_dmy` |
| 9 | Text Validation Min | Minimum value | `0` |
| 10 | Text Validation Max | Maximum value | `100` |
| 11 | Identifier? | PII flag | `y` or blank |
| 12 | Branching Logic | Show/hide condition | `[field] = '1'` |
| 13 | Required Field? | Mandatory flag | `y` or blank |
| 14 | Custom Alignment | Field alignment | `LH`, `RH`, `LV`, `RV` |
| 15 | Question Number | Survey question # | `1`, `2a` |
| 16 | Matrix Group Name | Groups matrix questions | `satisfaction_matrix` |
| 17 | Matrix Ranking? | Enable ranking | blank in ARGO builds (`dd_builder.py` always writes it blank; set by hand if a study ever needs ranking) |
| 18 | Field Annotation | Internal notes/tags | `@HIDDEN`, `@READONLY` |

## Field types

### text
Short single-line input. Names, IDs, short answers.
```
pi_name,form,,text,"PI Name",,,,,,,,,,,,,
```

### notes
Multi-line textarea. Paragraphs, descriptions, long responses.
```
summary,form,,notes,"Project Summary",,,,,,,,,,,,,
```

### dropdown
Single selection from menu. Best for many options (5+).
```
state,form,,dropdown,"State","1, Alabama | 2, Alaska | 3, Arizona",,,,,,,,,,,,
```

### radio
Single selection with visible options. Best for few options (2-5).
```
status,form,,radio,"Status","1, Active | 2, Inactive | 3, Pending",,,,,,,,,,,,
```

### yesno — DO NOT USE
Cannot hold MDC codes. Use `radio` with `1, Yes | 0, No` + MDC instead. See [[mdc-rules]].

### checkbox
Multiple selection. Values stored as comma-separated.
```
skills,form,,checkbox,"Skills","1, Python | 2, R | 3, SQL | 4, Excel",,,,,,,,,,,,
```

### file
File upload.
```
cv_upload,form,,file,"CV - File Upload",,,,,,,,,,,,,
```

### descriptive
Display-only text, no input collected.
```
instructions,form,,descriptive,"<div>Please complete all required fields.</div>",,,,,,,,,,,,,
```

### calc
Calculated field (read-only, auto-computed).
```
bmi,form,,calc,"BMI","round([weight]/([height]*[height])*10000,1)",,,,,,,,,,,,
```

### slider
Visual slider input.
```
pain_level,form,,slider,"Pain Level","0 | 50 | 100",,,,,,,,,,,,
```

## Choice format examples

```
1, Option A | 2, Option B | 3, Option C
2019, 2019 | 2020, 2020 | 2021, 2021
1, Yes | 0, No
1, Hospital A | 2, Hospital B | 3, Hospital C | 99, Other
1, Not Started | 2, In Progress | 3, Completed
```

## Branching logic syntax

```
[field_name] = 'value'             # equality
[field_name] <> 'value'            # not equal
[field1] = '1' AND [field2] = '1'  # AND
[field1] = '1' OR [field2] = '1'   # OR
[checkbox_field(1)] = '1'          # checkbox option checked
[field_name] <> ''                 # not empty
[age] >= 18                        # numeric comparison
```

## Common patterns

### "Other, specify" follow-up
```
institution,form,,dropdown,"Institution","1, Hosp A | 2, Hosp B | 99, Other",,,,,,,,,,,,
institution_other,form,,text,"Other Institution (specify)",,,,,,,"[institution] = '99'",,,,,,
```

### Conditional Yes/No with follow-up
```
has_insurance,form,,radio,"Do you have insurance?","1, Yes | 0, No | -666, Patient does not know | -777, Patient refused to answer | -888, Missing in case notes | -999, Other missing",,,,,,,,,,,,,
insurance_provider,form,,text,"Insurance Provider",,,,,,,"[has_insurance] = '1'",,,,,,
no_insurance_reason,form,,notes,"Reason for no insurance",,,,,,,"[has_insurance] = '0'",,,,,,
```

### Date fields
**Always use `date_dmy`** (DD-MM-YYYY) for ARGO dates. Whichever date/datetime validation a field
carries, its Field Note takes the **date-format** MDC codes, never the text-format ones
([[mdc-rules]]).
```
start_date,form,,text,"Start Date",,,date_dmy,,,,,,,,,,
```

### Rich text labels with bullet points
```
project_overview,form,"Project Overview",notes,"<div class=""rich-text-field-label""><p>Describe original goals and objectives of the grant:</p> <ul> <li>Original Project Goals and Objectives</li> <li>Target Population/Area Served</li> <li>Any Approved Changes to the Original Scope</li> </ul></div>",,,,,,,,,,,,,
```

### Payment / financial section with identifiers
```
bank_name,form,"Bank Details",text,"Bank Name",,,,,,y,,,,,,,
account_number,form,,text,"Account Number",,,,,,y,,,,,,,
swift_code,form,,text,"SWIFT Code",,,,,,y,,,,,,,
```

## Validation types

**Always use `date_dmy` (DD-MM-YYYY) for ARGO date fields.**

| Type | Description | Example |
|---|---|---|
| `email` | Valid email | Contact email |
| `date_dmy` | DD-MM-YYYY | **All ARGO dates** |
| `datetime_dmy` | DD-MM-YYYY HH:MM | Timestamps |
| `integer` | Whole numbers | Age, count |
| `number` | Decimal allowed | Weight, height |
| `phone` | Phone format | Contact phone |
| `alpha_only` | Letters only | Names |

## Field annotation tags

| Tag | Purpose |
|---|---|
| `@HIDDEN` | Hide from data entry |
| `@READONLY` | Display only, no editing |
| `@HIDDEN-SURVEY` | Hide on surveys only |
| `@HIDDEN-PDF` | Exclude from PDF exports |
| `@NOW` | Auto-fill current datetime |
| `@TODAY` | Auto-fill current date |
| `@USERNAME` | Auto-fill username |
| `@CALCTEXT` | Display calculated text |
| `@HIDECHOICE='x,y'` | Hide specific choice codes (data preserved, not selectable). Useful for legacy/pending values |
| `@MDC-EXEMPT` | **ARGO marker, not a REDCap tag.** Declares that this field is exempt from Missing Data Codes — `validate_dd.py` skips every MDC check on it, and on the whole matrix group if the field is in one. For validated psychometric / Likert scales. See [[mdc-rules]] |
