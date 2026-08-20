*! table1.do -- Table 1: demographics by site, for the SYN synthetic cohort.
*==============================================================================
* Study   : SYN -- Synthetic Colorectal Cohort (SYNTHETIC TEST STUDY)
* Inputs  : ../records.csv           the REDCap record export (raw codes)
*           ../datadictionary.csv    the codebook -- labels, types, choice maps
* Outputs : <out>/table1.csv         one tidy Table 1
* Author  : ARGO toolkit fixtures    Date: 2026-08-20
* Assumes : one row per participant; redcap_data_access_group is the site;
*           MDC codes (-666/-777/-888/-999, and 666) are missing, not values;
*           exactly the sites present in the export (discovered, not hardcoded).
*
* REFERENCE ONLY -- NOT AUTOMATICALLY TESTED
* ------------------------------------------
* Stata needs a licence and has no headless CI runner here, so unlike table1.py
* and table1.R this script is not executed by tests/test_analysis_parity.py
* (that test asserts only that this file exists). It is the third leg of the
* three-language parity reference: it is written to produce the SAME numbers as
* table1.py's committed output, expected_table1.csv, and should be diffed
* against that file by hand on any machine that does have Stata.
*
* It is also a worked example of what a run-analysis Stata script should look
* like: the header block above, inputs read and never modified, commented
* sections, one command from start to finish.
*
* Run:
*   stata -b do table1.do "/path/to/outdir"
* or, from inside Stata, from this file's directory:
*   do table1.do "./out"
*==============================================================================

version 14
clear all
set more off

*------------------------------------------------------------------------------
* Arguments and paths
*------------------------------------------------------------------------------
* Stata has no argument parser; the output directory is the single positional
* argument. Inputs sit one directory up, next to the rest of the fixture.

local out `1'
if ("`out'" == "") {
    display as error "usage: do table1.do <output directory>"
    exit 198
}
capture mkdir "`out'"

local records    "../records.csv"
local dictionary "../datadictionary.csv"

*------------------------------------------------------------------------------
* Study-specific choices, stated once (must match table1.py exactly)
*------------------------------------------------------------------------------

local site_field   "redcap_data_access_group"
local continuous   "age"
* histology_grade is not a demographic; it is here because it is the only field
* carrying both engineered blanks and MDC sentinels, so it exercises the
* missing-data path.
local categoricals "sex education marital_status tobacco_use histology_grade"

* Missing-data codes. REDCap stores these as ordinary values, so they must be
* removed explicitly or they silently poison every mean.
local mdc `""-666" "-777" "-888" "-999" "666""'

local decimals 2

*==============================================================================
* 1. Read the data dictionary and build the code -> label maps
*==============================================================================
* REDCap encodes choices as "1, Male | 2, Female". yes/no fields carry no choice
* string at all, so they get the implicit 0 = No / 1 = Yes map -- a detail that
* is easy to miss and produces an empty table when missed.
*
* The maps are held in global macros because they must survive the `clear` that
* loading the records does: $codes_<field> is the ordered code list and
* $lab_<field>_<code> is one label.

import delimited using "`dictionary'", varnames(1) stringcols(_all) clear

