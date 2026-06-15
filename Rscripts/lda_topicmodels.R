#!/usr/bin/env Rscript

suppressWarnings(suppressMessages({
  args <- commandArgs(trailingOnly = TRUE)
}))

fail <- function(msg) {
  cat(sprintf("LDA_R_ERROR: %s\n", msg), file = stderr())
  quit(save = "no", status = 1)
}

if (length(args) < 1) {
  fail("missing args json path")
}

args_path <- args[[1]]
if (!file.exists(args_path)) {
  fail(sprintf("args json not found: %s", args_path))
}

suppressWarnings(suppressMessages({
  library(jsonlite)
  library(topicmodels)
  library(slam)
}))

`%||%` <- function(a, b) if (is.null(a)) b else a

cfg <- fromJSON(args_path, simplifyVector = TRUE)

required_keys <- c(
  "input_dtm_csv",
  "output_topics_csv",
  "output_doc_topic_csv",
  "output_terms_beta_csv",
  "output_documents_gamma_csv",
  "output_summary_json",
  "output_tuning_csv"
)
missing_keys <- required_keys[!required_keys %in% names(cfg)]
if (length(missing_keys) > 0) {
  fail(sprintf("missing config keys: %s", paste(missing_keys, collapse = ", ")))
}

input_dtm_csv <- as.character(cfg$input_dtm_csv)
if (!file.exists(input_dtm_csv)) {
  fail(sprintf("input dtm csv not found: %s", input_dtm_csv))
}

safe_int <- function(x, default = 0L, min_value = NULL) {
  value <- suppressWarnings(as.integer(x))
  if (is.na(value)) value <- as.integer(default)
  if (!is.null(min_value)) value <- max(value, as.integer(min_value))
  value
}

safe_bool <- function(x, default = FALSE) {
  if (is.logical(x)) return(isTRUE(x))
  if (is.numeric(x)) return(as.integer(x) != 0L)
  if (is.character(x)) {
    token <- tolower(trimws(x))
    if (token %in% c("1", "true", "t", "yes", "y")) return(TRUE)
    if (token %in% c("0", "false", "f", "no", "n")) return(FALSE)
  }
  isTRUE(default)
}

method_raw <- toupper(as.character(cfg$method %||% "VEM"))
method_name <- if (method_raw %in% c("VEM", "GIBBS")) method_raw else "VEM"
seed <- safe_int(cfg$seed, 42L, 1L)
n_top_terms <- safe_int(cfg$n_top_terms, 15L, 3L)
k_requested <- safe_int(cfg$k_requested, 10L, 1L)
k_effective_cfg <- safe_int(cfg$k_effective, k_requested, 1L)

dtm_df <- read.csv(
  input_dtm_csv,
  sep = ";",
  stringsAsFactors = FALSE,
  check.names = FALSE,
  encoding = "UTF-8"
)

if (ncol(dtm_df) < 3) {
  fail("input dtm must contain Doc_ID, Label and at least one term column")
}

doc_id <- dtm_df[[1]]
doc_label <- as.character(dtm_df[[2]])
term_df <- dtm_df[, -(1:2), drop = FALSE]

if (nrow(term_df) < 2) {
  fail("LDA requires at least 2 documents")
}
if (ncol(term_df) < 2) {
  fail("LDA requires at least 2 terms")
}

term_matrix <- as.matrix(term_df)
storage.mode(term_matrix) <- "integer"
term_matrix[is.na(term_matrix)] <- 0L

k_effective <- min(k_effective_cfg, ncol(term_matrix))
k_effective <- max(k_effective, 1L)

stm <- slam::as.simple_triplet_matrix(term_matrix)
dimnames(stm) <- list(doc_label, colnames(term_matrix))

if (method_name == "GIBBS") {
  control <- list(
    seed = seed,
    burnin = safe_int(cfg$gibbs_burnin, 1000L, 0L),
    iter = safe_int(cfg$gibbs_iter, 1000L, 50L),
    thin = safe_int(cfg$gibbs_thin, 100L, 1L)
  )
} else {
  control <- list(seed = seed)
}

