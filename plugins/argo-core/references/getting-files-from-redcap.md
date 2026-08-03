---
name: getting-files-from-redcap
description: Click-by-click instructions for downloading the two files every ARGO tool needs — the records export and the data dictionary — from the REDCap website, for people who don't have an API key and don't know REDCap's menus.
---

# Getting the two files out of REDCap, by hand

Almost every ARGO tool can work from two files you download from the REDCap website. You do not
need an access key, and you do not need to ask an administrator for anything.

**The two files are:**

| File | What it is | Roughly how big |
|---|---|---|
| The **records export** | every patient's data, one row per record | one row per patient |
| The **data dictionary** | the list of fields — their names, types and answer options | one row per field |

Tools need both. The records file alone isn't enough: without the dictionary, a tool can't tell
which fields are dates, which are multiple-choice, or which only apply in certain circumstances.

---

## 1. The records export

1. Log in to REDCap and **open your project** (click its name on the "My Projects" page).
2. In the **left-hand menu**, find the heading **Applications**.
3. Click **Data Exports, Reports, and Stats**.
4. You'll see a list of reports. The first row is called **"All data (all records and fields)"**.
   On that row, click the **Export Data** button on the right.
5. A box appears asking about the format. Choose **CSV / Microsoft Excel (raw data)**.
   - **Raw** means you get the codes REDCap stores (`1`, `2`) rather than the labels (`Male`,
     `Female`). ARGO tools expect raw, and read the labels from the dictionary. If you're asked
     to choose and you're unsure, pick **raw**.
6. Click **Export Data**, then click the **download icon** that appears. Save the file somewhere
   you'll find it again.

> If step 4 shows a "de-identification" panel with tick boxes, leave it alone unless you've been
> told otherwise — ticking those removes data the QA tools need to do their job.

## 2. The data dictionary

1. Still inside the project, look in the left-hand menu under **Project Setup** — or under
   **Designer**, depending on your REDCap version.
2. Click **Designer** (sometimes labelled **Online Designer**).
3. Near the top of that page, click **Data Dictionary** (or **Download the current Data
   Dictionary**).
4. Click **Download the current Data Dictionary (CSV)**. Save it next to your records file.

---

## Which is which, afterwards

Downloads often get unhelpful names. You can tell them apart by opening each one:

- The **data dictionary** has a first column called `field_name` or `Variable / Field Name`, and
  one row per *question*.
- The **records export** has one row per *patient*, and its first column is the record ID — often
  `record_id`, but plenty of ARGO studies use `study_id`, `research_number` or similar.

Renaming them makes life easier later, for example:

```
crc_records_2026-08-03.csv
crc_datadictionary_2026-08-03.csv
```

## Handing them to a tool

Give both paths together. For example, to build QA worklists without an access key:

```bash
python3 build_worklists.py \
    --records-csv  crc_records_2026-08-03.csv \
    --metadata-csv crc_datadictionary_2026-08-03.csv \
    --fields fields.yaml --out worklists/
```

If you only pass one, the tool will tell you which one is missing and why it needs the other.

## If something doesn't match

- **"Data Exports, Reports, and Stats" isn't in the menu.** Your REDCap account doesn't have
  export rights on that project. Ask whoever runs the study to grant them — this is a permissions
  setting, not something a tool can work around.
- **The export is empty.** You may be in a Data Access Group that has no records yet, or the
  project genuinely has none.
- **Menu names differ slightly.** REDCap versions vary in wording. Look for the words *Export*
  and *Dictionary*; the position in the left-hand menu is stable even when labels change.

## A note on where these files live

They contain patient data. Keep them in your ARGO working folder (see [[access-tiers]]), not in
Downloads or on a shared drive, and don't email them.
