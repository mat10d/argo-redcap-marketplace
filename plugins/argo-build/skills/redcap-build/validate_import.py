#!/usr/bin/env python3
"""
REDCap Import-Data Validator

Validates an import-ready CSV against a REDCap data dictionary's branching
logic. Catches the common pre-import problems where the ingest step writes
a value into a field that the DD says should be hidden (parent condition
false), or sets checkbox bits on a hidden checkbox.

This is the data-side companion to validate_dd.py:
  - validate_dd.py    — does the DD itself conform to REDCap rules?
  - validate_import.py — does this import_ready.csv conform to the DD's
                         branching logic?

Usage:
  python3 validate_import.py <dd_csv> <import_csv> [--semantic <module.py>]
                                                    [--report <out.md>]

Optional --semantic loads a Python file that defines:
  def check(rows, issues): ...
where `rows` is a list of dicts (one per import record) and `issues` is a
list to which the function appends dicts of the form:
  {'record_id': ..., 'field': ..., 'severity': 'error'|'warn', 'note': ...}

Exit status: 0 if no errors, 1 if any errors. Warnings do not fail.

Supported branching grammar (parsed from the DD's branching column):
    [field] = '1'
    [field] = '1' or [field] = '2'
    [field(99)] = '1'                  (checkbox option)
    A or B
More complex expressions (and / parens / <>) are flagged as unparsed and
skipped, so the validator never silently false-positives on logic it
doesn't fully understand.
"""

import argparse
import csv
import importlib.util
import re
import sys
from pathlib import Path

MDC_CODES = {'-666', '-777', '-888', '-999'}

CLAUSE_RE = re.compile(r"\[(\w+)(?:\((-?\w+)\))?\]\s*=\s*'([^']*)'")


def parse_branching(expr):
    """Return list of (field, option, value) OR-clauses, or None if unparseable."""
    if not expr or not expr.strip():
        return []
    s = expr.strip()
    lower = s.lower()
    # We don't model AND / NOT-EQUAL — bail out.
    if ' and ' in lower or '<>' in s:
        return None
    parts = re.split(r'(?i)\s+or\s+', s)
    clauses = []
    for p in parts:
        m = CLAUSE_RE.search(p)
        if not m:
            return None
        field, opt, val = m.group(1), m.group(2), m.group(3)
        clauses.append((field, opt, val))
    return clauses


def is_blank(v):
    return v is None or str(v).strip() == ''


def is_blank_or_mdc(v):
    return is_blank(v) or str(v).strip() in MDC_CODES


def load_dd(path):
    """Return (fields, record_id_field). Fields is a list of dicts."""
    fields = []
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            fields.append({
                'name': row['Variable / Field Name'],
                'type': row['Field Type'],
                'branching': row.get('Branching Logic (Show field only if...)', ''),
            })
    record_id_field = fields[0]['name'] if fields else 'record_id'
    return fields, record_id_field


def check_branching(fields, rows, record_id_field, issues):
    """Verify every branched field is blank/MDC when its parent condition is false."""
    unparsed = []
    for f in fields:
        clauses = parse_branching(f['branching'])
        if clauses is None:
            unparsed.append((f['name'], f['branching']))
            continue
        if not clauses:
            continue
        for r in rows:
            rid = r.get(record_id_field, '?')
            parent_true = False
            for field, opt, val in clauses:
                if opt is not None:
                    col = f'{field}___{opt}'
                    actual = r.get(col, '')
                else:
                    actual = r.get(field, '')
                if str(actual).strip() == str(val).strip():
                    parent_true = True
                    break
            if parent_true:
                continue
            # Parent false -> this field should be blank/MDC
            child = f['name']
            if f['type'] == 'checkbox':
                set_opts = [
                    col.split('___', 1)[1]
                    for col in r.keys()
                    if col.startswith(child + '___') and str(r[col]).strip() == '1'
                ]
                if set_opts:
                    issues.append({
                        'record_id': rid, 'field': child, 'severity': 'error',
                        'note': f"branching parent false but checkbox bits set: {set_opts}",
                    })
            else:
                v = r.get(child, '')
                if not is_blank_or_mdc(v):
                    issues.append({
                        'record_id': rid, 'field': child, 'severity': 'error',
                        'note': f"branching parent false but value={v!r}",
                    })
    return unparsed


