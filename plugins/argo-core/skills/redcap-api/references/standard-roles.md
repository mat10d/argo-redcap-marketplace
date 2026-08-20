---
name: standard-roles
description: ARGO's four standard REDCap user roles (Study Builder, PI, PM, Data Entry) — canonical JSON payloads for the userRole API endpoint.
---

# Standard ARGO roles

Every ARGO cohort REDCap is set up with these four roles. Used by [[manage-redcaps]] when standing up a new study or copying roles between studies.

Placeholders to replace:
- `<all_forms>` — every form in the target study, set to the indicated access level
- `<clinical_forms>` — only the clinical data forms (Data Entry gets View & Edit on these and Read Only on `qa`)

## Access-level values

See `manage-redcaps` SKILL.md for the full form-access and form-export level tables.

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
