---
name: token-confirmation
description: Before any API call that modifies a REDCap project, confirm the token points at the intended project.
---

# Token confirmation

Multiple ARGO projects (admin REDCaps, four cohort REDCaps, dev/staging copies) share an API endpoint. The only thing distinguishing them is the token. A wrong token can silently destroy data in the wrong project.

**Before any write (`record import`, `metadata import`, `user import`, `file delete`, etc.):**

1. Call `content=project` to fetch project info
2. Echo `project_title` and `project_id` back to the user
3. Wait for explicit confirmation
4. Only then proceed

This rule applies to every plugin in this marketplace. See [[record-id-safety]] for the parallel field-name rule.
