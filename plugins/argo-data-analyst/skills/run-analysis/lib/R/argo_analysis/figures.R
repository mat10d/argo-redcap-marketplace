# figures.R -- two figures, one look.
#
#     source("lib/R/argo_analysis/core.R")
#     source("lib/R/argo_analysis/figures.R")
#     bar_by_group(study, "sex", "redcap_data_access_group", "out/sex_by_site.png")
#     hist(study, "age", "out/age.png")
#
# THE HOUSE LOOK, so every ARGO figure is recognisable:
#   * PNG at 300 dpi -- sharp when a journal or a report prints it
#   * text sized to be readable at print size, not just on screen
#   * the Okabe-Ito palette, which stays distinguishable to colourblind readers
#     and in greyscale
#   * title  = the field's label, as the codebook words it
#   * subtitle = "n = ... ; missing = ..." -- a figure that hides its denominator
#     is a figure that will be misread
#
# Base graphics on purpose: no ggplot2, no install step. The script that made the
# figure is its provenance -- there is no metadata to lose.
#
# hist() shadows base R's hist() once this file is sourced. That is the contract
# name; the base version is still there as graphics::hist().

if (!exists("applicable", mode = "function")) {
  stop(paste0("Load the core of the library first:\n",
              '    source("lib/R/argo_analysis/core.R")'), call. = FALSE)
}

# Okabe-Ito: eight colours that stay apart for every common form of colour
# blindness. Blue first because a single-series chart should not be red.
ARGO_PALETTE <- c("#0072B2", "#E69F00", "#009E73", "#CC79A7",
                  "#56B4E9", "#D55E00", "#F0E442", "#666666")

ARGO_FIGURE_DPI <- 300

#' Open a 300-dpi PNG device, whichever backend this R has.
argo_open_png <- function(path, width = 8, height = 5) {
  dir <- dirname(path)
  if (nzchar(dir) && !dir.exists(dir)) dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  type <- if (isTRUE(capabilities("cairo"))) "cairo"
          else if (isTRUE(capabilities("aqua"))) "quartz"
          else NULL
  ok <- tryCatch({
    if (is.null(type)) {
      grDevices::png(path, width = width, height = height, units = "in",
                     res = ARGO_FIGURE_DPI)
    } else {
      grDevices::png(path, width = width, height = height, units = "in",
                     res = ARGO_FIGURE_DPI, type = type)
    }
    TRUE
  }, error = function(e) FALSE)
  if (!ok) {
    stop(paste0("This copy of R cannot save PNG pictures -- it was built without the\n",
                "graphics support that needs. The tables will still work. If you need the\n",
                "figures, install R from https://cran.r-project.org (the standard build\n",
                "includes it) and run this again."), call. = FALSE)
  }
  graphics::par(mar = c(5.5, 5, 4.5, 1.5), family = "", cex.axis = 1.0,
                cex.lab = 1.1, las = 1)
  invisible(TRUE)
}

#' Title + "n = ... ; missing = ..." subtitle, drawn the same way on every figure.
argo_figure_titles <- function(title, n, missing) {
  graphics::title(main = title, cex.main = 1.35, font.main = 2, line = 2.6)
  graphics::mtext(sprintf("n = %d ; missing = %d", as.integer(n), as.integer(missing)),
                  side = 3, line = 1.0, cex = 1.0, col = "#444444")
}

