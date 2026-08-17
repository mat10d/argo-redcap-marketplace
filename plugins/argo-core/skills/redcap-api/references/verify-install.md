---
name: verify-install
description: Repro checklist for confirming an ARGO plugin install actually works — run it in a fresh session, since plugin copies are immutable snapshots taken when a conversation starts.
---

# Verification pass — run this in a fresh Cowork chat

Confirms the v0.7.0 hardening against the **actually-installed** plugin copies, rather than
re-auditing from scratch. Every check below is designed to run in Cowork: no REDCap access keys,
no `~/.argo/.env`, no writes to the plugin tree.

**Why a fresh chat:** a session's plugin copies are an immutable snapshot taken when the
conversation starts. Nothing committed afterwards appears in that session. Start a new chat, then
run these.

## Setup — one command, run first

Shell state does not carry between commands in Cowork or Claude Code, and `CLAUDE_PLUGIN_ROOT` is
**not set** in Cowork. So locate the files by search, and combine everything into single commands.

```bash
CORE=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name argo_redcap_client.py 2>/dev/null | head -1)
echo "argo-core scripts: $(dirname "$CORE")"
```

If that prints nothing, the plugins aren't installed in this session — stop, nothing below applies.

Expected: a path ending in `/scripts`. In Cowork the parent directory will be an **opaque ID**
like `plugin_01Nb88PFMeGYARWh6p7i7MV2`, *not* `argo-core` — that's the point of check 5.

---

## 0. First-time setup

Cowork has no `~/.argo/.env` and no persistent home, so the working folder has to be created.
This check confirms setup works *and* that it's safe to run.

```bash
U=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name argo_setup.py 2>/dev/null | head -1); echo "--- with no arguments, must create nothing ---"; python3 "$U" 2>&1 | tail -4; echo "--- the default first step: --ensure (scaffolds loudly on a fresh machine, skips if set up) ---"; python3 "$U" --ensure 2>&1 | tail -6; echo "--- explicit folder form ---"; python3 "$U" --dir /tmp/argo-work-test 2>&1 | tail -8; ls -la /tmp/argo-work-test/.env
```

**Pass:** the first run explains itself and ends with "Nothing has been created yet"; the second
creates `exports/ worklists/ builds/ analysis/ pm/`, a `.gitignore`, and a `.env` with permissions
`-rw-------`. **Fail:** the no-argument run creates anything, or the `.env` is group/world
readable.

For a real setup, use a folder you've connected rather than `/tmp`, and paste the REDCap address
and any access keys into the `.env` **in an editor** — never as a command, since commands are
saved in transcripts.

## 1. Crash site: `backfill_sir_from_csv.py`

Previously raised a bare `KeyError: 'REDCAP_URL'` with nothing configured.

```bash
B=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name backfill_sir_from_csv.py 2>/dev/null | head -1); python3 "$B" --csv /nonexistent.csv 2>&1 | tail -12
```

**Pass — either of these, depending on whether any credentials file is reachable:**

- No key found (the normal Cowork case): a plain-language message explaining that no access key is
  set up, what an access key is, and that this task needs one.
- A key *was* found (a credentials folder is connected): it gets further and reports
  `I couldn't find the spreadsheet you asked me to read: /nonexistent.csv`.

Both are correct — the client now auto-discovers a settings file, so which message appears depends
on the environment, not on whether the fix works. **Fail:** any line containing `Traceback`,
especially `KeyError: 'REDCAP_URL'`, which is the exact bug this replaced.

## 2. Crash site: `review_responses.py`

Previously raised a raw `openpyxl`/`zipfile` traceback on a missing or corrupt file.

```bash
R=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name review_responses.py 2>/dev/null | head -1); printf 'not a real xlsx' > /tmp/corrupt.xlsx; python3 "$R" /tmp/missing.xlsx /tmp/other.xlsx 2>&1 | tail -6; echo "--- corrupt file ---"; python3 "$R" /tmp/corrupt.xlsx /tmp/corrupt.xlsx 2>&1 | tail -7
```

**Pass:** "I couldn't find the original worklist:" for the first, and "looks damaged or
incomplete" for the second. **Fail:** any `Traceback`.

## 3. `--check` with no access keys

The setup check must work — and be *useful* — on a machine with nothing configured. This is the
normal Cowork state, so this is the most representative check of the three.

```bash
P=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name portfolio.py 2>/dev/null | head -1); python3 "$P" --check 2>&1 | tail -15
```

**Pass:** it finds argo-core across the plugin boundary, then explains that the REDCap web address
isn't set, in plain language, naming `~/.argo/.env` and the exact line to add. Exit code 1.
**Fail:** a `Traceback`, an `ImportError`, or a complaint about `ARGO_PM_ROOT` — that variable must
no longer be required just to run `--check`.

## 4. TTY guard — must refuse, never hang

Every prompt must detect that no keyboard is attached. A regression here **hangs the session**,
so the check is wrapped in a hard timeout.

```bash
S=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name sir_update.py 2>/dev/null | head -1); python3 -c "
import subprocess,sys
try:
    p=subprocess.run([sys.executable,'$S','109','--irb-number','TEST'],stdin=subprocess.DEVNULL,
                     capture_output=True,text=True,timeout=45)
    out=(p.stdout+p.stderr)
    print(out[-600:]); print('exit=',p.returncode)
    print('RESULT:', 'PASS' if p.returncode!=0 and 'Traceback' not in out else 'FAIL')
except subprocess.TimeoutExpired:
    print('RESULT: FAIL — it hung waiting for input that can never arrive')
"
```

