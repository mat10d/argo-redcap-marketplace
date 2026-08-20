---
name: token-optional
description: Cross-cutting rule — never hard-require a REDCap API token. Use the API only when a token for that project is present; otherwise fall back to on-disk data + the manual UI path.
---

# Tokens are optional — degrade gracefully, never block

REDCap API tokens are **scarce and admin-gated**: every project's token must be issued by a
REDCap admin, per user, per project. Requesting one for each new study does not scale, and OAU
has no Super API Token at all (project *creation* is UI-only — see [[project-no-super-token]]).

**So no ARGO skill may hard-require a token.** A token is an *accelerator* when present, never a
prerequisite. This applies to the admin trackers (SIR/SPR/etc.) too: everyone on the team should
hold those five keys, but never *assume* they're configured in this session — check, and degrade
if not.

In anything the user sees, call it an **access key**, never a token or API token.

## The rule

For any operation a skill performs:

1. **Check whether a token for the target project is present** (e.g. `os.environ.get(VAR)`).
2. **Token present → use the API path** (after confirming the project, see [[token-confirmation]]).
3. **Token absent → take the no-token path. Do not error, do not demand a token.** Tell the user
   plainly that you're proceeding without the API, and use files instead.

## No-token paths by operation

| Operation | With a token (API) | Without a token (default-safe) |
|---|---|---|
| **Read records / metadata** | `content=record` / `content=metadata` export | Work from an export/download the user provides on disk (CSV + data dictionary). This is the [[run-analysis]] model. |
| **Create a project** | (needs a Super Token — ARGO has none) | Generate the paste-ready "Create New Project" sheet; the user creates it in the UI ([[build-study]]). |
| **Upload a data dictionary** | API import | Save the validated DD CSV; the user uploads it via Designer ([[build-study]]). |
| **Set roles / user rights** | `content=userRole` API | Generate the roles CSV; the user uploads it (User Rights → Upload). `manage-redcaps` already supports this CSV path. |
| **Write/back-fill records** | diff-only API import | Emit the update/conflict CSVs for the user to import via the UI ([[link-data]] diff_payload). |
| **QA worklists** | pull via `--token-env` | Run against a local record export + Data Dictionary the user downloaded: `build_worklists.py --records-csv --metadata-csv`. |

## How a skill should behave

- Detect token presence first; branch to the right path; state which path you took.
- Prefer whatever input is actually available — if the user already has an on-disk export, use it
  even when a token exists (faster, and keeps cohort data out of unnecessary API calls).
- When you produce a file for the user to apply manually (paste sheet, DD CSV, roles CSV, import
  CSV), say exactly where it is and what UI step applies it.
- Only ask the user to obtain a token when the task is genuinely impossible without one — and even
  then, take the manual path first and tell them what you did, so getting a key is an improvement
  they can make later, not a blocker now.

See also: [[token-confirmation]] (when you DO have a token, confirm the project before writing),
[[redcap-api-gotchas]], [[project-no-super-token]].
