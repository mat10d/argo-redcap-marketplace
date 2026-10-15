---
name: link-patients
description: IN DEVELOPMENT on the linkage branch, not shipped. Link patients across ARGO studies from their exports, by site + hospital number, histology number and name, and report typos as RA worklists. Read-only; writes nothing to REDCap.
allowed-tools: Read, Bash, Write
---

# link-patients (in development)

Not part of any release. Built on the `linkage` branch until the access keys, the PathPresenter
metadata API and the parent table are settled.

One run reads one export per study and a studies file naming each study's fields, and writes
links, people, a check of every stored parent ID, a review list, near-miss worklists per site and
the name pairs to judge. See the docstring of `link_patients.py`.

```bash
python3 link_patients.py --studies studies.csv --exports <folder> --out ~/.argo/linkage/run-<date>
```

The output holds names and hospital numbers. Keep `--out` outside any folder Cowork can read.
Nothing is written to REDCap and no model is called; the ambiguous names in
`names_to_judge.csv` are for the session (or a person) to judge.
