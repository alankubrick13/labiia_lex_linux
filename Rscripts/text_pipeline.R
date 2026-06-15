#!/usr/bin/env Rscript

suppressWarnings(suppressMessages(library(jsonlite)))
suppressWarnings(suppressMessages(library(quanteda)))
suppressWarnings(suppressMessages(library(stopwords)))
suppressWarnings(suppressMessages(library(stringi)))

`%||%` <- function(a, b) {
  if (is.null(a)) b else a
}

normalize_entry <- function(value) {
  txt <- tolower(trimws(as.character(value %||% "")))
  txt <- gsub("[[:space:]]+", " ", txt, perl = TRUE)
  txt
}

safe_stopwords <- function(lang) {
  out <- character(0)
  for (src in c("snowball", "nltk", "stopwords-iso")) {
    vals <- tryCatch(stopwords::stopwords(language = lang, source = src), error = function(e) character(0))
    if (length(vals) > 0) {
      out <- c(out, vals)
      break
    }
  }
  unique(normalize_entry(out))
}

extract_selected_pairs <- function(items) {
  phrases <- list()
  if (is.null(items) || length(items) == 0) {
    return(phrases)
  }
  for (item in items) {
    expr <- normalize_entry(item$expression %||% "")
    repl <- normalize_entry(item$replacement %||% "")
    parts <- unlist(strsplit(expr, " ", fixed = TRUE))
    parts <- parts[nzchar(parts)]
    if (length(parts) < 2 || length(parts) > 6 || !nzchar(repl)) {
      next
    }
    phrases[[length(phrases) + 1L]] <- list(tokens = parts, replacement = repl, n_tokens = length(parts))
  }
  if (length(phrases) > 1L) {
    ord <- order(vapply(phrases, function(x) as.integer(x$n_tokens), integer(1)), decreasing = TRUE)
    phrases <- phrases[ord]
  }
  phrases
}

tokenize_line <- function(line) {
  toks <- quanteda::tokens(
    line,
    what = "word",
    remove_punct = TRUE,
    remove_symbols = TRUE,
    remove_numbers = FALSE,
    split_hyphens = TRUE,
    include_docvars = FALSE
  )
  values <- as.character((as.list(toks)[[1]]) %||% character(0))
  if (length(values) == 0) {
    return(character(0))
  }
  normalize_entry(values)
}

is_noise_token <- function(tok, remove_numbers, aggressive_noise_filter) {
  if (!nzchar(tok)) {
    return(TRUE)
  }
  if (grepl("^[_]+$", tok, perl = TRUE)) {
    return(TRUE)
  }
  if (grepl("^[[:punct:]]+$", tok, perl = TRUE)) {
    return(TRUE)
  }
  if (!isTRUE(remove_numbers)) {
    return(FALSE)
  }
  if (grepl("[0-9]", tok, perl = TRUE)) {
    return(TRUE)
  }
  if (grepl("^[ivxlcdm]{1,6}$", tok, perl = TRUE)) {
    return(TRUE)
  }
  if (isTRUE(aggressive_noise_filter)) {
    if (nchar(tok, allowNA = FALSE) <= 1) {
      return(TRUE)
    }
    if (nchar(tok, allowNA = FALSE) <= 2 && !tok %in% c("ia", "ai", "uf", "br", "pt")) {
      return(TRUE)
    }
  }
  FALSE
}

apply_pairs_to_tokens <- function(tokens, pairs, stopword_set, allow_bridge) {
  if (length(tokens) < 2 || length(pairs) == 0) {
    return(tokens)
  }
  out <- character(0)
  i <- 1
  n <- length(tokens)
  while (i <= n) {
    merged <- FALSE
    for (phrase in pairs) {
      phrase_tokens <- phrase$tokens %||% character(0)
      phrase_n <- length(phrase_tokens)
      if (phrase_n >= 2L && i + phrase_n - 1L <= n) {
        candidate <- tokens[i:(i + phrase_n - 1L)]
        if (identical(as.character(candidate), as.character(phrase_tokens))) {
          out <- c(out, phrase$replacement)
          i <- i + phrase_n
          merged <- TRUE
          break
        }
      }
    }
    if (!merged) {
      out <- c(out, tokens[[i]])
      i <- i + 1
    }
  }
  out
}

common_trailing_verbs <- c(
  "acontece", "acontecem", "ajuda", "ajudam", "aparece", "aparecem",
  "cresce", "crescem", "demonstra", "demonstram", "faz", "fazem",
  "gera", "geram", "indica", "indicam", "mostra", "mostram",
  "ocorre", "ocorrem", "permite", "permitem", "produz", "produzem",
  "revela", "revelam", "sugere", "sugerem"
)