model <- tryCatch(
  {
    topicmodels::LDA(
      x = stm,
      k = k_effective,
      method = method_name,
      control = control
    )
  },
  error = function(e) {
    fail(sprintf("topicmodels::LDA failed: %s", conditionMessage(e)))
  }
)

poster <- topicmodels::posterior(model)
beta <- poster$terms
gamma <- poster$topics

if (is.null(beta) || is.null(gamma)) {
  fail("posterior(model) returned empty beta/gamma")
}

topic_ids <- seq_len(k_effective) - 1L
topic_labels <- character(k_effective)
for (i in seq_len(k_effective)) {
  ord <- order(beta[i, ], decreasing = TRUE)
  top_terms <- colnames(beta)[ord][seq_len(min(3L, length(ord)))]
  topic_labels[i] <- paste(top_terms, collapse = " / ")
}

topics_rows <- list()
beta_rows <- list()
for (i in seq_len(k_effective)) {
  ord <- order(beta[i, ], decreasing = TRUE)
  terms_i <- colnames(beta)[ord]
  weights_i <- beta[i, ord]
  for (j in seq_along(terms_i)) {
    topics_rows[[length(topics_rows) + 1L]] <- list(
      Topic_ID = i - 1L,
      Topic_Label = topic_labels[i],
      Term = terms_i[[j]],
      Weight = sprintf("%.8f", as.numeric(weights_i[[j]]))
    )
    beta_rows[[length(beta_rows) + 1L]] <- list(
      topic_id = i - 1L,
      topic_label = topic_labels[i],
      term = terms_i[[j]],
      beta = sprintf("%.10f", as.numeric(weights_i[[j]])),
      rank = j
    )
  }
}

topics_df <- if (length(topics_rows) > 0) {
  do.call(rbind.data.frame, c(topics_rows, stringsAsFactors = FALSE))
} else {
  data.frame(Topic_ID = integer(0), Topic_Label = character(0), Term = character(0), Weight = numeric(0))
}

beta_df <- if (length(beta_rows) > 0) {
  do.call(rbind.data.frame, c(beta_rows, stringsAsFactors = FALSE))
} else {
  data.frame(topic_id = integer(0), topic_label = character(0), term = character(0), beta = numeric(0), rank = integer(0))
}

doc_topic_df <- data.frame(
  Doc_ID = as.integer(doc_id),
  Label = doc_label,
  Dominant_Topic = apply(gamma, 1L, function(x) which.max(x) - 1L),
  stringsAsFactors = FALSE
)
for (i in seq_len(k_effective)) {
  col_name <- sprintf("T%d", i - 1L)
  doc_topic_df[[col_name]] <- gamma[, i]
}

gamma_rows <- list()
for (d in seq_len(nrow(gamma))) {
  for (t in seq_len(k_effective)) {
    gamma_rows[[length(gamma_rows) + 1L]] <- list(
      doc_id = as.integer(doc_id[[d]]),
      doc_label = doc_label[[d]],
      topic_id = t - 1L,
      gamma = sprintf("%.10f", as.numeric(gamma[d, t]))
    )
  }
}
gamma_df <- if (length(gamma_rows) > 0) {
  do.call(rbind.data.frame, c(gamma_rows, stringsAsFactors = FALSE))
} else {
  data.frame(doc_id = integer(0), doc_label = character(0), topic_id = integer(0), gamma = numeric(0))
}

perplexity_value <- NA_real_
perplexity_value <- tryCatch(
  {
    as.numeric(topicmodels::perplexity(model, newdata = stm))
  },
  error = function(e) NA_real_
)

enable_tuning <- safe_bool(cfg$enable_tuning, FALSE)
k_min <- safe_int(cfg$k_min, 2L, 2L)
k_max <- safe_int(cfg$k_max, 20L, 2L)
k_max <- min(k_max, ncol(term_matrix))
if (k_min > k_max) k_min <- k_max

