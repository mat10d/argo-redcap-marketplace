# core.R -- the ARGO analysis library: loading a study, missing data, branching.
#
# Part of the run-analysis skill. Files here are SOURCED, not installed:
#
#     source("lib/R/argo_analysis/core.R")
#
# Base R only. An analyst on a fresh machine must be able to run this with
# nothing but R itself -- no tidyverse, no data.table, no install step.
#
# This is the R half of a two-language library. lib/python/argo_analysis/core.py
# is the other half; the function names, the output shapes and the rounding are
# deliberately identical, so a study can be written in either language and get
# the same numbers.
#
# WHAT IS IN HERE
#   load_study(export_csv, dictionary_csv)  read an export + its codebook
#   apply_missing(study)                    turn MDC codes into missing values
#   labels(study, field)                    code -> label, from the codebook
#   applicable(study, field)                did this field's branching fire?
#   denominator(study, field)               how many records it applies to
#
# Two of those names (labels, hist in figures.R) shadow base R functions once
# sourced. That is on purpose -- the contract names come first -- and this
# library never calls the base versions.

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Missing-data codes (MDC). REDCap stores these as ordinary values, so they must
# be removed explicitly or they silently poison every mean. 666 is included
# because some older ARGO studies used it before the four-code convention.
ARGO_MDC <- c("-666", "-777", "-888", "-999", "666")

# Every non-count statistic is rounded here, in both languages.
ARGO_DECIMALS <- 2

# The 18 columns of a REDCap data dictionary, API spelling.
ARGO_DD_COLUMNS <- c(
  "field_name", "form_name", "section_header", "field_type", "field_label",
  "select_choices_or_calculations", "field_note",
  "text_validation_type_or_show_slider_number", "text_validation_min",
  "text_validation_max", "identifier", "branching_logic", "required_field",
  "custom_alignment", "question_number", "matrix_group_name", "matrix_ranking",
  "field_annotation"
)

# The same 18 columns as the website spells them ("Download Data Dictionary"),
# so a user who never got an access key can hand us the file they downloaded.
ARGO_DD_HEADER_MAP <- c(
  "Variable / Field Name"                      = "field_name",
  "Form Name"                                  = "form_name",
  "Section Header"                             = "section_header",
  "Field Type"                                 = "field_type",
  "Field Label"                                = "field_label",
  "Choices, Calculations, OR Slider Labels"    = "select_choices_or_calculations",
  "Field Note"                                 = "field_note",
  "Text Validation Type OR Show Slider Number" = "text_validation_type_or_show_slider_number",
  "Text Validation Min"                        = "text_validation_min",
  "Text Validation Max"                        = "text_validation_max",
  "Identifier?"                                = "identifier",
  "Branching Logic (Show field only if...)"    = "branching_logic",
  "Required Field?"                            = "required_field",
  "Custom Alignment"                           = "custom_alignment",
  "Question Number (surveys only)"             = "question_number",
  "Matrix Group Name"                          = "matrix_group_name",
  "Matrix Ranking?"                            = "matrix_ranking",
  "Field Annotation"                           = "field_annotation"
)

# Field types whose values are numbers, not categories.
ARGO_NUMERIC_VALIDATIONS <- c("integer", "number", "number_1dp", "number_2dp",
                              "number_3dp", "number_4dp", "number_comma_decimal")

# Branching conditions we could not read this session. Reported the first time
# each one is seen, so the operator finds out the parser needs extending instead
# of quietly losing coverage.
ARGO_UNPARSEABLE <- new.env(parent = emptyenv())

# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------

# colClasses = "character" and na.strings = character(0) keep every cell exactly
# as REDCap wrote it. Letting R guess types is how a leading-zero ID becomes a
# number and an empty cell becomes NA before we have decided what empty means.
argo_read_csv <- function(path) {
  if (!file.exists(path)) {
    stop(sprintf(paste0("I could not find this file:\n  %s\n",
                        "Check the name and the folder, then try again."), path),
         call. = FALSE)
  }
  df <- utils::read.csv(path, colClasses = "character", na.strings = character(0),
                        check.names = FALSE, stringsAsFactors = FALSE)
  if (ncol(df) > 0) {
    # Excel and some REDCap downloads put an invisible marker on the first
    # header. Left in place it makes the first column impossible to find.
    names(df)[1] <- sub("^\uFEFF", "", names(df)[1])
  }
  df
}

