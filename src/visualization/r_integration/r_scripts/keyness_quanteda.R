#!/usr/bin/env Rscript
# ==============================================================================
# Keyness (Quanteda) - implementação substituta baseada em:
# - analise_texto (2)/1. quanteda_text_plots.R
# - analise_texto (2)/2. quanteda_text_plots_exemplo2.R
# ==============================================================================

suppressPackageStartupMessages({
  library(jsonlite)
})

lexi_lib <- Sys.getenv("LEXIANALYST_R_LIBS_USER", unset = Sys.getenv("R_LIBS_USER", unset = ""))
if (nzchar(lexi_lib)) {
  dir.create(lexi_lib, recursive = TRUE, showWarnings = FALSE)
  .libPaths(unique(c(normalizePath(lexi_lib, winslash = "/", mustWork = FALSE), .libPaths())))
  Sys.setenv(R_LIBS_USER = lexi_lib)
}

lexi_install_pkg <- function(pkg, repos = "https://cloud.r-project.org") {
  deps <- c("Depends", "Imports", "LinkingTo")
  pkg_type <- if (.Platform$OS.type == "windows") "binary" else "source"
  if (nzchar(lexi_lib)) {
    install.packages(pkg, repos = repos, lib = lexi_lib, dependencies = deps, type = pkg_type, quiet = TRUE)
  } else {
    install.packages(pkg, repos = repos, dependencies = deps, type = pkg_type, quiet = TRUE)
  }
}

ensure_package <- function(pkg) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    lexi_install_pkg(pkg)
  }
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop(paste("Pacote R ausente:", pkg))
  }
  suppressPackageStartupMessages(library(pkg, character.only = TRUE))
}

ensure_package("quanteda")
ensure_package("quanteda.textstats")
ensure_package("quanteda.textplots")

read_params <- function(path) {
  if (!file.exists(path)) {
    stop(paste("Arquivo de parametros nao encontrado:", path))
  }
  jsonlite::fromJSON(path)
}

read_utf8_text <- function(path) {
  if (!file.exists(path)) {
    stop(paste("Arquivo de texto nao encontrado:", path))
  }
  lines <- readLines(path, encoding = "UTF-8", warn = FALSE)
  paste(lines, collapse = "\n")
}

# Divide por marcadores ALCESTE (****) para manter granularidade por documento.
split_uci_docs <- function(text_input, prefix) {
  lines <- strsplit(as.character(text_input), "\n", fixed = TRUE)[[1]]
  marker_idx <- grep("^\\s*\\*{4}", lines)

  docs <- character(0)
  if (length(marker_idx) == 0) {
    one <- trimws(gsub("\\s+", " ", paste(lines, collapse = " ")))
    if (nchar(one) > 0) docs <- c(one)
  } else {
    current <- character(0)
    flush_current <- function() {
      doc <- trimws(gsub("\\s+", " ", paste(current, collapse = " ")))
      if (nchar(doc) > 0) docs <<- c(docs, doc)
    }
    for (line in lines) {
      if (grepl("^\\s*\\*{4}", line)) {
        if (length(current) > 0) {
          flush_current()
          current <- character(0)
        }
      } else {
        current <- c(current, line)
      }
    }
    if (length(current) > 0) flush_current()
  }

  if (length(docs) == 0) {
    fallback_doc <- trimws(gsub("\\s+", " ", as.character(text_input)))
    if (nchar(fallback_doc) > 0) docs <- c(fallback_doc)
  }

  if (length(docs) == 0) {
    stop("Nao foi possivel gerar documentos validos para keyness.")
  }

  names(docs) <- paste0(prefix, "_", seq_along(docs))
  docs
}