#' Counts of a categorical field, side by side across the groups.
#'
#' Bars are the PERCENT within each group, because groups are rarely the same
#' size and raw counts invite the wrong comparison. The counts are in the table;
#' this picture is for the shape.
#'
#' Levels are in codebook order. Missing values and MDC codes are not a bar --
#' they are in the subtitle, where they belong.
bar_by_group <- function(study, field, group_by, path, width = 8, height = 5) {
  if (!(field %in% names(study$data))) {
    stop(sprintf("There is no column called '%s' in this export.", field), call. = FALSE)
  }
  if (!(group_by %in% names(study$data))) {
    stop(sprintf("There is no column called '%s' to group by.", group_by), call. = FALSE)
  }
  map <- labels(study, field)
  if (!length(map)) {
    stop(sprintf(paste0("'%s' has no choices in the codebook, so there are no bars to ",
                        "draw.\nFor a number, use hist(study, \"%s\", ...) instead."),
                 field, field), call. = FALSE)
  }
  codes <- names(map)[!(names(map) %in% ARGO_MDC)]

  applies <- applicable(study, field)
  values  <- argo_usable(study$data[[field]])
  gvals   <- trimws(as.character(study$data[[group_by]]))
  gvals[is.na(gvals)] <- ""

  levels_ <- argo_group_levels_for_figures(study, group_by, gvals)
  gmap    <- argo_choice_map(study, group_by)
  gnames  <- vapply(levels_, function(lv)
    if (lv %in% names(gmap) && nzchar(gmap[[lv]])) unname(gmap[[lv]]) else lv, character(1))

  pct <- matrix(0, nrow = length(codes), ncol = length(levels_),
                dimnames = list(unname(map[codes]), unname(gnames)))
  for (j in seq_along(levels_)) {
    keep <- applies & gvals == levels_[j]
    v <- values[keep]
    v <- v[!is.na(v)]
    if (length(v)) {
      for (i in seq_along(codes)) pct[i, j] <- 100 * sum(v == codes[i]) / length(v)
    }
  }

  n_applicable <- sum(applies)
  n_missing    <- sum(applies & is.na(values))

  argo_open_png(path, width, height)
  on.exit(grDevices::dev.off(), add = TRUE)
  colours <- rep(ARGO_PALETTE, length.out = nrow(pct))
  # Fit the axis to the data, rounded up to a tidy multiple of 10, never past
  # 100 and never below 20 -- a bar chart of 2% against a 0-100 axis is unreadable,
  # and one against a 0-3 axis is a lie.
  top <- min(100, max(20, ceiling(max(pct) * 1.2 / 10) * 10))
  bp <- graphics::barplot(pct, beside = TRUE, col = colours, border = NA,
                          ylim = c(0, top), ylab = "Percent of participants (%)",
                          xlab = argo_field_label(study, group_by),
                          cex.names = 1.0, axes = TRUE)
  graphics::abline(h = graphics::axTicks(2), col = "#EEEEEE", lwd = 1)
  graphics::barplot(pct, beside = TRUE, col = colours, border = NA, add = TRUE, axes = FALSE)
  graphics::legend("topright", legend = rownames(pct), fill = colours, border = NA,
                   bty = "n", cex = 0.95, inset = c(0, -0.02), xpd = TRUE)
  argo_figure_titles(argo_field_label(study, field), n_applicable - n_missing, n_missing)
  invisible(path)
}

# Group levels for a figure: codebook order where there is a codebook, else the
# order the data offers, sorted. Kept beside the figures so figures.R can be
# sourced without table1.R.
argo_group_levels_for_figures <- function(study, group_by, gvals) {
  observed <- unique(gvals[nzchar(gvals)])
  codebook <- names(argo_choice_map(study, group_by))
  if (length(codebook)) c(codebook[codebook %in% observed], sort(setdiff(observed, codebook)))
  else sort(observed)
}

#' The distribution of a numeric field.
#'
#' Missing values and MDC codes are excluded from the bars and reported in the
#' subtitle. The median is drawn as a dashed line, because the first question
#' anyone asks of a histogram is "where is the middle".
hist <- function(study, field, path, bins = 20, width = 8, height = 5) {
  if (!(field %in% names(study$data))) {
    stop(sprintf("There is no column called '%s' in this export.", field), call. = FALSE)
  }
  applies <- applicable(study, field)
  values  <- suppressWarnings(as.numeric(argo_usable(study$data[[field]])))
  v <- values[applies]
  n_missing <- sum(is.na(v))
  v <- v[!is.na(v)]
  if (!length(v)) {
    stop(sprintf(paste0("'%s' has no usable numbers in this export, so there is nothing ",
                        "to plot.\nIf it is a question with choices, use bar_by_group() ",
                        "instead."), field), call. = FALSE)
  }

  breaks <- if (is.null(bins)) "Sturges" else as.integer(bins)
  # Measure first, then draw: the extra headroom keeps the median legend off the
  # tallest bar.
  shape <- graphics::hist(v, breaks = breaks, plot = FALSE)
  argo_open_png(path, width, height)
  on.exit(grDevices::dev.off(), add = TRUE)
  graphics::hist(v, breaks = breaks, col = ARGO_PALETTE[1], border = "white",
                 main = "", xlab = argo_field_label(study, field),
                 ylab = "Number of participants",
                 ylim = c(0, max(shape$counts) * 1.18))
  graphics::abline(v = stats::median(v), col = ARGO_PALETTE[6], lwd = 2, lty = 2)
  graphics::legend("topright", legend = sprintf("median = %s", argo_format(stats::median(v), FALSE)),
                   col = ARGO_PALETTE[6], lwd = 2, lty = 2, bty = "n", cex = 0.95)
  argo_figure_titles(argo_field_label(study, field), length(v), n_missing)
  invisible(path)
}