# Accept either header style and always hand the rest of the library the API
# spelling, with all 18 columns present (missing ones as empty text).
argo_normalise_dictionary <- function(dd) {
  if (!("field_name" %in% names(dd))) {
    hit <- match(names(dd), names(ARGO_DD_HEADER_MAP))
    names(dd)[!is.na(hit)] <- unname(ARGO_DD_HEADER_MAP[hit[!is.na(hit)]])
  }
  if (!("field_name" %in% names(dd))) {
    stop(paste0("This does not look like a data dictionary: it has no column of ",
                "field names.\nExpected either 'field_name' (an access-key export) ",
                "or 'Variable / Field Name'\n(the file the website gives you under ",
                "Download Data Dictionary)."), call. = FALSE)
  }
  for (col in ARGO_DD_COLUMNS) {
    if (!(col %in% names(dd))) dd[[col]] <- rep("", nrow(dd))
    dd[[col]][is.na(dd[[col]])] <- ""
  }
  dd
}

# ---------------------------------------------------------------------------
# load_study
# ---------------------------------------------------------------------------

#' Read an export and its codebook into one object.
#'
#' Returns a list with:
#'   data      the export, raw codes, one row per record, every column text
#'   dd        the data dictionary, 18 API-spelled columns
#'   id_field  the record identifier -- the FIRST field in the codebook, which
#'             is how REDCap defines it
#'   sites     "redcap_data_access_group" when the export has one, else NULL
#'   raw       the export before apply_missing() touched it. Branching logic is
#'             always evaluated against this, because REDCap itself shows and
#'             hides fields using the stored codes, sentinels included.
load_study <- function(export_csv, dictionary_csv) {
  data <- argo_read_csv(export_csv)
  dd   <- argo_normalise_dictionary(argo_read_csv(dictionary_csv))
  if (nrow(dd) == 0) {
    stop("The data dictionary is empty -- there are no fields to analyse.", call. = FALSE)
  }
  if (nrow(data) == 0) {
    stop("The export is empty -- there are no records to analyse.", call. = FALSE)
  }
  study <- list(
    data     = data,
    raw      = data,
    dd       = dd,
    id_field = dd$field_name[1],
    sites    = if ("redcap_data_access_group" %in% names(data))
                 "redcap_data_access_group" else NULL
  )
  class(study) <- "argo_study"
  study
}

print.argo_study <- function(x, ...) {
  cat(sprintf("ARGO study: %d records, %d fields in the codebook\n",
              nrow(x$data), nrow(x$dd)))
  cat(sprintf("  record identifier : %s\n", x$id_field))
  cat(sprintf("  sites             : %s\n",
              if (is.null(x$sites)) "none (no data access groups in this export)" else x$sites))
  invisible(x)
}

# ---------------------------------------------------------------------------
# apply_missing
# ---------------------------------------------------------------------------

#' Turn MDC sentinels and blanks into missing values, in EVERY field.
#'
#' "Blanks stay blank" is an ARGO rule: we never invent a reason for a missing
#' value. This goes the other way -- a code that MEANS missing must stop being
#' counted as if it were an answer.
apply_missing <- function(study) {
  if (is.null(study$raw)) study$raw <- study$data
  d <- study$data
  for (nm in names(d)) {
    v <- as.character(d[[nm]])
    v[is.na(v)] <- ""
    t <- trimws(v)
    v[t == "" | t %in% ARGO_MDC] <- NA_character_
    d[[nm]] <- v
  }
  study$data <- d
  study
}

# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------

argo_dd_row <- function(study, field) {
  hit <- which(study$dd$field_name == field)
  if (length(hit) == 0) return(NULL)
  study$dd[hit[1], , drop = FALSE]
}

