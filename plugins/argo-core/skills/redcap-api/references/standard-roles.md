---
name: standard-roles
description: ARGO's four standard REDCap user roles (Study Builder, PI, PM, Data Entry) — canonical JSON payloads for the userRole API endpoint.
---

# Standard ARGO roles

Every ARGO cohort REDCap is set up with these four roles. [[build-study]] step 4 generates them
as an upload-ready CSV (`make_roles_csv.py`); the JSON payloads below are the same roles for the
`userRole` API endpoint, used when copying a role set between studies by hand.

Placeholders to replace:
- `<all_forms>` — every form in the target study, set to the indicated access level
- `<clinical_forms>` — only the clinical data forms (Data Entry gets View & Edit on these and Read Only on `qa`)

## The roles CSV (the normal path — no access key needed)

`make_roles_csv.py <dd.csv>` writes REDCap's exact upload format, columns in this order:

```
unique_role_name,role_label,design,alerts,user_rights,data_access_groups,
reports,stats_and_charts,manage_survey_participants,calendar,
data_import_tool,data_comparison_tool,logging,file_repository,
data_quality_create,data_quality_execute,api_export,api_import,
mobile_app,mobile_app_download_data,record_create,record_rename,record_delete,
lock_records_customization,lock_records,lock_records_all_forms,
forms,forms_export
```

`unique_role_name` is left blank — REDCap generates project-specific IDs on upload. The `forms`
and `forms_export` cells use `form1:level,form2:level,...` syntax, quoted because of the inner
commas.

Upload it in the UI: **User Rights → User Roles → Upload user roles (CSV)**. People are then
assigned to roles on the same page; we never generate an assignment file, because we don't know
anyone's real REDCap username.

## Access-level values

`forms` — what someone can do with a form:

| Value | Meaning |
|---|---|
| 0 | No Access |
| 1 | View & Edit |
| 2 | Read Only |
| 3 | Edit Survey Responses Only |

`forms_export` — what someone can take out of a form:

| Value | Meaning |
|---|---|
| 0 | No Access |
| 1 | Full Data Set |
| 2 | De-Identified |
| 3 | Remove All Identifier Fields |

---

## 1. Study Builder

Full system access. Design, API, locking, all admin functions. Full data export.

```json
{
  "role_label": "Study Builder",
  "design": 1, "alerts": 1, "user_rights": 1, "data_access_groups": 1,
  "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
  "calendar": 1, "data_import_tool": 1, "data_comparison_tool": 1,
  "logging": 1, "file_repository": 1, "data_quality_create": 1,
  "data_quality_execute": 1, "api_export": 1, "api_import": 1,
  "mobile_app": 0, "mobile_app_download_data": 0,
  "record_create": 1, "record_rename": 1, "record_delete": 1,
  "lock_records_customization": 1, "lock_records": 1, "lock_records_all_forms": 1,
  "forms": {"<all_forms>": 1},
  "forms_export": {"<all_forms>": 1}
}
```

## 2. Principal Investigator

Full data access with API, locking, alerts, import tools. No design rights. De-identified export only.

```json
{
  "role_label": "Principal Investigator",
  "design": 0, "alerts": 1, "user_rights": 1, "data_access_groups": 1,
  "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
  "calendar": 1, "data_import_tool": 1, "data_comparison_tool": 1,
  "logging": 1, "file_repository": 1, "data_quality_create": 1,
  "data_quality_execute": 1, "api_export": 1, "api_import": 1,
  "mobile_app": 0, "mobile_app_download_data": 0,
  "record_create": 1, "record_rename": 1, "record_delete": 1,
  "lock_records_customization": 1, "lock_records": 1, "lock_records_all_forms": 1,
  "forms": {"<all_forms>": 1},
  "forms_export": {"<all_forms>": 2}
}
```

## 3. Project Manager

Record management with user rights, data quality, logging. No API, no locking, no import tools. Full data export.

```json
{
  "role_label": "Project Manager",
  "design": 0, "alerts": 0, "user_rights": 1, "data_access_groups": 1,
  "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
  "calendar": 1, "data_import_tool": 0, "data_comparison_tool": 0,
  "logging": 1, "file_repository": 1, "data_quality_create": 1,
  "data_quality_execute": 1, "api_export": 0, "api_import": 0,
  "mobile_app": 0, "mobile_app_download_data": 0,
  "record_create": 1, "record_rename": 1, "record_delete": 1,
  "lock_records_customization": 0, "lock_records": 0, "lock_records_all_forms": 0,
  "forms": {"<all_forms>": 1},
  "forms_export": {"<all_forms>": 1}
}
```

## 4. Data Entry

Data entry on clinical forms. QA is read-only. No export, no admin.

```json
{
  "role_label": "Data Entry",
  "design": 0, "alerts": 0, "user_rights": 0, "data_access_groups": 0,
  "reports": 1, "stats_and_charts": 1, "manage_survey_participants": 1,
  "calendar": 1, "data_import_tool": 0, "data_comparison_tool": 0,
  "logging": 0, "file_repository": 1, "data_quality_create": 1,
  "data_quality_execute": 1, "api_export": 0, "api_import": 0,
  "mobile_app": 0, "mobile_app_download_data": 0,
  "record_create": 1, "record_rename": 0, "record_delete": 0,
  "lock_records_customization": 0, "lock_records": 0, "lock_records_all_forms": 0,
  "forms": {"<clinical_forms>": 1, "qa": 2},
  "forms_export": {"<all_forms>": 0}
}
```
