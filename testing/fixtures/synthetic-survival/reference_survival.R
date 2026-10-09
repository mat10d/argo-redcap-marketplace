#!/usr/bin/env Rscript
# reference_survival.R -- the golden numbers for the survival analysis, from R's
# own `survival` package, on the SYN synthetic survival fixture.
#
# SYNTHETIC TEST DATA ONLY. Writes expected_survival.csv (key,value), which
# tests/test_analysis_survival.py compares the Python library against on every
# run -- with or without R on the machine -- and the R library against where R
# exists. Regenerate only when the fixture or the reference plan changes:
#
#     cd testing/fixtures/synthetic-survival && Rscript reference_survival.R
#
# The analysis set (who is in, time, event) comes from the ARGO R library's
# time_to_event(), whose counts are pinned separately against MANIFEST.json
# (computed independently by generate.py). Every STATISTIC below is computed
# here with survival:: directly -- survfit, quantile, summary, survdiff, coxph,
# cox.zph -- never with the ARGO tables code, so the golden is independent of
# the code it checks. Full precision (17 significant digits); the tolerance is
# the test's business.

suppressWarnings(suppressMessages(library(survival)))
here <- local({
  hit <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(hit)) dirname(normalizePath(sub("^--file=", "", hit[1]))) else getwd()
})
lib <- file.path(here, "..", "..", "..", "plugins", "argo-data-analyst", "skills",
                 "run-analysis", "lib", "R", "argo_analysis")
source(file.path(lib, "core.R"))
source(file.path(lib, "survival.R"))

study <- apply_missing(load_study(file.path(here, "records.csv"),
                                 file.path(here, "datadictionary.csv")))
tte <- time_to_event(study, origin = "dx_date", event_field = "follow_status",
                     event_codes = "3", event_date = "death_date", censor_date = "fu_date",
                     end_of_follow_up = "2026-06-30", group_by = "tnm_n",
                     covariates = c("age", "sex", "tnm_n", "tnm_m"))

out <- list()
put <- function(key, value) out[[key]] <<- if (is.na(value)) "" else trimws(formatC(value, digits = 17, format = "g"))

d <- data.frame(time = tte$times, event = tte$events,
                group = factor(tte$groups, levels = tte$group_levels))
for (g in c(levels(d$group), "overall")) {
  s <- if (g == "overall") d else d[d$group == g, ]
  f <- survfit(Surv(time, event) ~ 1, data = s, conf.type = "log")
  q <- quantile(f, 0.5, conf.int = TRUE)
  put(paste0("median.", g), unname(q$quantile))
  put(paste0("median_lower.", g), unname(q$lower))
  put(paste0("median_upper.", g), unname(q$upper))
  sm <- summary(f, times = c(12, 24, 36), extend = FALSE)
  for (i in seq_along(sm$time)) {
    put(sprintf("at_risk.%s.%g", g, sm$time[i]), sm$n.risk[i])
    put(sprintf("survival.%s.%g", g, sm$time[i]), sm$surv[i])
    put(sprintf("survival_lower.%s.%g", g, sm$time[i]), sm$lower[i])
    put(sprintf("survival_upper.%s.%g", g, sm$time[i]), sm$upper[i])
  }
}
put("logrank.chisq", survdiff(Surv(time, event) ~ group, data = d)$chisq)

v <- tte$covariates
cx <- data.frame(time = tte$times, event = tte$events,
                 age = suppressWarnings(as.numeric(v$age)),
                 sex = factor(v$sex, levels = c("1", "2")),
                 tnm_n = factor(v$tnm_n, levels = c("0", "1", "2")),
                 tnm_m = factor(v$tnm_m, levels = c("0", "1")))
cx <- cx[stats::complete.cases(cx), ]
put("cox.n", nrow(cx))
fit <- coxph(Surv(time, event) ~ age + sex + tnm_n + tnm_m, data = cx, ties = "efron")
co <- summary(fit)$coefficients
for (nm in rownames(co)) {
  put(paste0("cox.coef.", nm), co[nm, "coef"])
  put(paste0("cox.se.", nm), co[nm, "se(coef)"])
  put(paste0("cox.p.", nm), co[nm, "Pr(>|z|)"])
}
zt <- cox.zph(fit)$table
for (nm in rownames(zt)) {
  put(paste0("zph.chisq.", nm), zt[nm, "chisq"])
  put(paste0("zph.p.", nm), zt[nm, "p"])
}

lines <- c("key,value", paste(names(out), unlist(out), sep = ","))
writeLines(lines, file.path(here, "expected_survival.csv"))
cat(sprintf("wrote expected_survival.csv (%d values, survival %s)\n", length(out),
            as.character(packageVersion("survival"))))