def load_semantic_module(path):
    spec = importlib.util.spec_from_file_location('semantic_check', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, 'check'):
        raise SystemExit(f"semantic module {path} must define check(rows, issues)")
    return mod.check


def write_report(report_path, dd_path, import_path, rows, issues, unparsed):
    n_err = sum(1 for i in issues if i['severity'] == 'error')
    n_warn = sum(1 for i in issues if i['severity'] == 'warn')
    L = []
    L.append('# REDCap Import Validation Report')
    L.append('')
    L.append(f'- DD: `{Path(dd_path).name}`')
    L.append(f'- Import: `{Path(import_path).name}` ({len(rows)} records, {len(rows[0]) if rows else 0} columns)')
    L.append(f'- Errors: **{n_err}**, Warnings: **{n_warn}**')
    L.append('')
    if unparsed:
        L.append('## Branching expressions skipped (parser too simple)')
        L.append('')
        for name, expr in unparsed:
            L.append(f'- `{name}`: `{expr}`')
        L.append('')
    L.append('## Issues')
    L.append('')
    if not issues:
        L.append('_None._')
    else:
        L.append('| record_id | field | severity | note |')
        L.append('|---|---|---|---|')
        for i in sorted(issues, key=lambda x: (x['severity'] != 'error', str(x['record_id']))):
            L.append(f"| {i['record_id']} | `{i['field']}` | {i['severity']} | {i['note']} |")
    Path(report_path).write_text('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('dd_csv', help='Path to the REDCap data dictionary CSV')
    ap.add_argument('import_csv', help='Path to the import-ready CSV to validate')
    ap.add_argument('--semantic', help='Optional Python file defining check(rows, issues) for study-specific rules')
    ap.add_argument('--report', help='Optional path to write a Markdown report')
    args = ap.parse_args()

    fields, record_id_field = load_dd(args.dd_csv)
    with open(args.import_csv, newline='') as f:
        rows = list(csv.DictReader(f))

    issues = []
    # REDCap rejects checkbox columns suffixed with negative MDC codes
    # (___-666 / ___-777 / ___-888 / ___-999) — it strips the minus and
    # then can't find the resulting field. Flag any present.
    if rows:
        bad_mdc_cols = [c for c in rows[0].keys() if any(c.endswith(suf) for suf in ('___-666', '___-777', '___-888', '___-999'))]
        for c in bad_mdc_cols:
            issues.append({
                'record_id': '(header)', 'field': c, 'severity': 'error',
                'note': "REDCap will reject this column — drop checkbox columns for negative MDC codes",
            })
    # Flag any MDC value written from ingest. Source-missing data should be
    # blank in the import; MDC codes are reserved for affirmative missingness
    # picked at data-entry time.
    MDC_VALUES = {'-666', '-777', '-888', '-999', '06-06-6666', '07-07-7777', '08-08-8888', '09-09-9999'}
    for r in rows:
        rid = r.get(record_id_field, '?')
        for col, val in r.items():
            if str(val).strip() in MDC_VALUES:
                issues.append({
                    'record_id': rid, 'field': col, 'severity': 'warn',
                    'note': f"MDC value {val!r} in import — prefer leaving blank; MDC is for chart-review entry only",
                })
    unparsed = check_branching(fields, rows, record_id_field, issues)

    if args.semantic:
        semantic_check = load_semantic_module(args.semantic)
        semantic_check(rows, issues)

    n_err = sum(1 for i in issues if i['severity'] == 'error')
    n_warn = sum(1 for i in issues if i['severity'] == 'warn')

    if args.report:
        write_report(args.report, args.dd_csv, args.import_csv, rows, issues, unparsed)

    # Console summary
    print(f'{len(rows)} records, {n_err} errors, {n_warn} warnings, {len(unparsed)} branching expressions skipped')
    if unparsed:
        print('Skipped:')
        for name, expr in unparsed:
            print(f'  - {name}: {expr}')
    if issues:
        print()
        for i in sorted(issues, key=lambda x: (x['severity'] != 'error', str(x['record_id']))):
            print(f"  [{i['severity']:5}] {i['record_id']:>4} {i['field']:30} {i['note']}")

    return 1 if n_err else 0


if __name__ == '__main__':
    sys.exit(main())
