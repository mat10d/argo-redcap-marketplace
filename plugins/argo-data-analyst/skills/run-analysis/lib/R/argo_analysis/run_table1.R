#!/usr/bin/env Rscript
# run_table1.R -- Table 1 from the command line, in one call.
#
#   Rscript lib/R/argo_analysis/run_table1.R \
#       --export records.csv \
#       --dictionary datadictionary.csv \
#       --group-by redcap_data_access_group \
#       --out out/table1.csv
#
# Options:
#   --export      the REDCap record export (raw codes), REQUIRED
#   --dictionary  the data dictionary / codebook, REQUIRED
#   --group-by    the variable the table is split by, REQUIRED -- there is no
#                 default, because "grouped by what?" is a question only the
#                 analyst can answer
#   --out         where to write the table. A path ending in .csv is the file
#                 itself; anything else is treated as a folder and the table is
#                 written into it as table1.csv. REQUIRED
#   --variables   comma-separated list of fields to describe, in the order you
#                 want them. Left out, every field the library knows how to
#                 describe is included, in codebook order.
#   --p-values    add a p-value column (off by default)
#   --test        welch (default) or mannwhitney, for continuous variables
#   --seed        fixes any simulated p-value; default 20260827
#
# A study script that needs nothing else is exactly this one command. When a
# study needs more -- a second table, a figure, a workbook -- write a short R
# script that sources core.R and table1.R and calls them directly.

argo_run_here <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  hit <- grep("^--file=", args, value = TRUE)
  if (length(hit)) return(dirname(normalizePath(sub("^--file=", "", hit[1]))))
  for (i in seq_len(sys.nframe())) {
    f <- sys.frame(i)$ofile
    if (!is.null(f)) return(dirname(normalizePath(f)))
  }
  getwd()
}

HERE <- argo_run_here()
source(file.path(HERE, "core.R"))
source(file.path(HERE, "table1.R"))

args <- commandArgs(trailingOnly = TRUE)

get_arg <- function(name, default = NULL) {
  hit <- which(args == name)
  if (length(hit) >= 1 && length(args) > hit[1]) args[hit[1] + 1] else default
}
has_flag <- function(name) any(args == name)

usage <- paste0(
  "Table 1 needs four things. For example:\n\n",
  "    Rscript run_table1.R --export records.csv --dictionary datadictionary.csv \\\n",
  "        --group-by redcap_data_access_group --out out/table1.csv\n\n",
  "  --export      the file of records you downloaded from REDCap\n",
  "  --dictionary  the codebook (data dictionary) for the same project\n",
  "  --group-by    the column the table is split by, for example the site\n",
  "  --out         where to save the table (a .csv file, or a folder)\n")

export_csv <- get_arg("--export")
dict_csv   <- get_arg("--dictionary")
group_by   <- get_arg("--group-by")
out_path   <- get_arg("--out")

missing_args <- c(
  if (is.null(export_csv)) "--export",
  if (is.null(dict_csv))   "--dictionary",
  if (is.null(group_by))   "--group-by",
  if (is.null(out_path))   "--out"
)
if (length(missing_args)) {
  stop(sprintf("Missing: %s\n\n%s", paste(missing_args, collapse = ", "), usage), call. = FALSE)
}

variables <- get_arg("--variables")
if (!is.null(variables)) {
  variables <- trimws(strsplit(variables, ",", fixed = TRUE)[[1]])
  variables <- variables[nzchar(variables)]
}

seed <- suppressWarnings(as.numeric(get_arg("--seed", as.character(ARGO_DEFAULT_SEED))))
if (is.na(seed)) seed <- ARGO_DEFAULT_SEED

study <- apply_missing(load_study(export_csv, dict_csv))
t1 <- table1(study, group_by = group_by, variables = variables,
             p_values = has_flag("--p-values"),
             continuous_test = get_arg("--test", "welch"), seed = seed)

if (!grepl("\\.csv$", out_path, ignore.case = TRUE)) {
  if (!dir.exists(out_path)) dir.create(out_path, recursive = TRUE, showWarnings = FALSE)
  out_path <- file.path(out_path, "table1.csv")
}
argo_write_csv(t1, out_path)

cat(sprintf("Table 1 written to %s\n", out_path))
cat(sprintf("  %d records, grouped by %s (%s)\n", nrow(study$data), group_by,
            paste(attr(t1, "group_columns"), collapse = ", ")))
cat(sprintf("  %d rows: %d variable(s) described\n", nrow(t1),
            length(unique(t1$variable)) - 1))
tests <- attr(t1, "tests")
if (length(tests)) {
  cat("  p-values: ")
  cat(paste(sprintf("%s (%s)", names(tests), unname(tests)), collapse = ", "), "\n")
}
