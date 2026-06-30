---
name: project-no-super-token
description: OAU REDCap has no Super API Token — new-project creation is a UI step; per-project tokens are admin-granted on request. The marketplace defaults to UI/CSV paths; API is an enhancement.
---

# No Super API Token at OAU — the UI path is primary

The OAU REDCap instance does **not** issue a Super API Token, and there is no API to create a new
project. So **project creation is always a manual UI step** (New Project form), and **per-project
API tokens are granted by a REDCap admin on request**, one project at a time.

Consequences the skills are built around (see [[token-optional]]):

- **Creating a project** → prepare a paste-ready value sheet (`fill_new_project.py`); the user
  creates the project in the UI, then an admin issues its token.
- **Uploading a data dictionary / roles** → save the CSV; the user uploads via Designer / User
  Rights. No token required.
- **Reading or writing records** → use the API only once a per-project token exists; otherwise work
  from an on-disk export and apply changes through the UI.
- **Do not block** waiting for a token: requesting one per study doesn't scale. The API path is an
  enhancement layered on top of the UI path, never a prerequisite.

If a Super Token is ever granted, the create/upload steps can grow `--auto-create` / API-import
flows — but the default stays UI-first.