weak_edge_terms <- c(
  "janeiro", "fevereiro", "marco", "março", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
)

leading_adjective_suffixes <- c("iva", "ivo", "ivas", "ivos", "ial", "iais")
trailing_adjective_suffixes <- c(
  "iva", "ivo", "ivas", "ivos", "ial", "iais",
  "ada", "ado", "adas", "ados", "ida", "ido", "idas", "idos"
)

has_suffix <- function(token, suffixes) {
  token <- as.character(token %||% "")
  any(vapply(suffixes, function(suffix) endsWith(token, suffix), logical(1)))
}

is_weak_multiword_candidate <- function(parts) {
  parts <- tolower(as.character(parts))
  parts <- parts[nzchar(parts)]
  if (length(parts) < 2L) {
    return(TRUE)
  }
  if (parts[[1]] %in% weak_edge_terms || parts[[length(parts)]] %in% weak_edge_terms) {
    return(TRUE)
  }
  if (parts[[length(parts)]] %in% common_trailing_verbs) {
    return(TRUE)
  }
  if (length(parts) == 2L && has_suffix(parts[[1]], leading_adjective_suffixes)) {
    return(has_suffix(parts[[2]], trailing_adjective_suffixes))
  }
  FALSE
}

collect_multiwords <- function(lines, doc_ids, min_freq, top_n, ngram_max, min_is_norm, stopword_set) {
  if (length(lines) == 0) {
    return(list())
  }
  if (missing(doc_ids) || length(doc_ids) != length(lines)) {
    doc_ids <- seq_along(lines)
  }
  ngram_max <- min(3L, max(2L, as.integer(ngram_max %||% 3L)))
  min_freq <- max(1L, as.integer(min_freq %||% 2L))
  top_n <- max(1L, as.integer(top_n %||% 50L))
  min_is_norm <- max(0, as.numeric(min_is_norm %||% 0))

  ngram_counter <- new.env(parent = emptyenv())
  ngram_docs <- new.env(parent = emptyenv())
  ngram_line_starts <- new.env(parent = emptyenv())
  unigram_counter <- new.env(parent = emptyenv())
  total_unigrams <- 0L

  inc_counter <- function(env, key, step = 1L) {
    current <- env[[key]]
    if (is.null(current)) {
      env[[key]] <- as.integer(step)
    } else {
      env[[key]] <- as.integer(current) + as.integer(step)
    }
  }

  add_doc <- function(env, key, doc_id) {
    current <- env[[key]]
    doc_id <- as.integer(doc_id %||% 1L)
    if (is.null(current)) {
      env[[key]] <- doc_id
    } else if (!(doc_id %in% current)) {
      env[[key]] <- c(current, doc_id)
    }
  }

  total_docs <- length(unique(as.integer(doc_ids)))

  for (line_idx in seq_along(lines)) {
    line <- lines[[line_idx]]
    doc_id <- as.integer(doc_ids[[line_idx]] %||% 1L)
    vals <- tokenize_line(line)
    if (length(vals) < 2) {
      next
    }
    for (tok in vals) {
      inc_counter(unigram_counter, tok)
      total_unigrams <- total_unigrams + 1L
    }
    max_n <- min(ngram_max, length(vals))
    for (n_tokens in seq.int(2L, max_n)) {
      for (idx in seq_len(length(vals) - n_tokens + 1L)) {
        parts <- vals[idx:(idx + n_tokens - 1L)]
        if (!all(nzchar(parts))) {
          next
        }
        if (parts[[1]] %in% stopword_set || parts[[length(parts)]] %in% stopword_set) {
          next
        }
        if (!grepl("[[:alpha:]]", paste(parts, collapse = ""), perl = TRUE)) {
          next
        }
        if (is_weak_multiword_candidate(parts)) {
          next
        }
        key <- paste(parts, collapse = " ")
        inc_counter(ngram_counter, key)
        add_doc(ngram_docs, key, doc_id)
        if (idx == 1L) {
          inc_counter(ngram_line_starts, key)
        }
      }
    }
  }

  keys <- ls(ngram_counter, all.names = TRUE)
  if (length(keys) == 0) {
    return(list())
  }
  freq <- vapply(keys, function(k) as.integer(ngram_counter[[k]]), integer(1))
  keep <- which(freq >= min_freq)
  if (length(keep) == 0) {
    return(list())
  }
  keys <- keys[keep]
  freq <- freq[keep]

  doc_counts <- vapply(keys, function(k) length(unique(as.integer(ngram_docs[[k]] %||% integer(0)))), integer(1))
  line_starts <- vapply(keys, function(k) as.integer(ngram_line_starts[[k]] %||% 0L), integer(1))
  n_lengths <- vapply(strsplit(keys, " ", fixed = TRUE), length, integer(1))
  keep_quality <- rep(TRUE, length(keys))
  if (total_docs > 1L) {
    keep_quality <- keep_quality & doc_counts >= 2L
  }
  keep_quality <- keep_quality & (n_lengths < 3L | line_starts > 0L)
  if (!any(keep_quality)) {
    return(list())
  }
  keys <- keys[keep_quality]
  freq <- freq[keep_quality]
  doc_counts <- doc_counts[keep_quality]
  n_lengths <- n_lengths[keep_quality]

  scores <- numeric(length(keys))
  for (idx in seq_along(keys)) {
    parts <- unlist(strsplit(keys[[idx]], " ", fixed = TRUE), use.names = FALSE)
    density <- sum(!parts %in% stopword_set) / max(1L, length(parts))
    rarity <- 0
    for (tok in parts) {
      tok_freq <- max(1L, as.integer(unigram_counter[[tok]] %||% 1L))
      rarity <- rarity + log1p(max(1L, total_unigrams) / tok_freq)
    }
    scores[[idx]] <- as.numeric(freq[[idx]]) * density * rarity * length(parts)
  }
  max_score <- max(scores)
  if (!is.finite(max_score) || max_score <= 0) {
    return(list())
  }
  norm <- scores / max_score
  keep_norm <- which(norm >= min_is_norm)
  if (length(keep_norm) == 0) {
    return(list())
  }
  keys <- keys[keep_norm]
  freq <- freq[keep_norm]
  doc_counts <- doc_counts[keep_norm]
  scores <- scores[keep_norm]
  norm <- norm[keep_norm]

  n_lengths <- n_lengths[keep_norm]
  order_idx <- order(-norm, -scores, -freq, -n_lengths, keys)
  keys <- keys[order_idx]
  freq <- freq[order_idx]
  doc_counts <- doc_counts[order_idx]
  scores <- scores[order_idx]
  norm <- norm[order_idx]
  n_lengths <- n_lengths[order_idx]
  if (length(keys) > top_n) {
    keep_top <- seq_len(top_n)
    keys <- keys[keep_top]
    freq <- freq[keep_top]
    doc_counts <- doc_counts[keep_top]
    scores <- scores[keep_top]
    norm <- norm[keep_top]
    n_lengths <- n_lengths[keep_top]
  }
  out <- vector("list", length(keys))
  for (idx in seq_along(keys)) {
    out[[idx]] <- list(
      expression = keys[[idx]],
      replacement = gsub(" ", "_", keys[[idx]], fixed = TRUE),
      n_tokens = as.integer(n_lengths[[idx]]),
      frequency = as.integer(freq[[idx]]),
      doc_count = as.integer(doc_counts[[idx]]),
      is_score = as.numeric(round(scores[[idx]], 6)),
      is_norm = as.numeric(round(norm[[idx]], 6)),
      method = "is_index",
      selected_default = isTRUE(freq[[idx]] >= min_freq && norm[[idx]] >= 0.25)
    )
  }
  out
}