create_keyness <- function(params) {
  text_a <- read_utf8_text(params$input_a)
  text_b <- read_utf8_text(params$input_b)

  docs_a <- split_uci_docs(text_a, "a")
  docs_b <- split_uci_docs(text_b, "b")

  docs_df <- data.frame(
    doc_id = c(names(docs_a), names(docs_b)),
    text = c(docs_a, docs_b),
    group = c(rep("A", length(docs_a)), rep("B", length(docs_b))),
    stringsAsFactors = FALSE
  )

  corp <- quanteda::corpus(docs_df, text_field = "text")
  quanteda::docvars(corp, "group") <- docs_df$group

  # Pipeline direto do exemplo quanteda: tokens -> remove stopwords -> dfm -> group -> keyness.
  toks <- quanteda::tokens(
    corp,
    remove_punct = TRUE,
    remove_numbers = TRUE,
    remove_symbols = TRUE
  )
  toks <- quanteda::tokens_tolower(toks)

  if (isTRUE(params$remove_stopwords)) {
    lang <- as.character(params$stopwords_lang)
    if (is.null(lang) || !nzchar(lang)) lang <- "pt"
    sw <- tryCatch(quanteda::stopwords(lang), error = function(e) quanteda::stopwords("pt"))
    toks <- quanteda::tokens_remove(toks, sw, padding = FALSE)
  }

  dfmat <- quanteda::dfm(toks)
  if (quanteda::nfeat(dfmat) <= 0) {
    stop("Nenhum termo elegivel apos tokenizacao/stopwords.")
  }

  min_freq <- max(1, as.integer(params$min_freq))
  dfmat <- quanteda::dfm_trim(dfmat, min_termfreq = min_freq)
  if (quanteda::nfeat(dfmat) <= 0) {
    stop("Nenhum termo elegivel apos filtro de frequencia minima.")
  }

  dfmat_group <- quanteda::dfm_group(dfmat, groups = quanteda::docvars(dfmat, "group"))
  if (quanteda::ndoc(dfmat_group) < 2 || !all(c("A", "B") %in% quanteda::docnames(dfmat_group))) {
    stop("Nao foi possivel construir grupos A/B para keyness.")
  }

  measure <- as.character(params$measure)
  if (is.null(measure) || !nzchar(measure)) measure <- "lr"
  if (!measure %in% c("chi2", "exact", "lr")) measure <- "lr"

  tstat <- quanteda.textstats::textstat_keyness(
    dfmat_group,
    target = "A",
    measure = measure
  )

  result_df <- as.data.frame(tstat, stringsAsFactors = FALSE)
  if (!"feature" %in% names(result_df)) {
    stop("Resultado de keyness sem coluna 'feature'.")
  }

  metric_col <- if (measure %in% names(result_df)) {
    measure
  } else if (measure == "lr" && "G2" %in% names(result_df)) {
    "G2"
  } else {
    cands <- c("chi2", "lr", "exact", "G2")
    cands <- cands[cands %in% names(result_df)]
    if (length(cands) == 0) stop("Nao foi possivel identificar coluna de estatistica no keyness.")
    cands[1]
  }

  if (!"n_target" %in% names(result_df)) result_df$n_target <- 0
  if (!"n_reference" %in% names(result_df)) result_df$n_reference <- 0
  if (!"p" %in% names(result_df)) result_df$p <- NA_real_

  tokens_a <- as.numeric(sum(dfmat_group["A", ]))
  tokens_b <- as.numeric(sum(dfmat_group["B", ]))
  if (is.na(tokens_a) || tokens_a <= 0 || is.na(tokens_b) || tokens_b <= 0) {
    stop("Totais de tokens invalidos para grupos A/B.")
  }

  result_df$term <- as.character(result_df$feature)
  result_df$keyness_score <- as.numeric(result_df[[metric_col]])
  result_df$target_count <- as.integer(result_df$n_target)
  result_df$reference_count <- as.integer(result_df$n_reference)
  result_df$p_value <- as.numeric(result_df$p)
  result_df$norm_a <- (result_df$target_count / tokens_a) * 1000000
  result_df$norm_b <- (result_df$reference_count / tokens_b) * 1000000
  result_df$direction <- ifelse(result_df$keyness_score >= 0, "A", "B")

  result_df <- result_df[order(abs(result_df$keyness_score), decreasing = TRUE), ]
  row.names(result_df) <- NULL

  csv_out <- as.character(params$output_csv)
  png_out <- as.character(params$output_plot)
  summary_out <- as.character(params$output_summary)
  dir.create(dirname(csv_out), recursive = TRUE, showWarnings = FALSE)
  dir.create(dirname(png_out), recursive = TRUE, showWarnings = FALSE)
  dir.create(dirname(summary_out), recursive = TRUE, showWarnings = FALSE)

  write.table(
    result_df[, c("term", "keyness_score", "p_value", "target_count", "reference_count", "norm_a", "norm_b", "direction")],
    file = csv_out,
    sep = ";",
    row.names = FALSE,
    col.names = TRUE,
    quote = TRUE,
    fileEncoding = "UTF-8"
  )

  plot_n <- max(5, as.integer(params$top_n))
  width <- max(800, as.integer(params$plot_width))
  height <- max(500, as.integer(params$plot_height))
  name_a <- as.character(params$name_a)
  name_b <- as.character(params$name_b)
  if (!nzchar(name_a)) name_a <- "Corpus A"
  if (!nzchar(name_b)) name_b <- "Corpus B"

  png(filename = png_out, width = width, height = height, res = 130)
  tryCatch(
    {
      quanteda.textplots::textplot_keyness(
        tstat,
        margin = 0.2,
        n = plot_n,
        color = c("#1E3A8A", "#B91C1C")
      )
      title(main = paste0("Keyness (", measure, ") - ", name_a, " vs ", name_b))
    },
    error = function(e) {
      plot.new()
      text(0.5, 0.5, labels = paste("Falha ao gerar plot de keyness:", e$message))
    }
  )
  dev.off()

  summary_payload <- list(
    rows = nrow(result_df),
    docs_a = length(docs_a),
    docs_b = length(docs_b),
    tokens_a = as.numeric(tokens_a),
    tokens_b = as.numeric(tokens_b),
    min_freq = min_freq,
    top_n = plot_n,
    measure = measure
  )
  write(jsonlite::toJSON(summary_payload, auto_unbox = TRUE, pretty = TRUE), file = summary_out)
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Uso: Rscript keyness_quanteda.R <params.json>")
}
params <- read_params(args[[1]])
create_keyness(params)
