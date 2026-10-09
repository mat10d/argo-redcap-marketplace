---
name: export-data
description: Fulfil a data request — get a study's records and its data dictionary out of REDCap and onto disk as files someone can actually work with. Downloads them directly with the study's access key; when there isn't one yet it offers to add it to your settings file, and falls back to click-by-click website instructions if a key can't be had. Use when taking a data request off your request queue, when someone asks for an export or "the data", or when you need a clean cohort export before analysis, tables or a manuscript. Analysing the export itself is run-analysis.
allowed-tools: Read, Bash, Write, Glob, Edit, Grep
---

# export-data

Get a study's records and data dictionary out of REDCap and onto disk. The entry point is
usually a data request on your queue ([[weekly-check]]): that record says *what was asked for
and by whom*, and it is what you close when done. It doesn't say which project to pull from or
which key opens it — once you're exporting, the trackers are out of the picture.

Talk to the user in short sentences and plain words.

## Ask which study, and where the files go

Don't infer the study from what happens to be in the folder. If the user hasn't said which study,
**ask — one question.** If you found something plausible, name it in that same question ("the
request says the CRC cohort — is that `database-manager/exports/crc`?"). Two studies look alike
from outside, and a synthetic or test export looks exactly like the real thing. Same for files
coming the other way: if they downloaded an export by hand, ask where they put it.

### The key identifies the study. Nothing else does.

**Do not open the Study Tracker or SIR records during an export** — they hold no keys and can't
say which project a key opens. Only `export.py --info` can, because only REDCap knows.

So "the CRC data" is a question of *which access key*. Look in the settings file for a key whose
name matches, run `--info` on it, and read back the project name and number it opens. No key for
the study → ask which project they mean and solicit the key (below). Never probe other keys to
find one that fits, and never improvise a "list my projects" call.

## `export.py` is the only path

**Run `export.py`. Never hand-roll the export** — not a `python3 -c` snippet, not a
`RedcapClient` call, not `curl`. The one time an agent improvised, it built a malformed `fields`
parameter and put a raw traceback in front of the user. `export.py` confirms the key opens the
project you meant, retries when REDCap blips, names the files consistently and fails in plain
words. If it can't do what's needed, say so and ask before doing anything by hand.

`--token-env` takes the *name of the setting* holding the key; the key itself stays in the
settings file and never appears in a command. The script loads the settings file itself.

```bash
E=$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name export.py 2>/dev/null | head -1)

python3 "$E" --token-env CRC_TOKEN --info                                   # what does this key open?
python3 "$E" --token-env CRC_TOKEN --out database-manager/exports/crc       # the usual thing
python3 "$E" --token-env CRC_TOKEN --expect-project 77 --out database-manager/exports/crc
```

Other flags: `--what records|metadata|both`, `--forms a,b,c`, `--only-raw`, `--only-labelled`,
`--expect-project NAME_OR_PID` (refuses to download unless the key opens that project).

A relative `--out` is measured from the user's ARGO folder (where the settings file lives), not
from wherever the command ran. Absolute paths are used as given.

### What one run produces

The whole set, every time — no encoding to choose up front, because choosing means knowing what
you'll need before you've looked:

| File | What it is | Give it to |
|---|---|---|
| `<slug>_datadictionary_<date>.csv` | the field list, with choice codes and `Identifier?` flags | everything |
| `<slug>_records_raw_<date>.csv` | codes (`1`, `2`) | **[[run-analysis]] and the QA tools — the one they read** |
| `<slug>_records_labelled_<date>.csv` | the same records, labels (`Male`) | a person reading by eye |
| `<slug>_records_deidentified_raw_<date>.csv` | raw, minus every field the dictionary flags as an identifier | the one that can leave the building |
| `<slug>_records_deidentified_labelled_<date>.csv` | the same, labelled | reading by eye, shareable |
| `<slug>_records_labelled_tidy_<date>.csv` | labelled, each checkbox folded into one column (only when there are checkboxes) | a spreadsheet a person will scroll |
| `README.md` | what each file is, counts, which the tools read, which is safe to share | whoever opens the folder next |

Tell the user in those words — "raw codes", "readable labels", "de-identified" — never just "the
export". The script's "Saved" lines say the same; read them back.

**De-identification is a filter, not a judgement.** The `_deidentified_` files drop the fields
the dictionary marks `Identifier?` — nothing else. A free-text note naming a relative is still
there. Say so when you hand one over. If the dictionary flags nothing, **no de-identified copy
is written** (an identical file under that name would be a lie); the README says so, which
usually means nobody ticked the boxes in the Designer — worth passing on.

What an export contains at all is decided by the export rights of the account the key belongs
to. For an extract de-identified at source, the key must belong to an account with
"De-Identified" export rights — ask the REDCap administrator. Either way, check a file before
sharing it.

Counts are real CSV rows, not lines (a free-text answer with a line break spans several lines).
They say `records`, and add patients only when the record-ID column proves it: "2,143 records
across 1,525 patients".

## No key for this study? Ask for it — the export is the whole point

Ask for the key rather than handing back instructions — one line, one question:

> This study has no access key in your settings file yet. With one, I can download the records
> and data dictionary straight into your folder. **Want me to put your settings file on screen
> so you can paste it in?**

1. **Yes → put the file itself in the chat.** In Cowork, present it with `present_files`.
   Otherwise: open the ARGO folder and double-click **'Add keys here'**. Say which line the key
   goes on (`<STUDY>_TOKEN=`, one per study) and to save.
2. **Wait.** Don't fill the silence with website instructions.
3. **Verify:**
   ```bash
   D=$(dirname "$(find /mnt/.remote-plugins /mnt/skills ~/mnt ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1)")
   python3 "$D/argo_redcap_client.py" --check
   ```
   Relay the result in one line.
4. **Then export** with `export.py`.

**Never ask for a key in the chat** — a key typed here is in the transcript forever. If they
start, stop them and point at the file.

**Only if they can't get one** (a key is issued per person, per project, by an administrator —
[[project-no-super-token]]), take the website path. It works, so it's never a failure — but don't
reach for it before offering the key:

1. Open the study in REDCap.
2. **Data Exports, Reports, and Stats** → "All data" → CSV, choosing **CSV / Microsoft Excel (raw
   data)**.
3. **Data Dictionary** → download as CSV.

Save both into `database-manager/exports/<study>/`. These are what [[run-analysis]] and the QA
tools expect — **provided the data export is the raw one.** The website's labelled export is a
different file; the tools read codes. Say which encoding a file is before using it.
Click-by-click: [[getting-files-from-redcap]]. A website download is just those two files — no
de-identified copy, no README. If they'll be shared, either run `export.py` with a key, or drop
the flagged columns by hand and say which.

## Close out the request

When the files are on disk and handed over, close the request: `close_request.py data <record>`
from [[weekly-check]] (shows the change, asks first), or tick `completed` in the REDCap UI. An
unclosed request sits on someone's queue forever.

## Reference

What REDCap's API parameters mean, for explaining an option — not for running:
[[redcap-api-reference]]. Base conventions: [[redcap-api]]. Project-identification safety:
[[token-confirmation]], [[record-id-safety]]. Write-side traps: [[redcap-api-gotchas]].

Next step: [[run-analysis]] (argo-data-analyst) turns these files into tables and figures, with
no access key.