process_text <- function(payload) {
  opts <- payload$options %||% list()
  text <- as.character(payload$text %||% "")
  lower <- isTRUE(opts$lowercase)
  remove_numbers <- isTRUE(opts$remove_numbers)
  remove_accents <- isTRUE(opts$remove_accents)
  clean_web <- isTRUE(opts$clean_web_data)
  detect_bigrams <- isTRUE(opts$detect_bigrams)
  aggressive_noise_filter <- isTRUE(opts$aggressive_noise_filter)
  bigram_top_n <- as.integer(opts$bigram_top_n %||% 20L)
  bigram_min_freq <- as.integer(opts$bigram_min_freq %||% 2L)
  ngram_max <- as.integer(opts$ngram_max %||% 3L)
  min_is_norm <- as.numeric(opts$min_is_norm %||% 0)

  mandatory <- c("et", "al", "et al", "the", "off")
  extra <- unlist(payload$extra_stopwords %||% character(0), use.names = FALSE)
  extra <- normalize_entry(extra)
  stopword_entries <- unique(c(safe_stopwords("pt"), safe_stopwords("en"), normalize_entry(mandatory), extra))
  stopword_tokens <- unique(unlist(strsplit(stopword_entries, " ", fixed = TRUE), use.names = FALSE))
  stopword_tokens <- stopword_tokens[nzchar(stopword_tokens)]

  selected_pairs <- extract_selected_pairs(payload$selected_bigrams %||% list())
  output_lines <- character(0)
  cleaned_content_lines <- character(0)
  cleaned_content_doc_ids <- integer(0)
  current_doc_id <- 0L

  lines <- unlist(strsplit(text, "\n", fixed = TRUE), use.names = FALSE)
  if (length(lines) == 0) {
    lines <- character(0)
  }

  for (raw in lines) {
    line <- as.character(raw %||% "")
    trimmed <- trimws(line)
    if (!nzchar(trimmed)) {
      output_lines <- c(output_lines, "")
      next
    }
    if (startsWith(trimmed, "****")) {
      current_doc_id <- current_doc_id + 1L
      output_lines <- c(output_lines, trimmed)
      next
    }
    if (current_doc_id == 0L) {
      current_doc_id <- 1L
    }

    txt <- line
    if (isTRUE(clean_web)) {
      txt <- gsub("(https?://|www\\.)\\S+", " ", txt, perl = TRUE)
      txt <- gsub("[[:alnum:]_.%+-]+@[[:alnum:].-]+\\.[[:alpha:]]{2,}", " ", txt, perl = TRUE)
    }
    if (isTRUE(lower)) {
      txt <- tolower(txt)
    }
    if (isTRUE(remove_accents)) {
      txt <- stringi::stri_trans_general(txt, "Latin-ASCII")
    }
    txt <- gsub("[\r\t]+", " ", txt, perl = TRUE)
    txt <- gsub("[[:space:]]+", " ", txt, perl = TRUE)
    txt <- trimws(txt)
    if (!nzchar(txt)) {
      next
    }

    tokens <- tokenize_line(txt)
    if (length(tokens) == 0) {
      next
    }
    tokens <- tokens[!vapply(tokens, is_noise_token, logical(1), remove_numbers = remove_numbers, aggressive_noise_filter = aggressive_noise_filter)]
    if (length(tokens) == 0) {
      next
    }
    tokens <- tokens[!tokens %in% stopword_tokens]
    if (length(tokens) == 0) {
      next
    }

    tokens <- apply_pairs_to_tokens(tokens, selected_pairs, stopword_tokens, allow_bridge = TRUE)
    tokens <- tokens[nzchar(tokens)]
    if (length(tokens) == 0) {
      next
    }

    cleaned <- paste(tokens, collapse = " ")
    output_lines <- c(output_lines, cleaned)
    cleaned_content_lines <- c(cleaned_content_lines, cleaned)
    cleaned_content_doc_ids <- c(cleaned_content_doc_ids, current_doc_id)
  }

  prepared_text <- paste(output_lines, collapse = "\n")
  prepared_text <- gsub("\n{3,}", "\n\n", prepared_text, perl = TRUE)
  prepared_text <- trimws(prepared_text)
  if (nzchar(prepared_text)) {
    prepared_text <- paste0("\n", prepared_text, "\n")
  }

  preview <- prepared_text
  if (nchar(preview) > 2000) {
    preview <- paste0(substr(preview, 1, 2000), "\n\n[... texto truncado para preview ...]")
  }

  bigrams <- list()
  if (isTRUE(detect_bigrams)) {
    bigrams <- collect_multiwords(
      cleaned_content_lines,
      cleaned_content_doc_ids,
      min_freq = bigram_min_freq,
      top_n = bigram_top_n,
      ngram_max = ngram_max,
      min_is_norm = min_is_norm,
      stopword_set = stopword_tokens
    )
  }

  list(
    ok = TRUE,
    prepared_text = prepared_text,
    preview_text = preview,
    bigram_candidates = bigrams,
    warnings = list(),
    diagnostics = list(
      stopword_count = length(stopword_tokens),
      selected_bigram_count = length(selected_pairs),
      multiword_candidates_count = length(bigrams),
      multiword_selected_count = length(selected_pairs),
      multiword_ngram_max = ngram_max,
      multiword_min_is_norm = min_is_norm,
      cleaned_content_lines = length(cleaned_content_lines),
      remove_numbers = remove_numbers,
      aggressive_noise_filter = aggressive_noise_filter
    )
  )
}

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) < 2) {
    stop("Usage: Rscript text_pipeline.R <input_json> <output_json>")
  }
  input_path <- args[[1]]
  output_path <- args[[2]]

  result <- tryCatch({
    payload <- jsonlite::fromJSON(input_path, simplifyVector = FALSE)
    process_text(payload)
  }, error = function(e) {
    list(
      ok = FALSE,
      error = as.character(conditionMessage(e)),
      prepared_text = "",
      preview_text = "",
      bigram_candidates = list(),
      warnings = list(),
      diagnostics = list()
    )
  })

  jsonlite::write_json(result, path = output_path, auto_unbox = TRUE, pretty = FALSE, null = "null")
}

main()
