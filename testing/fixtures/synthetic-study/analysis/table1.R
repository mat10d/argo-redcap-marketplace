#!/usr/bin/env Rscript
# table1.R -- Table 1: demographics by site, for the SYN synthetic cohort.
#
# Study   : SYN -- Synthetic Colorectal Cohort (SYNTHETIC TEST STUDY)
# Inputs  : ../records.csv           the REDCap record export (raw codes)
#           ../datadictionary.csv    the codebook -- labels, types, choice maps
# Outputs : <--out>/table1.csv       one tidy Table 1
# Author  : ARGO toolkit fixtures    Date: 2026-08-20
# Assumes : one row per participant; `redcap_data_access_group` is the site;
#           MDC codes (-666/-777/-888/-999, and 666) are missing, not values.
#
# This is the R half of a three-language PARITY REFERENCE. table1.py (the
# golden copy), table1.R and table1.do must all produce byte-identical numbers
# from the same two input files. tests/test_analysis_parity.py compares this
# script's output against expected_table1.csv whenever Rscript is installed.
#
# It is also a worked example of what a run-analysis R script should look like:
# a header block like the one above, inputs read from disk and never modified,
# commented sections, one command from start to finish.
#
# Base R only -- no tidyverse, no data.table. An analyst on a fresh machine
# should be able to run this with nothing but R itself.
#
# Run:
#   Rscript table1.R --out ./out

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

args <- commandArgs(trailingOnly = TRUE)
here <- dirname(normalizePath(sub("^--file=", "",
  grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)[1])))

get_arg <- function(name, default) {
  hit <- which(args == name)
  if (length(hit) == 1 && length(args) > hit) args[hit + 1] else default
}

records_path <- get_arg("--records", file.path(here, "..", "records.csv"))
dict_path    <- get_arg("--dictionary", file.path(here, "..", "datadictionary.csv"))
out_dir      <- get_arg("--out", NA)
if (is.na(out_dir)) stop("--out <directory> is required")

# ---------------------------------------------------------------------------
# Study-specific choices, stated once (must match table1.py exactly)
# ---------------------------------------------------------------------------

SITE_FIELD  <- "redcap_data_access_group"
CONTINUOUS  <- "age"
# histology_grade is not a demographic; it is here because it is the only field
# carrying both engineered blanks and MDC sentinels, so it exercises the
# missing-data path.
CATEGORICALS <- c("sex", "education", "marital_status", "tobacco_use",
                  "histology_grade")

# Missing-data codes. REDCap stores these as ordinary values; they must be
# removed explicitly or they silently poison every mean.
MDC <- c("-666", "-777", "-888", "-999", "666")

DECIMALS <- 2

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
# colClasses = "character" and na.strings = character(0) keep every cell exactly
# as REDCap wrote it. Letting R guess types is how a leading-zero ID becomes a
# number and an empty cell becomes NA before we have decided what empty means.

read_redcap <- function(path) {
  read.csv(path, colClasses = "character", na.strings = character(0),
           check.names = FALSE, stringsAsFactors = FALSE)
}

records <- read_redcap(records_path)
dd      <- read_redcap(dict_path)

# {field: named vector of code -> label} from the data dictionary.
# REDCap encodes choices as "1, Male | 2, Female". yes/no fields carry no choice
# string at all, so they get the implicit 0 = No / 1 = Yes map.
choice_map <- list()
for (i in seq_len(nrow(dd))) {
  field <- dd$field_name[i]
  ftype <- dd$field_type[i]
  if (ftype == "yesno") {
    choice_map[[field]] <- c("0" = "No", "1" = "Yes")
    next
  }
  raw <- dd$select_choices_or_calculations[i]
  if (!(ftype %in% c("radio", "dropdown", "checkbox")) || !nzchar(trimws(raw))) next
  mapping <- c()
  for (chunk in strsplit(raw, "|", fixed = TRUE)[[1]]) {
    if (!grepl(",", chunk, fixed = TRUE)) next
    code  <- trimws(sub(",.*$", "", chunk))
    label <- trimws(sub("^[^,]*,", "", chunk))
    mapping[code] <- label
  }
  choice_map[[field]] <- mapping
}

# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

# A value we may compute on: present, and not a missing-data code.
usable <- function(v) {
  v <- trimws(v)
  ifelse(nzchar(v) & !(v %in% MDC), v, NA_character_)
}