#' The code -> label map for a field, without complaining about fields that were
#' never in the codebook. REDCap's own columns (redcap_data_access_group and
#' friends) have no codebook entry and are asked about constantly.
argo_choice_map <- function(study, field) {
  row <- argo_dd_row(study, field)
  if (is.null(row)) return(character(0))
  ftype <- row$field_type[1]
  if (identical(ftype, "yesno"))     return(c("0" = "No", "1" = "Yes"))
  if (identical(ftype, "truefalse")) return(c("0" = "False", "1" = "True"))
  raw <- row$select_choices_or_calculations[1]
  if (!(ftype %in% c("radio", "dropdown", "checkbox")) || !nzchar(trimws(raw))) {
    return(character(0))
  }
  out <- character(0)
  for (chunk in strsplit(raw, "|", fixed = TRUE)[[1]]) {
    if (!grepl(",", chunk, fixed = TRUE)) next
    code  <- trimws(sub(",.*$", "", chunk))
    label <- trimws(sub("^[^,]*,", "", chunk))
    out[code] <- label
  }
  out
}

#' The code -> label map for a field, in CODEBOOK order.
#'
#' REDCap encodes choices as "1, Male | 2, Female". yes/no and true/false fields
#' carry no choice string at all, so they get their implicit map -- a detail that
#' is easy to miss and produces an empty table when missed.
#'
#' Returns a named character vector (names = codes). character(0) when the field
#' has no choices, with a warning when the field is not in the codebook at all --
#' which is nearly always a typo worth hearing about.
labels <- function(study, field) {
  if (is.null(argo_dd_row(study, field))) {
    warning(sprintf("There is no field called '%s' in the codebook.", field), call. = FALSE)
    return(character(0))
  }
  argo_choice_map(study, field)
}

# REDCap's own columns have no codebook entry, so they have no label either.
# These are the ones an analyst actually groups or splits by.
ARGO_SYSTEM_LABELS <- c(
  "redcap_data_access_group" = "Data access group",
  "redcap_event_name"        = "Event",
  "redcap_repeat_instrument" = "Repeating instrument",
  "redcap_repeat_instance"   = "Repeat number"
)

#' The human label of a field, falling back to its name.
argo_field_label <- function(study, field) {
  row <- argo_dd_row(study, field)
  if (is.null(row) || !nzchar(trimws(row$field_label[1]))) {
    if (field %in% names(ARGO_SYSTEM_LABELS)) return(unname(ARGO_SYSTEM_LABELS[[field]]))
    return(field)
  }
  trimws(gsub("[[:space:]]+", " ", row$field_label[1]))
}

# ---------------------------------------------------------------------------
# Branching logic
# ---------------------------------------------------------------------------
#
# Ported clause for clause from the QA worklist builder's evaluator, which is
# the tool that has met real REDCap projects. One clause pattern, and it must
# accept everything the Designer actually emits -- broader than it first looks:
#
#   [field] = 'value'   quoted, the form most documentation shows
#   [field] = 1         UNQUOTED -- what REDCap writes for numeric codes, and by
#                       far the most common form in practice. A stricter pattern
#                       that demanded quotes silently dropped 28% of branching
#                       fields on one live cohort and 70% on another.
#   [field(2)] = 1      a single checkbox option
#   [age] >= 18         numeric comparison
#
# Anything else is reported, and the field is treated as applying to everyone --
# never silently dropped.

ARGO_CLAUSE_RE <- paste0(
  "^\\s*\\[(?<field>[a-zA-Z0-9_]+)(?:\\((?<choice>-?\\w+)\\))?\\]\\s*",
  "(?<op><=|>=|<>|!=|=|<|>)\\s*",
  "(?:'(?<sq>[^']*)'|\"(?<dq>[^\"]*)\"|(?<bare>[^\\s'\"]+))\\s*$"
)

