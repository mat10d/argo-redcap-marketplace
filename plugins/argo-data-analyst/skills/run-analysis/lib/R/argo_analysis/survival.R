# survival.R -- PLANNED, NOT BUILT.
#
#     source("lib/R/argo_analysis/survival.R")
#     survival(study, "enrol_date", "death_date")
#     -> stops with: Survival analysis is planned but not built yet.
#
# Survival analysis (Kaplan-Meier curves, log-rank tests, Cox models) is on the
# list for the ARGO analysis library and is not in it yet.
#
# This file exists so that the answer to "can ARGO do survival?" is a straight
# NOT YET, in one place, rather than a half-finished function producing a number
# nobody should trust. The registry entry (analyses/survival.md) marks it
# planned, so it appears in "what I can do" as something coming rather than
# something missing, and this stub says the same thing to anyone who calls it
# anyway -- immediately, instead of failing halfway through a study script.
#
# When it is built it belongs here, shaped like the rest of the library: a
# function that takes a study, uses applicable() for its denominators, and
# returns a plain table.

#: Read by the registry and by "what I can do". "ready" when this is built.
ARGO_SURVIVAL_STATUS <- "planned"

ARGO_SURVIVAL_PLANNED_MESSAGE <- paste0(
  "Survival analysis is planned but not built yet.\n",
  "Kaplan-Meier curves, log-rank tests and Cox models are on the list for the ARGO\n",
  "analysis library, but nothing here computes them today, and a wrong survival\n",
  "curve is worse than none. Table 1 is ready and works now. If survival is what\n",
  "you need, say so -- that is what moves it up the list."
)

#' Stop, with an explanation. This is the whole module, on purpose.
survival <- function(...) {
  stop(ARGO_SURVIVAL_PLANNED_MESSAGE, call. = FALSE)
}

# The same stub under its longer name, because `survival` is also the name of a
# well-known R package and a study script may well have spelled it out.
survival_analysis <- survival