# Format: counts as integers, everything else fixed to DECIMALS places.
# sprintf goes through C printf in R, Python and Stata alike, so the three
# scripts round identically -- which is the whole point of the parity check.
fmt <- function(value, is_count) {
  if (length(value) == 0 || is.na(value)) return("")
  if (is_count) return(sprintf("%d", as.integer(value)))
  sprintf(paste0("%.", DECIMALS, "f"), value)
}

# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

sites   <- sort(unique(records[[SITE_FIELD]][nzchar(trimws(records[[SITE_FIELD]]))]))
columns <- c(sites, "overall")

# Each column is a subset of the records; "overall" is all of them.
subsets <- list()
for (s in sites) subsets[[s]] <- records[records[[SITE_FIELD]] == s, , drop = FALSE]
subsets[["overall"]] <- records

rows <- list()
add <- function(variable, level, statistic, per_column, is_count) {
  row <- list(variable = variable, level = level, statistic = statistic)
  for (cl in columns) row[[cl]] <- fmt(per_column[[cl]], is_count)
  rows[[length(rows) + 1]] <<- row
}

# --- 1. how many records are in each column --------------------------------
counts <- setNames(lapply(columns, function(cl) nrow(subsets[[cl]])), columns)
add("records", "", "n", counts, TRUE)

# --- 2. the continuous variable --------------------------------------------
vals <- setNames(lapply(columns, function(cl) {
  v <- usable(subsets[[cl]][[CONTINUOUS]])
  as.numeric(v[!is.na(v)])
}), columns)

add(CONTINUOUS, "", "n",
    setNames(lapply(columns, function(cl) length(vals[[cl]])), columns), TRUE)
add(CONTINUOUS, "", "missing",
    setNames(lapply(columns, function(cl) nrow(subsets[[cl]]) - length(vals[[cl]])),
             columns), TRUE)
# mean() and sd() -- sd() uses the n-1 denominator, matching table1.py's
# explicit sample SD and Stata's summarize.
add(CONTINUOUS, "", "mean",
    setNames(lapply(columns, function(cl) {
      if (length(vals[[cl]]) == 0) NA_real_ else mean(vals[[cl]])
    }), columns), FALSE)
add(CONTINUOUS, "", "sd",
    setNames(lapply(columns, function(cl) {
      if (length(vals[[cl]]) < 2) NA_real_ else sd(vals[[cl]])
    }), columns), FALSE)

# --- 3. the categorical variables ------------------------------------------
for (field in CATEGORICALS) {
  mapping <- choice_map[[field]]
  if (is.null(mapping)) next
  # Level order comes from the DATA DICTIONARY, not from the data, so a level
  # nobody happens to have still appears (as a zero) and the row order is
  # identical in all three languages.
  #
  # MDC codes are offered as choices on some fields so an RA can record
  # "missing, and here is why". They are NOT categories of the variable and
  # must never become rows of a Table 1 -- they are counted under `missing`.
  codes <- names(mapping)[!(names(mapping) %in% MDC)]

  present    <- setNames(lapply(columns, function(cl) usable(subsets[[cl]][[field]])), columns)
  nonmissing <- setNames(lapply(columns, function(cl) present[[cl]][!is.na(present[[cl]])]), columns)

  for (code in codes) {
    n_level <- setNames(lapply(columns, function(cl) sum(nonmissing[[cl]] == code)), columns)
    add(field, unname(mapping[code]), "n", n_level, TRUE)
    # Percent denominator is the non-missing count in that column.
    add(field, unname(mapping[code]), "pct",
        setNames(lapply(columns, function(cl) {
          d <- length(nonmissing[[cl]])
          if (d == 0) NA_real_ else 100 * n_level[[cl]] / d
        }), columns), FALSE)
  }
  add(field, "", "missing",
      setNames(lapply(columns, function(cl) {
        length(present[[cl]]) - length(nonmissing[[cl]])
      }), columns), TRUE)
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

table1 <- do.call(rbind, lapply(rows, function(r) as.data.frame(r, stringsAsFactors = FALSE)))
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
out_path <- file.path(out_dir, "table1.csv")
write.csv(table1, out_path, row.names = FALSE, quote = FALSE, na = "")

cat(sprintf("Table 1 written to %s  (%d rows, %d columns of results)\n",
            out_path, nrow(table1), length(columns)))