#' (field, choice, op, value) for one clause, or NULL when it cannot be read.
argo_clause_parts <- function(clause) {
  m <- regexpr(ARGO_CLAUSE_RE, clause, perl = TRUE)
  if (m[1] == -1) return(NULL)
  starts <- attr(m, "capture.start")
  lens   <- attr(m, "capture.length")
  nms    <- attr(m, "capture.names")
  grab <- function(name) {
    i <- match(name, nms)
    # start == 0 means the group did not take part in the match; a group that
    # matched the empty string has a real start and a length of 0.
    if (starts[i] <= 0) return(NULL)
    substring(clause, starts[i], starts[i] + lens[i] - 1)
  }
  value <- grab("sq")
  if (is.null(value)) value <- grab("dq")
  if (is.null(value)) value <- grab("bare")
  if (is.null(value)) return(NULL)
  choice <- grab("choice")
  list(field  = grab("field"),
       choice = if (is.null(choice)) "" else choice,
       op     = grab("op"),
       value  = value)
}

#' The export column a clause refers to (checkbox options get their own column).
argo_clause_column <- function(field, choice) {
  if (!nzchar(choice)) return(field)
  # REDCap writes a negative checkbox code as an extra underscore: [f(-1)] is
  # stored in f____1.
  if (substr(choice, 1, 1) == "-") paste0(field, "____", substring(choice, 2))
  else paste0(field, "___", choice)
}

#' One clause, evaluated over every record at once.
#' TRUE / FALSE per record; NA where we could not decide.
argo_clause_vector <- function(clause, data) {
  n <- nrow(data)
  parts <- argo_clause_parts(clause)
  if (is.null(parts)) return(rep(NA, n))
  col <- argo_clause_column(parts$field, parts$choice)
  actual <- if (col %in% names(data)) as.character(data[[col]]) else rep("", n)
  actual[is.na(actual)] <- ""
  actual <- trimws(actual)
  val <- trimws(parts$value)

  if (parts$op %in% c("=", "<>", "!=")) {
    equal <- actual == val
    return(if (parts$op == "=") equal else !equal)
  }

  # Numeric comparison. A BLANK value fails the comparison, and that is a
  # definite answer, not an unknown one: REDCap evaluates `[x] >= 1` with x
  # empty as false and hides the field, so we match it. Calling blanks
  # "uncertain" instead would flood every worklist and every denominator.
  res   <- rep(NA, n)
  blank <- actual == ""
  res[blank] <- FALSE
  left  <- suppressWarnings(as.numeric(actual))
  right <- suppressWarnings(as.numeric(val))
  ok <- !blank & !is.na(left) & !is.na(right)
  if (any(ok)) {
    res[ok] <- switch(parts$op,
                      "<"  = left[ok] <  right,
                      ">"  = left[ok] >  right,
                      "<=" = left[ok] <= right,
                      ">=" = left[ok] >= right)
  }
  res
}

#' Evaluate a whole branching condition over every record.
#'
#' Returns list(applies = logical, certain = logical).
#'
#' `certain` is FALSE where some part of the logic could not be understood. In
#' that case we say the field DOES apply -- never silently drop a field just
#' because we could not read its condition -- but the caller can say so, and the
#' condition is reported.
argo_evaluate_branching <- function(logic, data) {
  n <- nrow(data)
  if (is.null(logic) || is.na(logic) || !nzchar(trimws(logic))) {
    return(list(applies = rep(TRUE, n), certain = rep(TRUE, n)))
  }
  branches <- lapply(strsplit(logic, "(?i)\\s+OR\\s+", perl = TRUE)[[1]], function(part) {
    lapply(strsplit(part, "(?i)\\s+AND\\s+", perl = TRUE)[[1]],
           argo_clause_vector, data = data)
  })

  applies <- logical(n)
  certain <- rep(TRUE, n)
  for (i in seq_len(n)) {
    any_unparseable <- FALSE
    satisfied <- FALSE
    for (branch in branches) {
      ok <- TRUE
      branch_unparseable <- FALSE
      for (clause_values in branch) {
        r <- clause_values[i]
        if (is.na(r)) {
          # Unknown -- do not let it decide the branch either way.
          branch_unparseable <- TRUE
          any_unparseable <- TRUE
          next
        }
        if (!r) { ok <- FALSE; break }
      }
      if (ok && !branch_unparseable) { satisfied <- TRUE; break }
    }
    if (satisfied) {
      applies[i] <- TRUE
    } else if (any_unparseable) {
      applies[i] <- TRUE
      certain[i] <- FALSE
    }
  }
  list(applies = applies, certain = certain)
}

