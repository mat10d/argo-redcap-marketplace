# table1.R -- Table 1: a cohort described, split by one grouping variable.
#
#     source("lib/R/argo_analysis/core.R")
#     source("lib/R/argo_analysis/table1.R")
#     study <- apply_missing(load_study("records.csv", "datadictionary.csv"))
#     t1 <- table1(study, group_by = "redcap_data_access_group",
#                  variables = c("age", "sex", "education"))
#
# THE SHAPE OF THE TABLE
# ----------------------
# Long, one row per (variable, level, statistic), one column per group level
# plus `overall`:
#
#     variable,level,statistic,site_alpha,site_beta,overall
#
# `statistic` is one of:
#     n        a count -- of records, of non-missing values, or of that level
#     missing  how many applicable records had no usable value
#     pct      percent of the APPLICABLE, non-missing records in that column
#     mean sd median q1 q3   for a continuous variable
#
# Every cell is a bare number, never a pre-formatted "12 (34.5%)" string. That
# is what lets two languages be compared for equality, and lets a user paste the
# table into anything without unpicking it.
#
# TWO RULES THAT DECIDE EVERY NUMBER
# ----------------------------------
# 1. Missing means missing. Blanks and MDC sentinels (-666/-777/-888/-999, 666)
#    are counted under `missing`, never as a category and never in a mean. An
#    MDC code offered as a choice on a field is there so an RA can record "no
#    answer, and here is why" -- it is not a level of the variable.
# 2. The denominator is the APPLICABLE denominator. A field that REDCap only
#    shows to some records is described against those records. Pregnancy status
#    is out of 111 women, not out of 200 participants. See applicable() in
#    core.R.
#
# Level order comes from the CODEBOOK, never from the data and never
# alphabetically, so a level nobody happens to have still appears (as a zero)
# and the row order is stable between runs and between languages.

if (!exists("applicable", mode = "function")) {
  stop(paste0("Load the core of the library first:\n",
              '    source("lib/R/argo_analysis/core.R")'), call. = FALSE)
}

# ---------------------------------------------------------------------------
# Choosing the columns
# ---------------------------------------------------------------------------

#' The group levels, in codebook order where the variable has a codebook.
#'
#' Data access groups are a REDCap system column with no codebook entry, so
#' their levels are taken from the data and sorted -- there is no other order to
#' respect. A coded field keeps its Designer order.
argo_group_levels <- function(study, group_by) {
  values <- as.character(study$data[[group_by]])
  values[is.na(values)] <- ""
  values <- trimws(values)
  observed <- unique(values[nzchar(values)])
  codebook <- names(argo_choice_map(study, group_by))
  if (length(codebook)) {
    ordered <- codebook[codebook %in% observed]
    extra   <- sort(setdiff(observed, codebook))
    c(ordered, extra)
  } else {
    sort(observed)
  }
}

#' What to call a group column: the label if the codebook has one, else the code.
argo_group_column_names <- function(study, group_by, levels_) {
  map <- argo_choice_map(study, group_by)
  out <- vapply(levels_, function(lv) {
    if (lv %in% names(map) && nzchar(map[[lv]])) unname(map[[lv]]) else lv
  }, character(1))
  # "overall" is reserved for the last column, so a group level that happens to
  # be called that is renamed rather than silently overwriting it.
  make.unique(c("overall", unname(out)), sep = " ")[-1]
}

#' The fields worth putting in a Table 1 when the analyst does not name any:
#' every codebook field we know how to describe, in codebook order, minus the
#' record identifier and the grouping variable itself.
table1_variables <- function(study, group_by = NULL) {
  fields <- study$dd$field_name
  keep <- vapply(fields, function(f) argo_field_kind(study, f) != "unsupported", logical(1))
  fields <- fields[keep]
  fields <- setdiff(fields, c(study$id_field, group_by))
  fields[fields %in% names(study$data)]
}

# ---------------------------------------------------------------------------
# p-values (only when asked for)
# ---------------------------------------------------------------------------

