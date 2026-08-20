#!/usr/bin/env python3
"""The one list of ARGO's admin tracker REDCaps.

This list used to be written out separately in four places — the shared client, argo_setup.py,
portfolio.py, and access-tiers.md, and they had already drifted apart.
Four copies means four things to remember to update the day a token is finally issued, and
nothing checked that they agreed. They live here now; everything else imports this.

Each entry is (env_var, project_title, pid, done_marker_field).

  env_var        the name of the setting holding that project's access key
  project_title  the project's title in REDCap, used to confirm a key opens what we expect
  pid            REDCap's project number, verified live. Used to spot a key that has been
                 repointed at a different project.
  done_marker    the field the portfolio uses to bucket a record as finished
"""
from __future__ import annotations

# ARGO's REDCap instance. One org, one instance — so the settings template pre-fills it
# rather than asking every new person to find and type it correctly.
ARGO_REDCAP_URL = "https://redcap.oauife.edu.ng/api/"

# Stamped by release.py on every release — the runtime answer to "which version am I running?".
TOOLKIT_VERSION = "0.16.1"

ADMIN_TRACKERS = [
    ("STUDY_INITIATION_REQUEST", "Study Tracker",             "224", "study_production"),
    ("STUDY_PERSONELL_REQUEST",  "Study Personnel Request",   "221", "completed"),
    ("DATA_LINKING_REQUEST",     "Data Linking Request",      "222", "completed"),
    ("DATA_REQUEST",             "Data Request",              "223", "completed"),
    ("SUPPORT_TICKET_REQUEST",   "Support Ticket Request",    "225", "completed"),
]

# The form each tracker's records live on, used by the portfolio when summarising a record.
SOURCE_FORMS = {
    "STUDY_INITIATION_REQUEST": "study_initiation_request",
    "STUDY_PERSONELL_REQUEST": "study_personnel_request",
    "DATA_LINKING_REQUEST": "data_linking_request",
    "DATA_REQUEST": "data_request",
    "SUPPORT_TICKET_REQUEST": "support_ticket",
}

# The 7 canonical build steps tracked on a SIR record's build_tracking form.
SIR_BUILD_STEPS = [
    "project_created", "dd_uploaded", "user_rights_complete", "data_imported",
    "review_internal", "review_pi", "study_production",
]


def env_vars() -> list:
    return [t[0] for t in ADMIN_TRACKERS]


def title_for(env_var: str) -> "str | None":
    return next((t[1] for t in ADMIN_TRACKERS if t[0] == env_var), None)


def as_portfolio_rows() -> list:
    """(env_var, title, source_form, done_marker, 'Yes') — the shape portfolio.py wants."""
    return [(env, title, SOURCE_FORMS.get(env, ""), marker, "Yes")
            for env, title, _pid, marker in ADMIN_TRACKERS]


if __name__ == "__main__":
    for env, title, pid, marker in ADMIN_TRACKERS:
        print(f"{env:28} {title:28} pid={pid or '(none issued)':<14} done={marker}")