tuning_df <- NULL
tuning_available <- FALSE
tuning_has_ldatuning <- FALSE
tuning_error <- ""

if (enable_tuning && k_max >= 2L && k_min <= k_max) {
  ks <- seq.int(k_min, k_max, by = 1L)
  tuning_rows <- vector("list", length(ks))
  for (idx in seq_along(ks)) {
    k_val <- ks[[idx]]
    control_k <- control
    model_k <- tryCatch(
      topicmodels::LDA(
        x = stm,
        k = as.integer(k_val),
        method = method_name,
        control = control_k
      ),
      error = function(e) NULL
    )
    perp <- NA_real_
    if (!is.null(model_k)) {
      perp <- tryCatch(
        as.numeric(topicmodels::perplexity(model_k, newdata = stm)),
        error = function(e) NA_real_
      )
    }
    tuning_rows[[idx]] <- list(k = as.integer(k_val), perplexity = perp)
  }
  tuning_df <- do.call(rbind.data.frame, c(tuning_rows, stringsAsFactors = FALSE))

  if (requireNamespace("ldatuning", quietly = TRUE)) {
    tuning_has_ldatuning <- TRUE
    extra_metrics <- tryCatch(
      {
        metric_control <- control
        metric_df <- ldatuning::FindTopicsNumber(
          dtm = stm,
          topics = ks,
          metrics = c("Griffiths2004", "CaoJuan2009", "Arun2010", "Deveaud2014"),
          method = method_name,
          control = metric_control,
          mc.cores = 1L,
          verbose = FALSE
        )
        metric_df
      },
      error = function(e) {
        tuning_error <<- conditionMessage(e)
        NULL
      }
    )
    if (!is.null(extra_metrics)) {
      extra_metrics <- as.data.frame(extra_metrics, stringsAsFactors = FALSE)
      names(extra_metrics) <- gsub("\\.", "_", names(extra_metrics))
      tuning_df <- merge(tuning_df, extra_metrics, by = "k", all.x = TRUE, sort = TRUE)
    }
  }

  if (!is.null(tuning_df) && nrow(tuning_df) > 0) {
    write.csv(tuning_df, cfg$output_tuning_csv, sep = ";", row.names = FALSE, fileEncoding = "UTF-8")
    tuning_available <- TRUE
  }
}

write.csv(topics_df, cfg$output_topics_csv, sep = ";", row.names = FALSE, fileEncoding = "UTF-8")
write.csv(doc_topic_df, cfg$output_doc_topic_csv, sep = ";", row.names = FALSE, fileEncoding = "UTF-8")
write.csv(beta_df, cfg$output_terms_beta_csv, sep = ";", row.names = FALSE, fileEncoding = "UTF-8")
write.csv(gamma_df, cfg$output_documents_gamma_csv, sep = ";", row.names = FALSE, fileEncoding = "UTF-8")

topic_mass <- colMeans(gamma)
empty_topics <- which(topic_mass <= 1e-12) - 1L

summary_payload <- list(
  backend = "r_topicmodels",
  method = method_name,
  seed = seed,
  k_requested = as.integer(k_requested),
  k_effective = as.integer(k_effective),
  n_docs = as.integer(nrow(term_matrix)),
  n_terms = as.integer(ncol(term_matrix)),
  perplexity = ifelse(is.na(perplexity_value), NULL, as.numeric(perplexity_value)),
  topic_labels = as.list(topic_labels),
  tuning_available = tuning_available,
  diagnostics = list(
    ldatuning_installed = tuning_has_ldatuning,
    ldatuning_error = ifelse(tuning_error == "", NULL, tuning_error),
    topic_mass = as.list(as.numeric(topic_mass)),
    empty_topics = as.list(as.integer(empty_topics))
  )
)

write_json(summary_payload, cfg$output_summary_json, auto_unbox = TRUE, pretty = TRUE)
cat("OK\n")