#' A p-value comparing the group columns (never `overall`).
#'
#' Categorical : chi-square, falling back to Fisher's exact test when any
#'               expected count is under 5. Where a table is too large to
#'               enumerate exactly, the p-value is simulated and the simulation
#'               is SEEDED, so the same data always gives the same number.
#'
#'               ONE PLACE THE TWO LANGUAGES DIVERGE: the Python half has no
#'               exact Fisher available (it is stdlib-only, no scipy), so where
#'               R computes an exact Fisher p-value Python simulates instead.
#'               Both are correct and both are reproducible; they will not print
#'               the same number. Every other cell of the table matches. Which
#'               test produced each p-value is in attr(table, "tests") and is
#'               printed when the table is built, so a paper never has to guess.
#' Continuous  : Welch's t-test for two groups (Welch, not Student -- equal
#'               variances are an assumption nobody checks), Welch's ANOVA for
#'               more. `continuous_test = "mannwhitney"` swaps in Mann-Whitney /
#'               Kruskal-Wallis.
#'
#' Returns list(p = numeric or NA, test = character).
argo_pvalue_categorical <- function(counts, seed) {
  # counts: levels x groups matrix
  counts <- counts[rowSums(counts) > 0, , drop = FALSE]
  counts <- counts[, colSums(counts) > 0, drop = FALSE]
  if (nrow(counts) < 2 || ncol(counts) < 2) return(list(p = NA_real_, test = "not tested"))
  expected <- outer(rowSums(counts), colSums(counts)) / sum(counts)
  if (all(expected >= 5)) {
    p <- suppressWarnings(stats::chisq.test(counts, correct = FALSE)$p.value)
    return(list(p = p, test = "chi-square"))
  }
  # Exact first. R can compute Fisher exactly for the table sizes a Table 1
  # actually produces, and an exact p-value is both better and the same every
  # time it is run. Simulation is the fallback for a table too big to enumerate,
  # and it is seeded so that even then the number is reproducible.
  exact <- tryCatch(stats::fisher.test(counts, workspace = 2e7)$p.value,
                    error = function(e) NULL)
  if (!is.null(exact)) return(list(p = exact, test = "Fisher's exact"))
  set.seed(seed)
  p <- tryCatch(stats::fisher.test(counts, simulate.p.value = TRUE, B = 20000)$p.value,
                error = function(e) NA_real_)
  list(p = p, test = sprintf("Fisher's exact, p by 20000 seeded simulations (seed %s)", seed))
}

argo_pvalue_continuous <- function(values_by_group, test) {
  values_by_group <- values_by_group[vapply(values_by_group, length, integer(1)) >= 2]
  if (length(values_by_group) < 2) return(list(p = NA_real_, test = "not tested"))
  x <- unlist(values_by_group, use.names = FALSE)
  g <- factor(rep(names(values_by_group),
                  vapply(values_by_group, length, integer(1))))
  two <- length(values_by_group) == 2
  res <- tryCatch({
    if (identical(test, "mannwhitney")) {
      if (two) list(p = suppressWarnings(stats::wilcox.test(x ~ g)$p.value),
                    test = "Mann-Whitney U")
      else     list(p = stats::kruskal.test(x ~ g)$p.value, test = "Kruskal-Wallis")
    } else {
      if (two) list(p = stats::t.test(x ~ g, var.equal = FALSE)$p.value,
                    test = "Welch t-test")
      else     list(p = stats::oneway.test(x ~ g, var.equal = FALSE)$p.value,
                    test = "Welch ANOVA")
    }
  }, error = function(e) list(p = NA_real_, test = "not tested"))
  res
}

#' p-values keep FOUR places -- two would print every small p as 0.00 -- and stay
#' bare numbers rather than "<0.001", so the column can still be read by a
#' machine. The Python half of the library formats them identically.
argo_format_p <- function(p) {
  if (length(p) == 0 || is.null(p) || is.na(p)) return("")
  sprintf("%.4f", p)
}

# ---------------------------------------------------------------------------
# table1
# ---------------------------------------------------------------------------

# The one randomised test (a simulated Fisher) is seeded from here, so the same
# data always produces the same p-value. Same number as the Python half.
ARGO_DEFAULT_SEED <- 20260827