**Pass:** `RESULT: PASS`. With no key configured it stops at the missing-key message; with one, it
prints the proposed change then refuses and tells you to re-run with `--yes`. Either is correct —
what matters is that it **terminates** and writes nothing. **Fail:** `RESULT: FAIL`.

Same guard, second script:

```bash
SR=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name set_roles.py 2>/dev/null | head -1); python3 -c "
import subprocess,sys
try:
    p=subprocess.run([sys.executable,'$SR','SOME_TOKEN'],stdin=subprocess.DEVNULL,
                     capture_output=True,text=True,timeout=45)
    print((p.stdout+p.stderr)[-400:]); print('RESULT:','PASS' if 'Traceback' not in p.stdout+p.stderr else 'FAIL')
except subprocess.TimeoutExpired: print('RESULT: FAIL — hung')
"
```

## 5. Marker-file glob — the Cowork-specific fix

The locator must find argo-core by **file**, since Cowork's plugin directories are opaque IDs with
the plugin name only inside `.claude-plugin/plugin.json`.

```bash
CORE=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name argo_redcap_client.py 2>/dev/null | head -1); D=$(dirname "$CORE"); echo "found at: $D"; case "$D" in *argo-core*) echo "NOTE: this layout happens to contain the name — the name-independent path is untested here";; *) echo "RESULT: PASS — resolved from a directory name that does NOT contain 'argo-core'";; esac; python3 -c "
import importlib.util,sys
s=importlib.util.spec_from_file_location('c','$CORE'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
print('find_argo_core() ->', m.find_argo_core())
print('RESULT: PASS — module imports and locates itself')"
```

**Pass:** a path is printed and the module imports. In Cowork the directory should be
`plugin_<opaque-id>`, proving the search never relied on the name.

## 6. Read-only plugin tree

Nothing may write next to a script.

```bash
CORE=$(find /mnt/.remote-plugins /mnt/skills ~/.claude/plugins -name argo_redcap_client.py 2>/dev/null | head -1); ls -l "$CORE"; python3 -c "
import subprocess,sys,os
# Running --check must not attempt to create anything inside the plugin directory.
before=set(os.listdir(os.path.dirname('$CORE')))
subprocess.run([sys.executable,'$CORE','--check'],capture_output=True,timeout=60)
after=set(os.listdir(os.path.dirname('$CORE')))
print('new files in plugin dir:', after-before or 'none')
print('RESULT:', 'PASS' if not (after-before) - {'__pycache__'} else 'FAIL')"
```

`__pycache__` is the one acceptable exception — Python writes it when one script imports another,
and skips it silently when the directory is read-only, which is the Cowork case. Any *other* new
file is a real failure.

## 7. The test suite itself

**Only available if the repo folder is connected.** The tests live at the repo root, outside every plugin, so they are NOT part of a plugin snapshot — unlike this checklist, which ships inside argo-core precisely so a fresh session can read it.

```bash
T=$(find /mnt -name run_all.py -path '*tests*' 2>/dev/null | head -1); [ -n "$T" ] && python3 "$T" 2>&1 | tail -4 || echo "repo folder not connected — skip"
```

**Pass:** the run ends `All N checks passed.` for some N, with no FAILED line. (Don't pin N — the suite grows.)

---

## Checks that need an access key — skip in Cowork unless a credentials folder is connected

These are Tier 1/2/3 paths ([[access-tiers]]). In Cowork they only run if a folder containing an
`argo.env` has been connected; the client searches cwd, its parents, `/mnt/*`, and `ARGO_ENV_FILE`.
**Connect a folder holding only that file** — connected folders are readable in full.

| Check | Expected |
|---|---|
| `portfolio.py --check` with keys | one line per tracker: title, PID, ID column, key shown as `…1234` only |
| `export.py --token-env X --info` | names the project and its record-ID column (which is often *not* `record_id`) |
| `push_updates.py --force-migration` without a preview | refuses: "I can't find a record that you previewed this exact data" |
| same, after `--dry-run`, but with `--expect-project` naming the wrong project | refuses: "Stopping before making any changes", nothing written |

## 8. Network egress (sandboxed sessions)

Tells you which of three states this session is in — the interpretation matters more than the
result:

```bash
python3 - <<'EOF'
import urllib.request, urllib.error
for host in ("https://redcap.oauife.edu.ng/api/", "https://example.com"):
    try:
        urllib.request.urlopen(urllib.request.Request(host, method="HEAD"), timeout=10)
        print(f"  reachable   {host}")
    except urllib.error.HTTPError as e:
        blocked = (e.headers or {}).get("X-Proxy-Error") == "blocked-by-allowlist"
        print(f"  {'BLOCKED-BY-POLICY' if blocked else f'http {e.code}'}   {host}")
    except Exception as e:
        print(f"  unreachable {host}  ({str(e)[:60]})")
EOF
```

- **Both reachable** → API paths work here.
- **REDCap blocked, example.com reachable** → the allowlist is on but missing the domain: an org
  admin adds `redcap.oauife.edu.ng`, and it applies to NEW sessions only.
- **Both blocked** → network access is off org-wide. File-based paths still work; API paths
  don't, and no domain entry will help until an admin enables network access.

## Reporting back

For each numbered check, record PASS/FAIL and paste the last few lines. A FAIL on 1–4 is a
regression in the fix. A FAIL on 5 means the plugin layout differs again from what was assumed —
capture `find /mnt/.remote-plugins -maxdepth 2` so the layout can be re-derived rather than guessed.
