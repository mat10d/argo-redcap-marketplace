# excel.R -- one workbook per analysis, in the ARGO house style.
#
#     source("lib/R/argo_analysis/excel.R")
#     write_workbook(list("Table 1" = t1), "out/table1.xlsx",
#                    notes = "Cohort: everyone enrolled by 2026-06-30.")
#
# THE HOUSE STYLE, stated once so every ARGO output looks the same:
#   * one workbook per analysis, one sheet per table
#   * a bold header row, frozen, so the column names stay visible while scrolling
#   * column widths fitted to the contents
#   * statistics written as NUMBERS, not text, so they can be summed, sorted and
#     charted -- and so this workbook and the Python one are the same to Excel;
#     labels and levels stay text
#   * a final "Notes" sheet carrying N, the missing-data rule, the
#     applicable-denominator rule, and which script made the file, when
#
# The Notes sheet is not decoration. A table without its denominators and its
# missing-data rule written down is a table someone will misread six months from
# now -- usually the person who made it.
#
# This is the one module that needs a package. Everything else in the library is
# base R.

ARGO_EXCEL_PACKAGE <- "openxlsx"

#' Stop with an instruction a non-programmer can follow.
argo_require_openxlsx <- function() {
  if (requireNamespace(ARGO_EXCEL_PACKAGE, quietly = TRUE)) return(invisible(TRUE))
  stop(paste0(
    "Writing Excel files needs one extra R add-on, called openxlsx, and it is not\n",
    "installed on this computer. Open R and run this one line, then try again:\n\n",
    '    install.packages("openxlsx")\n\n',
    "It will ask you to pick a download site the first time; any of them is fine.\n",
    "If you would rather not install anything, the same tables can be saved as CSV\n",
    "files instead, which Excel opens directly."), call. = FALSE)
}

#' Excel sheet names cannot be longer than 31 characters or contain : \ / ? * [ ]
argo_safe_sheet_name <- function(name, taken = character(0)) {
  clean <- gsub("[\\\\/?*\\[\\]:]", " ", as.character(name), perl = TRUE)
  clean <- trimws(gsub("[[:space:]]+", " ", clean))
  if (!nzchar(clean)) clean <- "Sheet"
  if (nchar(clean) > 31) clean <- substr(clean, 1, 31)
  base <- clean
  i <- 2
  while (clean %in% taken) {
    suffix <- paste0(" ", i)
    clean <- paste0(substr(base, 1, 31 - nchar(suffix)), suffix)
    i <- i + 1
  }
  clean
}

# Columns whose cells are LABELS, never numbers. A level coded "1" or a variable
# called "2" is still a label: Excel must not right-align it, and nobody should be
# able to sum it. Everything else in a Table 1 is a statistic.
ARGO_LABEL_COLUMNS <- c("variable", "level", "statistic", "notes")

#' Does every value in this column read as a plain number?
#'
#' Column by column, not cell by cell: one non-numeric value anywhere (a "n/a", a
#' footnote marker) and the whole column stays text, so a column never comes out
#' half number and half string. Identifiers are deliberately excluded -- a leading
#' zero ("007") or more than 15 digits means Excel would silently change the value.
argo_all_numeric <- function(x) {
  v <- trimws(as.character(x))
  v <- v[!is.na(v) & nzchar(v)]
  if (!length(v)) return(FALSE)
  if (!all(grepl("^[+-]?([0-9]+\\.?[0-9]*|\\.[0-9]+)([eE][+-]?[0-9]+)?$", v))) return(FALSE)
  if (any(grepl("^[+-]?0[0-9]", v))) return(FALSE)
  if (any(nchar(gsub("[^0-9]", "", v)) > 15)) return(FALSE)
  TRUE
}

#' Statistics go into the workbook as NUMBERS; labels stay text.
#'
#' The R table1 formats every cell to a string so the CSV can be compared with
#' Python's byte for byte. A workbook is not a CSV: a mean stored as "2.50" cannot
#' be summed, sorted, charted or rounded, and the two languages' workbooks were
#' different shapes to Excel. Converted here, at the point of writing, so the
#' printed table and the CSV are untouched.
argo_numeric_cells <- function(tb) {
  for (name in names(tb)) {
    column <- tb[[name]]
    if (!is.character(column) && !is.factor(column)) next
    if (tolower(name) %in% ARGO_LABEL_COLUMNS) next
    if (!argo_all_numeric(column)) next
    values <- trimws(as.character(column))
    values[is.na(values) | !nzchar(values)] <- NA_character_
    tb[[name]] <- suppressWarnings(as.numeric(values))
  }
  tb
}

#' N, read out of a Table 1 if one of the tables is a Table 1.
argo_n_from_tables <- function(tables) {
  for (tb in tables) {
    if (!is.data.frame(tb)) next
    if (!all(c("variable", "statistic") %in% names(tb))) next
    hit <- which(tb$variable == "records" & tb$statistic == "n")
    if (!length(hit)) next
    col <- if ("overall" %in% names(tb)) "overall" else names(tb)[ncol(tb)]
    value <- tb[[col]][hit[1]]
    if (nzchar(as.character(value))) return(as.character(value))
  }
  NULL
}

