#!/usr/bin/env Rscript
# reference_epi.R -- the golden numbers for the epidemiology measures, from R's own
# stats package, on the SYN synthetic survival fixture (../synthetic-survival).
#
# SYNTHETIC TEST DATA ONLY. Writes expected_epi.csv (key,value), which
# tests/test_analysis_epi.py compares the Python library against on every run --
# with or without R on the machine. Regenerate only when the fixture or the plan in
# MANIFEST.json changes:
#
#     cd testing/fixtures/synthetic-epi && Rscript reference_epi.R
#
# The 2x2 and logistic analysis sets are derived HERE, in plain base R, straight
# from records.csv -- independently of the ARGO library they check. Person-time
# comes from the ARGO R library's time_to_event() (its counts are pinned against
# the survival MANIFEST separately). Every statistic is R's own: fisher.test,
# chisq.test, prop.test, poisson.test, glm. Full precision (17 digits).

here <- local({
  hit <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(hit)) dirname(normalizePath(sub("^--file=", "", hit[1]))) else getwd()
})
data_dir <- file.path(here, "..", "synthetic-survival")
d <- utils::read.csv(file.path(data_dir, "records.csv"), colClasses = "character",
                     na.strings = character(0))
mdc <- c("-666", "-777", "-888", "-999", "666")
clean <- function(v) { v <- trimws(v); v[v %in% mdc] <- ""; v }

out <- list()
put <- function(key, value) out[[key]] <<- if (is.na(value)) "" else
  trimws(formatC(value, digits = 17, format = "g"))

# ---- the 2x2 set: exposure tnm_m 1 vs 0; outcome follow_status 3 vs 1,2 ----------
e <- clean(d$tnm_m); y <- clean(d$follow_status)
keep <- e %in% c("1", "0") & y %in% c("3", "1", "2")
ex <- e[keep] == "1"; case <- y[keep] == "3"
a <- sum(ex & case); b <- sum(ex & !case); c <- sum(!ex & case); dd <- sum(!ex & !case)
put("cell.a", a); put("cell.b", b); put("cell.c", c); put("cell.d", dd)
put("excluded.outcome_missing", sum(e %in% c("1", "0") & y == ""))
put("excluded.outcome_other", sum(e %in% c("1", "0") & y == "4"))

z <- qnorm(0.975)
lor <- log(a * dd / (b * c)); se <- sqrt(1/a + 1/b + 1/c + 1/dd)
put("or.wald", exp(lor)); put("or.wald.lower", exp(lor - z * se)); put("or.wald.upper", exp(lor + z * se))
put("or.wald.p", 2 * pnorm(-abs(lor / se)))
f <- fisher.test(matrix(c(a, c, b, dd), 2))
put("or.fisher", f$estimate); put("or.fisher.lower", f$conf.int[1])
put("or.fisher.upper", f$conf.int[2]); put("or.fisher.p", f$p.value)
n1 <- a + b; n2 <- c + dd
lrr <- log((a / n1) / (c / n2)); se <- sqrt(1/a - 1/n1 + 1/c - 1/n2)
put("rr.wald", exp(lrr)); put("rr.wald.lower", exp(lrr - z * se)); put("rr.wald.upper", exp(lrr + z * se))
put("rr.wald.p", 2 * pnorm(-abs(lrr / se)))
p1 <- a / n1; p2 <- c / n2; rd <- p1 - p2; se <- sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
put("rd.wald", rd); put("rd.wald.lower", rd - z * se); put("rd.wald.upper", rd + z * se)
put("rd.wald.p", 2 * pnorm(-abs(rd / se)))
w1 <- prop.test(a, n1, correct = FALSE)$conf.int; w2 <- prop.test(c, n2, correct = FALSE)$conf.int
put("rd.newcombe.lower", rd - sqrt((p1 - w1[1])^2 + (w2[2] - p2)^2))
put("rd.newcombe.upper", rd + sqrt((w1[2] - p1)^2 + (p2 - w2[1])^2))
ch <- suppressWarnings(chisq.test(matrix(c(a, c, b, dd), 2), correct = FALSE))
put("chisq.statistic", unname(ch$statistic)); put("chisq.p", ch$p.value)

# ---- logistic: follow_status 3 ~ tnm_m + age + sex + tnm_n, complete cases -------
m <- data.frame(y = as.integer(case), x = as.integer(ex),
                age = suppressWarnings(as.numeric(clean(d$age)[keep])),
                sex = factor(clean(d$sex)[keep], levels = c("1", "2")),
                tnm_n = factor(clean(d$tnm_n)[keep], levels = c("0", "1", "2")))
m <- m[stats::complete.cases(m), ]
put("logistic.n", nrow(m))
g <- glm(y ~ x + age + sex + tnm_n, family = binomial, data = m,
         control = glm.control(epsilon = 1e-14, maxit = 100))
co <- summary(g)$coefficients
for (term in rownames(co)) {
  put(paste0("logistic.coef.", term), co[term, 1])
  put(paste0("logistic.se.", term), co[term, 2])
  put(paste0("logistic.p.", term), co[term, 4])
}

# ---- incidence: person-time from the ARGO R library's time_to_event -------------
lib <- file.path(here, "..", "..", "..", "plugins", "argo-data-analyst", "skills",
                 "run-analysis", "lib", "R", "argo_analysis")
source(file.path(lib, "core.R")); source(file.path(lib, "survival.R"))
study <- apply_missing(load_study(file.path(data_dir, "records.csv"),
                                  file.path(data_dir, "datadictionary.csv")))
tte <- time_to_event(study, origin = "dx_date", event_field = "follow_status",
                     event_codes = "3", event_date = "death_date", censor_date = "fu_date",
                     end_of_follow_up = "2026-06-30", group_by = "tnm_m")
for (g_ in c("M1", "M0")) {
  x <- sum(tte$events[tte$groups == g_]); t <- sum(tte$times[tte$groups == g_]) / 12
  pt <- poisson.test(x, t)
  put(paste0("rate.", g_), x / t); put(paste0("rate.lower.", g_), pt$conf.int[1])
  put(paste0("rate.upper.", g_), pt$conf.int[2]); put(paste0("person_years.", g_), t)
  put(paste0("events.", g_), x)
}
x <- c(sum(tte$events[tte$groups == "M1"]), sum(tte$events[tte$groups == "M0"]))
t <- c(sum(tte$times[tte$groups == "M1"]), sum(tte$times[tte$groups == "M0"])) / 12
pr <- poisson.test(x, t)
put("rate_ratio", pr$estimate); put("rate_ratio.lower", pr$conf.int[1])
put("rate_ratio.upper", pr$conf.int[2]); put("rate_ratio.p", pr$p.value)

res <- data.frame(key = names(out), value = unlist(out), stringsAsFactors = FALSE)
utils::write.csv(res, file.path(here, "expected_epi.csv"), row.names = FALSE, quote = FALSE)
cat(sprintf("wrote %d golden values to expected_epi.csv (R %s)\n", nrow(res),
            as.character(getRversion())))