local nfields = _N
forvalues i = 1/`nfields' {
    local fname = field_name[`i']
    local ftype = field_type[`i']

    if ("`ftype'" == "yesno") {
        global codes_`fname' "0 1"
        global lab_`fname'_0 "No"
        global lab_`fname'_1 "Yes"
        continue
    }
    if !inlist("`ftype'", "radio", "dropdown", "checkbox") continue

    local raw = select_choices_or_calculations[`i']
    if (trim("`raw'") == "") continue

    * Walk the "code, label | code, label | ..." string one chunk at a time.
    local codes ""
    while (strpos("`raw'", "|") > 0 | trim("`raw'") != "") {
        local cut = strpos("`raw'", "|")
        if (`cut' > 0) {
            local chunk = substr("`raw'", 1, `cut' - 1)
            local raw   = substr("`raw'", `cut' + 1, .)
        }
        else {
            local chunk "`raw'"
            local raw   ""
        }
        local comma = strpos("`chunk'", ",")
        if (`comma' == 0) continue
        local code  = trim(substr("`chunk'", 1, `comma' - 1))
        local label = trim(substr("`chunk'", `comma' + 1, .))

        * MDC codes are offered as choices on some fields so an RA can record
        * "missing, and here is why". They are NOT categories of the variable
        * and must never become rows of a Table 1 -- they are counted under
        * `missing' instead. Dropping them here also keeps the macro names
        * legal, since a leading "-" cannot appear in a Stata macro name.
        local is_mdc 0
        foreach m of local mdc {
            if ("`code'" == "`m'") local is_mdc 1
        }
        if (`is_mdc') continue

        local codes "`codes' `code'"
        global lab_`fname'_`code' "`label'"
    }
    global codes_`fname' = trim("`codes'")
}

*==============================================================================
* 2. Read the records and mark what is usable
*==============================================================================
* stringcols(_all) keeps every cell exactly as REDCap wrote it. Letting Stata
* guess types is how a leading-zero ID becomes a number and an empty cell
* becomes something we have not yet decided the meaning of.

import delimited using "`records'", varnames(1) stringcols(_all) clear

* A value we may compute on: present, and not a missing-data code.
foreach v of local continuous {
    generate byte use_`v' = trim(`v') != ""
    foreach m of local mdc {
        quietly replace use_`v' = 0 if trim(`v') == "`m'"
    }
    * Numeric copy for the summary statistics, missing where not usable.
    generate double num_`v' = real(`v') if use_`v'
}
foreach v of local categoricals {
    generate byte use_`v' = trim(`v') != ""
    foreach m of local mdc {
        quietly replace use_`v' = 0 if trim(`v') == "`m'"
    }
}

*==============================================================================
* 3. Columns: one per site, discovered from the data, plus "overall"
*==============================================================================

quietly levelsof `site_field', local(sites) clean
local columns ""
foreach s of local sites {
    local columns "`columns' `s'"
}
local columns "`columns' overall"

*==============================================================================
* 4. Write the table
*==============================================================================
* Written straight out as CSV with file write rather than assembled as a
* dataset: the table is a mix of counts and percentages in the same cells, and
* forcing it through a Stata dataset would mean either losing the formatting or
* inventing a wide layout that neither of the other two scripts uses.
*
* Every cell is numeric text: counts as integers, everything else fixed to
* `decimals' places. Stata's string(x, "%9.2f") rounds through C printf, as do
* Python's format() and R's sprintf() -- which is what lets the three scripts
* agree to the last digit.

capture file close fh
file open fh using "`out'/table1.csv", write replace text

file write fh "variable,level,statistic"
foreach c of local columns {
    file write fh ",`c'"
}
file write fh _n

* --- 4a. how many records are in each column ---------------------------------
file write fh "records,,n"
foreach c of local columns {
    if ("`c'" == "overall") local cond "1"
    else local cond `"`site_field' == "`c'""'
    quietly count if `cond'
    file write fh ",`r(N)'"
}
file write fh _n

* --- 4b. the continuous variable ---------------------------------------------
* Non-missing count, missing count, then mean and SD over the non-missing.
* summarize reports the SAMPLE standard deviation (n-1 denominator), matching
* R's sd() and table1.py's explicit sample SD.

foreach stat in n missing mean sd {
    file write fh "`continuous',,`stat'"
    foreach c of local columns {
        if ("`c'" == "overall") local cond "1"
        else local cond `"`site_field' == "`c'""'

        quietly count if `cond'
        local total = r(N)
        quietly count if `cond' & use_`continuous'
        local n_ok = r(N)

        if ("`stat'" == "n")       local cell "`n_ok'"
        if ("`stat'" == "missing") local cell = `total' - `n_ok'
        if inlist("`stat'", "mean", "sd") {
            quietly summarize num_`continuous' if `cond'
            if ("`stat'" == "mean") {
                local cell = cond(r(N) == 0, "", trim(string(r(mean), "%20.`decimals'f")))
            }
            else {
                local cell = cond(r(N) < 2, "", trim(string(r(sd), "%20.`decimals'f")))
            }
        }
        file write fh ",`cell'"
    }
    file write fh _n
}

* --- 4c. the categorical variables -------------------------------------------
* Level order comes from the DATA DICTIONARY, not from the data, so a level
* nobody happens to have still appears (as a zero) and the row order is
* identical in all three languages.

foreach v of local categoricals {
    local codes "${codes_`v'}"
    if ("`codes'" == "") continue

    foreach code of local codes {
        local label "${lab_`v'_`code'}"

        * count row
        file write fh "`v',`label',n"
        foreach c of local columns {
            if ("`c'" == "overall") local cond "1"
            else local cond `"`site_field' == "`c'""'
            quietly count if `cond' & use_`v' & trim(`v') == "`code'"
            file write fh ",`r(N)'"
        }
        file write fh _n

        * percent row -- the denominator is the NON-MISSING count in that
        * column, because "percent of what" is the first question every reader
        * of a Table 1 asks.
        file write fh "`v',`label',pct"
        foreach c of local columns {
            if ("`c'" == "overall") local cond "1"
            else local cond `"`site_field' == "`c'""'
            quietly count if `cond' & use_`v' & trim(`v') == "`code'"
            local k = r(N)
            quietly count if `cond' & use_`v'
            local d = r(N)
            if (`d' == 0) local cell ""
            else local cell = trim(string(100 * `k' / `d', "%20.`decimals'f"))
            file write fh ",`cell'"
        }
        file write fh _n
    }

    * missing row -- blanks and MDC codes together
    file write fh "`v',,missing"
    foreach c of local columns {
        if ("`c'" == "overall") local cond "1"
        else local cond `"`site_field' == "`c'""'
        quietly count if `cond'
        local total = r(N)
        quietly count if `cond' & use_`v'
        local n_ok = r(N)
        local cell = `total' - `n_ok'
        file write fh ",`cell'"
    }
    file write fh _n
}

file close fh

display as text "Table 1 written to `out'/table1.csv"
display as text "Compare by hand against expected_table1.csv -- Stata is not covered by the parity test."