#' The name of the script that is running, for the provenance line.
argo_calling_script <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  hit <- grep("^--file=", args, value = TRUE)
  if (length(hit)) return(basename(sub("^--file=", "", hit[1])))
  for (i in seq_len(sys.nframe())) {
    f <- sys.frame(i)$ofile
    if (!is.null(f)) return(basename(f))
  }
  "an interactive R session"
}

#' openxlsx writes a "there is a picture on this sheet" link into every sheet
#' even when there is no picture, pointing at a file it never creates. Excel
#' shrugs; strict readers -- openpyxl, which is what the rest of ARGO reads
#' workbooks with -- refuse to open the file at all. Drop the dangling links
#' before saving, but only where the sheet really has no drawing on it.
#'
#' Guarded end to end: if a future openxlsx keeps its innards somewhere else,
#' the workbook is saved exactly as openxlsx made it, which Excel still opens.
argo_drop_dangling_drawing_links <- function(wb) {
  tryCatch({
    rels <- wb$worksheets_rels
    if (!is.list(rels) || !length(rels)) return(FALSE)
    for (i in seq_along(rels)) {
      r <- rels[[i]]
      if (!is.character(r) || !length(r)) next
      has_drawing <- length(wb$drawings) >= i && length(wb$drawings[[i]]) > 0
      has_vml     <- length(wb$vml)      >= i && length(wb$vml[[i]])      > 0
      keep <- rep(TRUE, length(r))
      if (!has_drawing) keep <- keep & !grepl("drawings/drawing", r, fixed = TRUE)
      if (!has_vml)     keep <- keep & !grepl("drawings/vmlDrawing", r, fixed = TRUE)
      wb$worksheets_rels[[i]] <- r[keep]
    }
    TRUE
  }, error = function(e) FALSE)
}

#' Write one workbook in the house style.
#'
#' tables  a NAMED list of data frames: names become sheet names, in order.
#' path    where to write the .xlsx
#' notes   extra lines for the Notes sheet -- say what the cohort was, what was
#'         excluded, anything a reader would otherwise have to guess. The
#'         standing rules and the provenance line are added for you.
#' n       how many records the analysis covers; read out of a Table 1 when it
#'         is left out.
#' script  overrides the detected script name (rarely needed).
write_workbook <- function(tables, path, notes = character(0), n = NULL,
                           script = NULL) {
  argo_require_openxlsx()
  if (!is.list(tables) || !length(tables)) {
    stop("There are no tables to write -- pass a named list, e.g. list(\"Table 1\" = t1).",
         call. = FALSE)
  }
  if (is.null(names(tables)) || any(!nzchar(names(tables)))) {
    stop(paste0("Every table needs a sheet name. Pass them named, like:\n",
                '    write_workbook(list("Table 1" = t1, "By site" = t2), "out/analysis.xlsx")'),
         call. = FALSE)
  }

  wb <- openxlsx::createWorkbook()
  header_style <- openxlsx::createStyle(textDecoration = "bold", halign = "left",
                                        valign = "center", border = "bottom")

  used <- character(0)
  for (i in seq_along(tables)) {
    tb <- tables[[i]]
    if (!is.data.frame(tb)) tb <- as.data.frame(tb, stringsAsFactors = FALSE)
    tb <- argo_numeric_cells(tb)
    sheet <- argo_safe_sheet_name(names(tables)[i], used)
    used <- c(used, sheet)
    openxlsx::addWorksheet(wb, sheet)
    openxlsx::writeData(wb, sheet, tb, headerStyle = header_style)
    openxlsx::freezePane(wb, sheet, firstActiveRow = 2)
    openxlsx::setColWidths(wb, sheet, cols = seq_len(max(1, ncol(tb))), widths = "auto")
  }

  # --- the Notes sheet, always last ----------------------------------------
  if (is.null(n)) n <- argo_n_from_tables(tables)
  lines <- c(
    if (!is.null(n)) sprintf("N = %s records in this analysis.", n),
    as.character(notes),
    paste0("Missing data: blanks and the missing-data codes -666, -777, -888, -999 ",
           "(and 666) are counted as missing. They are never counted as an answer and ",
           "never enter a mean."),
    paste0("Denominators: a field that REDCap only shows to some participants is ",
           "described against those participants -- the applicable denominator -- not ",
           "against the whole cohort. Percentages are of the applicable, non-missing ",
           "records in that column."),
    sprintf("Generated by %s on %s.",
            if (is.null(script)) argo_calling_script() else script,
            format(Sys.Date(), "%Y-%m-%d"))
  )
  lines <- lines[nzchar(lines)]
  notes_sheet <- argo_safe_sheet_name("Notes", used)
  openxlsx::addWorksheet(wb, notes_sheet)
  openxlsx::writeData(wb, notes_sheet,
                      data.frame(Notes = lines, stringsAsFactors = FALSE),
                      headerStyle = header_style)
  openxlsx::freezePane(wb, notes_sheet, firstActiveRow = 2)
  openxlsx::setColWidths(wb, notes_sheet, cols = 1, widths = 110)

  argo_drop_dangling_drawing_links(wb)

  dir <- dirname(path)
  if (nzchar(dir) && !dir.exists(dir)) dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  openxlsx::saveWorkbook(wb, path, overwrite = TRUE)
  invisible(path)
}