#' Say once per session which condition we could not read.
argo_report_unparseable <- function(logic, field) {
  key <- trimws(logic)
  if (!is.null(ARGO_UNPARSEABLE[[key]])) return(invisible(NULL))
  assign(key, TRUE, envir = ARGO_UNPARSEABLE)
  warning(sprintf(paste0(
    "I could not fully read the branching condition on '%s':\n    %s\n",
    "Every record is being counted as if the field applies to them, so nothing ",
    "is dropped --\nbut the denominator for this field may be too large. ",
    "Check it by hand, and pass this\ncondition on so the tool can be taught to ",
    "read it."), field, key), call. = FALSE)
  invisible(NULL)
}

#' Does this field's branching logic fire, record by record?
#'
#' A field with no branching logic applies to everyone. Evaluated against the
#' export as REDCap stored it, before apply_missing() -- REDCap shows and hides
#' fields using the stored codes.
applicable <- function(study, field) {
  data <- if (!is.null(study$raw)) study$raw else study$data
  row <- argo_dd_row(study, field)
  logic <- if (is.null(row)) "" else row$branching_logic[1]
  result <- argo_evaluate_branching(logic, data)
  if (any(!result$certain)) argo_report_unparseable(logic, field)
  result$applies
}

#' How many records this field applies to -- the denominator to report against.
#'
#' This is the whole point of the applicable-denominator rule: 111 women, not
#' 200 participants, is the denominator for a pregnancy question.
denominator <- function(study, field) {
  sum(applicable(study, field))
}

# ---------------------------------------------------------------------------
# Small shared helpers (used by table1.R, figures.R)
# ---------------------------------------------------------------------------

#' A value we may compute on: present, and not a missing-data code.
argo_usable <- function(v) {
  v <- as.character(v)
  v[is.na(v)] <- ""
  t <- trimws(v)
  ifelse(nzchar(t) & !(t %in% ARGO_MDC), t, NA_character_)
}

#' Counts print as integers, everything else to ARGO_DECIMALS places.
#' sprintf goes through C's printf in R and Python alike, so both languages
#' round identically -- which is the point of having two of them.
argo_format <- function(value, is_count) {
  if (length(value) == 0 || is.null(value) || is.na(value)) return("")
  if (is_count) return(sprintf("%d", as.integer(round(value))))
  sprintf(paste0("%.", ARGO_DECIMALS, "f"), value)
}

#' Is this field a number to average, or a set of categories to count?
#' "continuous", "categorical", or "unsupported".
argo_field_kind <- function(study, field) {
  row <- argo_dd_row(study, field)
  if (is.null(row)) return("unsupported")
  ftype <- row$field_type[1]
  if (ftype %in% c("radio", "dropdown", "yesno", "truefalse", "checkbox")) return("categorical")
  if (ftype %in% c("calc", "slider")) return("continuous")
  if (ftype == "text" &&
      row$text_validation_type_or_show_slider_number[1] %in% ARGO_NUMERIC_VALIDATIONS) {
    return("continuous")
  }
  "unsupported"
}

#' Write a table to CSV with the same quoting rules Python's csv module uses:
#' quote a cell only when it contains a comma, a quote or a line break. Doing it
#' by hand (rather than write.csv) is what lets the R and Python outputs be
#' compared byte for byte.
argo_write_csv <- function(df, path) {
  quote_cell <- function(x) {
    x <- as.character(x)
    x[is.na(x)] <- ""
    needs <- grepl('[,"\r\n]', x)
    x[needs] <- paste0('"', gsub('"', '""', x[needs]), '"')
    x
  }
  dir <- dirname(path)
  if (nzchar(dir) && !dir.exists(dir)) dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  lines <- paste(quote_cell(names(df)), collapse = ",")
  if (nrow(df) > 0) {
    body <- do.call(paste, c(lapply(df, quote_cell), sep = ","))
    lines <- c(lines, body)
  }
  con <- file(path, open = "wb")
  on.exit(close(con))
  writeLines(lines, con, sep = "\n", useBytes = TRUE)
  invisible(path)
}