#' Build Table 1.
#'
#' study            from load_study(); run apply_missing() on it first
#' group_by         REQUIRED. The variable the table is split by. There is no
#'                  default on purpose: "grouped by what?" is a question only
#'                  the analyst can answer, and guessing it silently is how a
#'                  table ends up describing the wrong comparison.
#' variables        fields to describe, in the order you want them. NULL means
#'                  every field the library knows how to describe, in codebook
#'                  order.
#' p_values         add a `p_value` column. Off by default -- a p-value nobody
#'                  asked for is a p-value nobody chose the test for.
#' continuous_test  "welch" (default) or "mannwhitney".
#' seed             fixes any Monte Carlo p-value, so runs are reproducible.
table1 <- function(study, group_by = NULL, variables = NULL, p_values = FALSE,
                   continuous_test = c("welch", "mannwhitney"),
                   seed = ARGO_DEFAULT_SEED) {
  continuous_test <- match.arg(continuous_test)

  if (is.null(group_by) || !nzchar(trimws(as.character(group_by)[1]))) {
    stop(paste0("Table 1 has to be split by something. Tell me which variable to ",
                "group by -- for\nexample the site (",
                if (is.null(study$sites)) "redcap_data_access_group" else study$sites,
                ") or the treatment arm:\n",
                '    table1(study, group_by = "your_variable", variables = c(...))'),
         call. = FALSE)
  }
  group_by <- as.character(group_by)[1]
  if (!(group_by %in% names(study$data))) {
    stop(sprintf(paste0("There is no column called '%s' in this export, so the table ",
                        "cannot be grouped by it.\nThe columns available include: %s"),
                 group_by, paste(utils::head(names(study$data), 12), collapse = ", ")),
         call. = FALSE)
  }
  if (is.null(variables)) variables <- table1_variables(study, group_by)
  variables <- as.character(variables)

  levels_ <- argo_group_levels(study, group_by)
  if (!length(levels_)) {
    stop(sprintf("Every record is blank for '%s', so there is nothing to group by.",
                 group_by), call. = FALSE)
  }
  group_columns <- argo_group_column_names(study, group_by, levels_)
  columns <- c(group_columns, "overall")

  # Which records fall in which column. A record with no group value is counted
  # in `overall` and in no group column -- it is a real record, it just cannot
  # be placed.
  gvals <- trimws(as.character(study$data[[group_by]]))
  gvals[is.na(gvals)] <- ""
  masks <- list()
  for (i in seq_along(levels_)) masks[[group_columns[i]]] <- gvals == levels_[i]
  masks[["overall"]] <- rep(TRUE, nrow(study$data))

  rows <- list()
  add <- function(variable, level, statistic, per_column, is_count, p = NULL) {
    row <- list(variable = variable, level = level, statistic = statistic)
    for (cl in columns) row[[cl]] <- argo_format(per_column[[cl]], is_count)
    if (p_values) row[["p_value"]] <- if (is.null(p)) "" else argo_format_p(p)
    rows[[length(rows) + 1]] <<- row
  }
  per <- function(f) stats::setNames(lapply(columns, f), columns)

  tests_used <- character(0)

  # --- how many records are in each column ---------------------------------
  add("records", "", "n", per(function(cl) sum(masks[[cl]])), TRUE)

  for (field in variables) {
    kind <- argo_field_kind(study, field)
    if (!(field %in% names(study$data))) {
      warning(sprintf(paste0("'%s' is in the codebook but not in this export, so it is ",
                             "not in the table."), field), call. = FALSE)
      next
    }
    if (kind == "unsupported") {
      dd_row <- argo_dd_row(study, field)
      ftype <- if (is.null(dd_row)) "field not in the codebook" else dd_row$field_type[1]
      warning(sprintf(paste0("I do not know how to describe '%s' in a Table 1 (%s, with\n",
                             "no choices and no numeric validation), so it is not in the ",
                             "table."), field, ftype), call. = FALSE)
      next
    }

    # The applicable denominator: only records whose branching logic fired.
    applies <- applicable(study, field)
    values  <- argo_usable(study$data[[field]])
    in_col  <- per(function(cl) masks[[cl]] & applies)

    if (kind == "continuous") {
      numeric_values <- suppressWarnings(as.numeric(values))
      good <- per(function(cl) {
        v <- numeric_values[in_col[[cl]]]
        v[!is.na(v)]
      })
      first_row_index <- length(rows) + 1
      add(field, "", "n", per(function(cl) length(good[[cl]])), TRUE)
      add(field, "", "missing",
          per(function(cl) sum(in_col[[cl]]) - length(good[[cl]])), TRUE)
      # sd() uses the n-1 denominator (the sample SD), matching the Python half
      # and Stata's summarize. numpy's std() defaults to n and would disagree in
      # the second decimal -- the classic three-language mismatch.
      add(field, "", "mean",
          per(function(cl) if (length(good[[cl]])) mean(good[[cl]]) else NA_real_), FALSE)
      add(field, "", "sd",
          per(function(cl) if (length(good[[cl]]) > 1) stats::sd(good[[cl]]) else NA_real_), FALSE)
      # Quantile type 7 -- R's default, and numpy's default. Stated because the
      # nine quantile definitions disagree on small samples.
      qtl <- function(cl, p) {
        v <- good[[cl]]
        if (!length(v)) return(NA_real_)
        unname(stats::quantile(v, probs = p, type = 7, names = FALSE))
      }
      add(field, "", "median", per(function(cl) qtl(cl, 0.50)), FALSE)
      add(field, "", "q1",     per(function(cl) qtl(cl, 0.25)), FALSE)
      add(field, "", "q3",     per(function(cl) qtl(cl, 0.75)), FALSE)

      if (p_values) {
        res <- argo_pvalue_continuous(
          stats::setNames(lapply(group_columns, function(cl) good[[cl]]), group_columns),
          continuous_test)
        tests_used[[field]] <- res$test
        # The p-value belongs to the variable, not to a statistic, so it sits on
        # the variable's first row and the rest of the block is left blank.
        rows[[first_row_index]][["p_value"]] <- argo_format_p(res$p)
      }

    } else {
      map <- labels(study, field)
      if (!length(map)) {
        warning(sprintf(paste0("'%s' has no choices in the codebook, so there is nothing ",
                               "to count."), field), call. = FALSE)
        next
      }
      # MDC codes are offered as choices on some fields so an RA can record
      # "missing, and here is why". They are NOT categories of the variable and
      # must never become rows of a Table 1 -- they are counted under `missing`.
      codes <- names(map)[!(names(map) %in% ARGO_MDC)]
      present    <- per(function(cl) values[in_col[[cl]]])
      nonmissing <- per(function(cl) present[[cl]][!is.na(present[[cl]])])

      counts <- matrix(0L, nrow = length(codes), ncol = length(group_columns),
                       dimnames = list(codes, group_columns))
      first_row_index <- length(rows) + 1
      for (code in codes) {
        n_level <- per(function(cl) sum(nonmissing[[cl]] == code))
        for (cl in group_columns) counts[code, cl] <- as.integer(n_level[[cl]])
        add(field, unname(map[code]), "n", n_level, TRUE)
        # Percent of the applicable, non-missing records in that column --
        # "percent of what" is the question every reader of a Table 1 asks first.
        add(field, unname(map[code]), "pct",
            per(function(cl) {
              d <- length(nonmissing[[cl]])
              if (d == 0) NA_real_ else 100 * n_level[[cl]] / d
            }), FALSE)
      }
      add(field, "", "missing",
          per(function(cl) length(present[[cl]]) - length(nonmissing[[cl]])), TRUE)

      if (p_values) {
        res <- argo_pvalue_categorical(counts, seed)
        tests_used[[field]] <- res$test
        rows[[first_row_index]][["p_value"]] <- argo_format_p(res$p)
      }
    }
  }

  out <- do.call(rbind, lapply(rows, function(r)
    as.data.frame(r, stringsAsFactors = FALSE, check.names = FALSE)))
  rownames(out) <- NULL
  attr(out, "group_by")       <- group_by
  attr(out, "group_levels")   <- levels_
  attr(out, "group_columns")  <- group_columns
  attr(out, "n_records")      <- nrow(study$data)
  attr(out, "tests")          <- tests_used
  out
}

#' Write a Table 1 (or any long table) to CSV.
write_table <- function(table, path) argo_write_csv(table, path)
