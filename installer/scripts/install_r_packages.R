#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 5) {
  cat("Usage: Rscript install_r_packages.R <core_manifest> <optional_manifest> <log_file> <state_json> <libs_user> [cran_mirror] [lock_manifest]\n")
  quit(status = 2)
}

core_manifest <- args[[1]]
optional_manifest <- args[[2]]
log_file <- args[[3]]
state_file <- args[[4]]
libs_user <- args[[5]]
default_mirror <- if (length(args) >= 6 && nzchar(args[[6]])) args[[6]] else "https://cloud.r-project.org"
lock_manifest <- if (length(args) >= 7 && nzchar(args[[7]])) args[[7]] else ""

Sys.setenv(RGL_USE_NULL = "TRUE")
options(rgl.useNULL = TRUE)

log_lines <- c()
append_log <- function(msg) {
  line <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), msg)
  cat(line, "\n")
  log_lines <<- c(log_lines, line)
}

`%||%` <- function(a, b) {
  if (is.null(a)) b else a
}

extract_packages <- function(path) {
  if (!file.exists(path)) {
    append_log(sprintf("Manifest not found: %s", path))
    return(character(0))
  }
  txt <- paste(readLines(path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  start <- regexpr('"packages"\\s*:\\s*\\[', txt, perl = TRUE)
  if (start[1] < 0) {
    append_log(sprintf("No 'packages' key in %s", path))
    return(character(0))
  }
  chunk <- substring(txt, start[1] + attr(start, "match.length"))
  end <- regexpr('\\]', chunk, perl = TRUE)
  if (end[1] < 0) {
    append_log(sprintf("Malformed packages array in %s", path))
    return(character(0))
  }
  arr <- substring(chunk, 1, end[1] - 1)
  m <- gregexpr('"[^"\\n\\r]+"', arr, perl = TRUE)
  vals <- regmatches(arr, m)[[1]]
  if (length(vals) == 0) {
    return(character(0))
  }
  vals <- gsub('^"|"$', '', vals)
  unique(vals[nzchar(vals)])
}

extract_string_value <- function(path, key) {
  if (!file.exists(path)) {
    return("")
  }
  txt <- paste(readLines(path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  pattern <- sprintf('"%s"\\s*:\\s*"([^"]+)"', key)
  m <- regexpr(pattern, txt, perl = TRUE)
  if (m[1] < 0) {
    return("")
  }
  hit <- regmatches(txt, m)
  if (!nzchar(hit)) {
    return("")
  }
  sub(pattern, "\\1", hit, perl = TRUE)
}

check_installed <- function(pkg) {
  suppressWarnings(requireNamespace(pkg, quietly = TRUE))
}

r_version_token <- function() {
  as.character(getRversion())
}

r_version_minor <- function(version = r_version_token()) {
  parts <- strsplit(as.character(version), ".", fixed = TRUE)[[1]]
  if (length(parts) < 2) {
    return(as.character(version))
  }
  paste(parts[[1]], parts[[2]], sep = ".")
}

r_version_at_least <- function(version) {
  getRversion() >= package_version(version)
}

rscript_path <- function() {
  executable <- if (.Platform$OS.type == "windows") "Rscript.exe" else "Rscript"
  normalizePath(file.path(R.home("bin"), executable), winslash = "/", mustWork = FALSE)
}

ensure_versioned_lib_path <- function(path, minor_version) {
  base_path <- normalize_lib_path(path)
  if (!nzchar(base_path)) {
    return("")
  }
  escaped_minor <- gsub(".", "\\.", minor_version, fixed = TRUE)
  if (grepl(sprintf("(^|[/\\\\])%s$", escaped_minor), base_path, perl = TRUE)) {
    return(base_path)
  }
  normalize_lib_path(file.path(base_path, minor_version))
}

has_rtools45 <- function() {
  if (.Platform$OS.type != "windows") {
    return(TRUE)
  }
  make_path <- Sys.which("make")
  if (nzchar(make_path)) {
    return(TRUE)
  }
  any(file.exists(c(
    "C:/rtools45/usr/bin/make.exe",
    "C:/rtools45/x86_64-w64-mingw32.static.posix/bin/gcc.exe",
    "C:/rtools45/x86_64-w64-mingw32.static.posix/bin/g++.exe"
  )))
}

package_built_version <- function(pkg) {
  if (!check_installed(pkg)) {
    return("")
  }
  built <- tryCatch(packageDescription(pkg)$Built, error = function(e) "")
  if (is.null(built) || !nzchar(built)) {
    return("")
  }
  match <- regexpr("R [0-9]+\\.[0-9]+(?:\\.[0-9]+)?", built, perl = TRUE)
  if (match[1] < 0) {
    return("")
  }
  sub("^R ", "", regmatches(built, match))
}

package_needs_reinstall_for_r <- function(pkg) {
  if (!check_installed(pkg)) {
    return(FALSE)
  }
  desc <- tryCatch(packageDescription(pkg), error = function(e) NULL)
  if (is.null(desc)) {
    return(TRUE)
  }
  needs_compilation <- identical(tolower(as.character(desc$NeedsCompilation %||% "no")), "yes")
  if (!needs_compilation) {
    return(FALSE)
  }
  built_version <- package_built_version(pkg)
  if (!nzchar(built_version)) {
    return(FALSE)
  }
  !identical(r_version_minor(built_version), r_version_minor())
}

package_built_record <- function(pkg) {
  desc <- tryCatch(packageDescription(pkg), error = function(e) NULL)
  if (is.null(desc)) {
    return(list(installed = FALSE, version = "", built = "", needs_compilation = ""))
  }
  list(
    installed = TRUE,
    version = as.character(desc$Version %||% ""),
    built = as.character(desc$Built %||% ""),
    needs_compilation = as.character(desc$NeedsCompilation %||% "")
  )
}

normalize_lib_path <- function(path) {
  if (is.null(path) || !nzchar(path)) {
    return("")
  }
  normalizePath(path, winslash = "/", mustWork = FALSE)
}

ensure_writable_library <- function(path) {
  if (!nzchar(path)) {
    append_log("Invalid libs_user path (empty).")
    return(FALSE)
  }

  dir.create(path, recursive = TRUE, showWarnings = FALSE)
  test_file <- file.path(path, sprintf(".write_test_%d", as.integer(Sys.time())))
  ok <- FALSE
  err <- ""

  tryCatch({
    writeLines("ok", test_file, useBytes = TRUE)
    file.remove(test_file)
    ok <- TRUE
  }, error = function(e) {
    err <<- conditionMessage(e)
  })

  if (!ok) {
    append_log(sprintf("R library path is not writable: %s", path))
    if (nzchar(err)) {
      append_log(sprintf("Write test error: %s", err))
    }
    return(FALSE)
  }

  append_log(sprintf("Writable R library path confirmed: %s", path))
  TRUE
}

probe_cran_mirror <- function(mirror) {
  result <- list(ok = FALSE, count = 0L, error = "")
  tryCatch({
    available <- available.packages(repos = mirror)
    result$count <- nrow(available)
    result$ok <- result$count > 0
  }, error = function(e) {
    result$error <<- conditionMessage(e)
  })
  result
}

select_cran_mirror <- function(candidates) {
  diagnostics <- list()
  for (mirror in candidates) {
    append_log(sprintf("Testing CRAN mirror: %s", mirror))
    probe <- probe_cran_mirror(mirror)
    diagnostics[[mirror]] <- probe
    if (isTRUE(probe$ok)) {
      append_log(sprintf("CRAN mirror selected: %s (packages=%d)", mirror, probe$count))
      return(list(ok = TRUE, mirror = mirror, diagnostics = diagnostics))
    }
    err_text <- if (nzchar(probe$error)) probe$error else "empty package index"
    append_log(sprintf("[WARN] Mirror unavailable: %s (%s)", mirror, err_text))
  }
  list(ok = FALSE, mirror = "", diagnostics = diagnostics)
}

order_packages_by_dependency <- function(pkgs) {
  priority <- c(
    "jsonlite", "XML", "Matrix", "Rmpfr",
    "slam", "topicmodels", "png",
    "ggplot2", "scales", "reshape2", "dplyr", "tidyr",
    "ggwordcloud", "syuzhet", "fmsb",
    "igraph", "cluster", "ca", "proxy", "ape", "MASS", "ade4",
    "quanteda", "quanteda.textstats", "quanteda.textplots",
    "stopwords", "stringi",
    "ggraph", "wordcloud", "wordcloud2", "network", "sna", "intergraph",
    "colorspace", "RColorBrewer", "scatterplot3d", "irlba",
    "servr", "rgl", "textometry", "rgexf", "ldatuning"
  )
  unique(c(intersect(priority, pkgs), setdiff(pkgs, priority)))
}

cleanup_install_artifacts <- function(pkg, libs_user_path = "") {
  if (!nzchar(libs_user_path)) {
    return(invisible(FALSE))
  }
  lock_paths <- c(
    file.path(libs_user_path, "00LOCK"),
    file.path(libs_user_path, sprintf("00LOCK-%s", pkg))
  )
  for (path in lock_paths) {
    if (dir.exists(path)) {
      append_log(sprintf("[WARN] Removing stale R install lock: %s", path))
      unlink(path, recursive = TRUE, force = TRUE)
    }
  }
  invisible(TRUE)
}

archive_source_url <- function(pkg) {
  switch(
    pkg,
    "ldatuning" = "https://cran.r-project.org/src/contrib/Archive/ldatuning/ldatuning_1.0.2.tar.gz",
    "rgexf" = "https://cran.r-project.org/src/contrib/Archive/rgexf/rgexf_0.16.2.tar.gz",
    ""
  )
}

install_archive_source <- function(pkg, url, libs_user_path = "") {
  result <- list(ok = FALSE, archive_source = url, error = "")
  if (!nzchar(url)) {
    result$error <- "archive URL absent"
    return(result)
  }
  append_log(sprintf("[WARN] Trying CRAN Archive fallback for %s: %s", pkg, url))
  cleanup_install_artifacts(pkg, libs_user_path)
  tryCatch({
    if (nzchar(libs_user_path)) {
      install.packages(
        url,
        repos = NULL,
        lib = libs_user_path,
        quiet = TRUE,
        dependencies = FALSE,
        type = "source"
      )
    } else {
      install.packages(
        url,
        repos = NULL,
        quiet = TRUE,
        dependencies = FALSE,
        type = "source"
      )
    }
    result$ok <- check_installed(pkg)
    if (!result$ok) {
      result$error <- "package absent after CRAN Archive install"
    }
  }, error = function(e) {
    result$error <<- conditionMessage(e)
  })
  if (isTRUE(result$ok)) {
    append_log(sprintf("[OK] %s installed from CRAN Archive", pkg))
  } else {
    append_log(sprintf("[FAIL] CRAN Archive fallback for %s failed: %s", pkg, result$error))
  }
  result
}

safe_install <- function(pkg, mirrors, retries = 3, timeout_sec = 1200, libs_user_path = "", allow_source_fallback = FALSE) {
  deps <- c("Depends", "Imports", "LinkingTo")
  binary_type <- if (.Platform$OS.type == "windows") "binary" else "source"
  used_fallback_source <- FALSE
  last_error <- ""

  for (attempt in seq_len(retries)) {
    mirror <- mirrors[((attempt - 1) %% length(mirrors)) + 1]
    options(timeout = timeout_sec, repos = c(CRAN = mirror))
    append_log(sprintf("Installing %s (attempt %d/%d, mirror=%s)", pkg, attempt, retries, mirror))

    ok <- FALSE
    last_error <- ""
    cleanup_install_artifacts(pkg, libs_user_path)

    install_once <- function(type) {
      tryCatch({
        if (nzchar(libs_user_path)) {
          install.packages(
            pkg,
            repos = mirror,
            lib = libs_user_path,
            quiet = TRUE,
            dependencies = deps,
            type = type
          )
        } else {
          install.packages(
            pkg,
            repos = mirror,
            quiet = TRUE,
            dependencies = deps,
            type = type
          )
        }
        ok <<- check_installed(pkg)
      }, error = function(e) {
        last_error <<- conditionMessage(e)
      })
    }

    install_once(binary_type)

    if (!ok && binary_type == "binary" && attempt == retries && isTRUE(allow_source_fallback)) {
      append_log(sprintf("[WARN] %s binary installation failed; trying source fallback", pkg))
      used_fallback_source <- TRUE
      install_once("source")
    }

    if (ok) {
      append_log(sprintf("[OK] %s", pkg))
      return(list(
        ok = TRUE,
        attempts = attempt,
        mirror = mirror,
        fallback_source = used_fallback_source,
        archive_source = "",
        error = ""
      ))
    }

    if (!nzchar(last_error)) {
      last_error <- "installation failed without explicit error"
    }
    append_log(sprintf("[WARN] %s attempt %d failed: %s", pkg, attempt, last_error))
  }

  fallback_mirrors <- unique(c(
    "https://cloud.r-project.org",
    "https://cran.rstudio.com",
    "https://cran.r-project.org"
  ))
  for (mirror in fallback_mirrors) {
    cleanup_install_artifacts(pkg, libs_user_path)
    options(timeout = timeout_sec, repos = c(CRAN = mirror))
    append_log(sprintf("[WARN] Final clean retry for %s (mirror=%s)", pkg, mirror))
    last_error <- ""
    tryCatch({
      install.packages(
        pkg,
        repos = mirror,
        lib = if (nzchar(libs_user_path)) libs_user_path else NULL,
        quiet = FALSE,
        dependencies = TRUE,
        type = binary_type
      )
    }, error = function(e) {
      last_error <<- conditionMessage(e)
    })
    if (check_installed(pkg)) {
      append_log(sprintf("[OK] %s installed on final clean retry", pkg))
      return(list(
        ok = TRUE,
        attempts = retries + 1,
        mirror = mirror,
        fallback_source = used_fallback_source,
        archive_source = "",
        error = ""
      ))
    }
    if (!nzchar(last_error)) {
      last_error <- "final clean retry failed without explicit error"
    }
    append_log(sprintf("[WARN] Final clean retry for %s failed: %s", pkg, last_error))
  }

  archive_url <- archive_source_url(pkg)
  if (nzchar(archive_url)) {
    archive_result <- install_archive_source(pkg, archive_url, libs_user_path)
    if (isTRUE(archive_result$ok)) {
      return(list(
        ok = TRUE,
        attempts = retries + 2,
        mirror = "",
        fallback_source = TRUE,
        archive_source = archive_url,
        error = ""
      ))
    }
    if (nzchar(archive_result$error)) {
      last_error <- archive_result$error
    }
  }

  append_log(sprintf("[FAIL] %s", pkg))
  list(
    ok = FALSE,
    attempts = retries,
    mirror = mirrors[[length(mirrors)]],
    fallback_source = used_fallback_source,
    archive_source = archive_url,
    error = last_error
  )
}

find_text_pipeline_script <- function(core_manifest_path) {
  installer_root <- dirname(dirname(normalizePath(core_manifest_path, winslash = "/", mustWork = FALSE)))
  app_root <- dirname(installer_root)
  candidates <- c(
    file.path(app_root, "Rscripts", "text_pipeline.R"),
    file.path(app_root, "_internal", "Rscripts", "text_pipeline.R"),
    file.path(getwd(), "Rscripts", "text_pipeline.R"),
    file.path(getwd(), "_internal", "Rscripts", "text_pipeline.R")
  )
  hits <- candidates[file.exists(candidates)]
  if (length(hits) == 0) {
    return("")
  }
  hits[[1]]
}

run_text_pipeline_smoke <- function(core_manifest_path) {
  result <- list(ok = FALSE, reason = "not_run", script = "")
  script_path <- find_text_pipeline_script(core_manifest_path)
  result$script <- script_path
  if (!nzchar(script_path)) {
    result$reason <- "text_pipeline.R not found"
    return(result)
  }
  input_file <- tempfile(fileext = ".json")
  output_file <- tempfile(fileext = ".json")
  payload <- list(
    text = "**** *doc_1\nEste e um corpus de teste para validar o pipeline textual.",
    mode = "iramuteq",
    options = list(
      lowercase = FALSE,
      remove_numbers = FALSE,
      remove_accents = FALSE,
      clean_web_data = FALSE,
      detect_bigrams = FALSE,
      aggressive_noise_filter = TRUE,
      bigram_top_n = 5,
      bigram_min_freq = 2
    ),
    selected_bigrams = list(),
    extra_stopwords = list()
  )
  output <- character(0)
  status <- tryCatch({
    jsonlite::write_json(payload, input_file, auto_unbox = TRUE)
    output <- system2(
      rscript_path(),
      c("--vanilla", "--slave", script_path, input_file, output_file),
      stdout = TRUE,
      stderr = TRUE
    )
    attr(output, "status") %||% 0L
  }, error = function(e) {
    result$reason <<- conditionMessage(e)
    1L
  })
  if (!identical(status, 0L) || !file.exists(output_file)) {
    if (!nzchar(result$reason)) {
      result$reason <- sprintf(
        "pipeline status=%s output=%s",
        as.character(status),
        paste(output, collapse = " | ")
      )
    }
    return(result)
  }
  data <- tryCatch(jsonlite::read_json(output_file), error = function(e) list(ok = FALSE, error = conditionMessage(e)))
  result$ok <- isTRUE(data$ok)
  result$reason <- if (result$ok) "" else as.character(data$error %||% "pipeline returned ok=false")
  result
}

render_ggwordcloud_shape <- function(shape_name, output_file) {
  words_df <- data.frame(
    word = c(
      "analise", "texto", "metodo", "resultado", "dados",
      "ciencia", "pesquisa", "corpus", "lexico", "classe",
      "rede", "nuvem", "estatistica", "contexto", "similaridade"
    ),
    freq = c(30, 28, 25, 22, 20, 18, 16, 14, 12, 11, 10, 9, 8, 7, 6),
    stringsAsFactors = FALSE
  )
  set.seed(42)
  p <- ggplot2::ggplot(words_df, ggplot2::aes(label = word, size = freq)) +
    ggwordcloud::geom_text_wordcloud_area(
      shape = shape_name,
      rm_outside = TRUE,
      seed = 42,
      grid_size = 4,
      max_steps = 60
    ) +
    ggplot2::scale_size_area(max_size = 32) +
    ggplot2::theme_void()
  ggplot2::ggsave(
    filename = output_file,
    plot = p,
    width = 1200 / 300,
    height = 1200 / 300,
    dpi = 300,
    units = "in",
    bg = "white"
  )
  file.exists(output_file) && (file.info(output_file)$size > 0)
}

run_ggwordcloud_shape_smoke <- function() {
  result <- list(
    ok = FALSE,
    reason = "",
    circle_hash = "",
    star_hash = "",
    circle_file = "",
    star_file = ""
  )
  tryCatch({
    suppressPackageStartupMessages(library(ggplot2, quietly = TRUE, warn.conflicts = FALSE))
    suppressPackageStartupMessages(library(ggwordcloud, quietly = TRUE, warn.conflicts = FALSE))
    smoke_dir <- tempfile(pattern = "lexi_ggwordcloud_shape_")
    dir.create(smoke_dir, recursive = TRUE, showWarnings = FALSE)
    circle_file <- file.path(smoke_dir, "shape_circle.png")
    star_file <- file.path(smoke_dir, "shape_star.png")
    ok_circle <- render_ggwordcloud_shape("circle", circle_file)
    ok_star <- render_ggwordcloud_shape("star", star_file)
    if (!ok_circle || !ok_star) {
      result$reason <- "shape render file missing"
      return(result)
    }
    circle_hash <- as.character(tools::md5sum(circle_file)[1])
    star_hash <- as.character(tools::md5sum(star_file)[1])
    result$circle_hash <- circle_hash
    result$star_hash <- star_hash
    result$circle_file <- circle_file
    result$star_file <- star_file
    if (!nzchar(circle_hash) || !nzchar(star_hash)) {
      result$reason <- "empty md5 hash"
      return(result)
    }
    if (identical(circle_hash, star_hash)) {
      result$reason <- "circle and star hashes are identical"
      return(result)
    }
    result$ok <- TRUE
    result
  }, error = function(e) {
    result$reason <<- conditionMessage(e)
    result
  })
}

install_ggwordcloud_from_github <- function(mirror, libs_user_path) {
  response <- list(ok = FALSE, error = "")
  pkg_type <- if (.Platform$OS.type == "windows") "binary" else "source"
  deps <- c("Depends", "Imports", "LinkingTo")
  tryCatch({
    if (!check_installed("remotes")) {
      append_log("Installing 'remotes' for ggwordcloud GitHub fallback...")
      if (nzchar(libs_user_path)) {
        install.packages(
          "remotes",
          repos = mirror,
          lib = libs_user_path,
          quiet = TRUE,
          dependencies = deps,
          type = pkg_type
        )
      } else {
        install.packages(
          "remotes",
          repos = mirror,
          quiet = TRUE,
          dependencies = deps,
          type = pkg_type
        )
      }
    }
    if (!check_installed("remotes")) {
      stop("Pacote remotes nao disponivel para fallback GitHub.")
    }
    append_log("Installing ggwordcloud from GitHub: lepennec/ggwordcloud")
    if (nzchar(libs_user_path)) {
      remotes::install_github(
        "lepennec/ggwordcloud",
        lib = libs_user_path,
        dependencies = TRUE,
        quiet = TRUE,
        upgrade = "never"
      )
    } else {
      remotes::install_github(
        "lepennec/ggwordcloud",
        dependencies = TRUE,
        quiet = TRUE,
        upgrade = "never"
      )
    }
    response$ok <- check_installed("ggwordcloud")
    if (!response$ok) {
      response$error <- "ggwordcloud absent after GitHub install"
    }
    response
  }, error = function(e) {
    response$error <<- conditionMessage(e)
    response
  })
}

write_state <- function(state) {
  dir.create(dirname(state_file), recursive = TRUE, showWarnings = FALSE)

  if (!check_installed("jsonlite")) {
    try(
      install.packages(
        "jsonlite",
        repos = state$cran_mirror,
        lib = libs_user_norm,
        quiet = TRUE,
        dependencies = c("Depends", "Imports", "LinkingTo"),
        type = if (.Platform$OS.type == "windows") "binary" else "source"
      ),
      silent = TRUE
    )
  }

  if (check_installed("jsonlite")) {
    tryCatch({
      json <- jsonlite::toJSON(state, auto_unbox = TRUE, pretty = TRUE)
      writeLines(json, state_file, useBytes = TRUE)
      return(invisible(TRUE))
    }, error = function(e) {
      append_log(sprintf("Failed to write JSON state via jsonlite: %s", conditionMessage(e)))
    })
  }

  fallback <- c(
    sprintf("timestamp=%s", state$timestamp),
    sprintf("r_version=%s", state$r_version),
    sprintf("r_version_minor=%s", state$r_version_minor),
    sprintf("rscript_path=%s", state$rscript_path),
    sprintf("cran_mirror=%s", state$cran_mirror),
    sprintf("libs_user=%s", state$libs_user),
    sprintf("core_success=%s", ifelse(isTRUE(state$core_success), "true", "false")),
    sprintf("optional_success=%s", ifelse(isTRUE(state$optional_success), "true", "false")),
    sprintf("critical_load_success=%s", ifelse(isTRUE(state$critical_load_success), "true", "false")),
    sprintf("functional_smoke_success=%s", ifelse(isTRUE(state$functional_smoke_success), "true", "false"))
  )
  tryCatch({
    writeLines(fallback, state_file, useBytes = TRUE)
  }, error = function(e) {
    append_log(sprintf("Failed to write fallback state file: %s", conditionMessage(e)))
  })
}

dir.create(dirname(log_file), recursive = TRUE, showWarnings = FALSE)

current_r_version <- r_version_token()
current_r_minor <- r_version_minor(current_r_version)
current_rscript_path <- rscript_path()
libs_user_norm <- ensure_versioned_lib_path(libs_user, current_r_minor)
dir.create(libs_user_norm, recursive = TRUE, showWarnings = FALSE)

if (!ensure_writable_library(libs_user_norm)) {
  writeLines(log_lines, log_file, useBytes = TRUE)
  quit(status = 2)
}

append_log(sprintf("R version: %s", current_r_version))
append_log(sprintf("R minor library token: %s", current_r_minor))
append_log(sprintf("Rscript path: %s", current_rscript_path))
append_log("RGL headless mode enabled for installer validation.")

cloud_mirrors <- c(
  "https://cloud.r-project.org",
  "https://cran.rstudio.com",
  "https://cran.r-project.org",
  "https://cran.ufrj.br"
)
candidate_mirrors <- unique(c(default_mirror, cloud_mirrors))
if (r_version_at_least("4.6.0")) {
  candidate_mirrors <- unique(c(cloud_mirrors, default_mirror))
}

lock_snapshot <- ""
lock_snapshot_mirror <- ""
lock_packages <- character(0)
lock_enabled <- FALSE
if (nzchar(lock_manifest)) {
  if (!file.exists(lock_manifest)) {
    append_log(sprintf("Lock manifest not found: %s", lock_manifest))
    writeLines(log_lines, log_file, useBytes = TRUE)
    quit(status = 2)
  }
  lock_enabled <- TRUE
  lock_snapshot <- extract_string_value(lock_manifest, "r_snapshot")
  lock_packages <- extract_packages(lock_manifest)
  if (nzchar(lock_snapshot) && !r_version_at_least("4.6.0")) {
    lock_snapshot_mirror <- sprintf("https://packagemanager.posit.co/cran/%s", lock_snapshot)
    candidate_mirrors <- unique(c(lock_snapshot_mirror, candidate_mirrors))
    append_log(sprintf("R lock snapshot enabled: %s", lock_snapshot))
    append_log(sprintf("Snapshot mirror candidate: %s", lock_snapshot_mirror))
  } else if (nzchar(lock_snapshot)) {
    append_log(
      sprintf(
        "R %s detected; ignoring legacy snapshot %s and using live CRAN mirrors.",
        current_r_version,
        lock_snapshot
      )
    )
  } else {
    append_log("R lock manifest loaded without snapshot date; using default mirrors.")
  }
  if (length(lock_packages) > 0) {
    append_log(sprintf("R lock package count: %d", length(lock_packages)))
  }
}

mirror_selection <- select_cran_mirror(candidate_mirrors)
mirror_available <- isTRUE(mirror_selection$ok)
if (!mirror_available) {
  append_log("No CRAN mirror is reachable. Proceeding in offline verification mode.")
  cran_mirror <- default_mirror
} else {
  cran_mirror <- mirror_selection$mirror
}
options(timeout = 900, repos = c(CRAN = cran_mirror))

system_libs <- vapply(c(.Library.site, .Library), normalize_lib_path, character(1))
target_libs <- unique(c(libs_user_norm, system_libs))
target_libs <- target_libs[nzchar(target_libs)]

if (length(target_libs) == 0) {
  append_log("Could not determine valid R library paths.")
  writeLines(log_lines, log_file, useBytes = TRUE)
  quit(status = 2)
}

.libPaths(target_libs)
Sys.setenv(R_LIBS_USER = libs_user_norm)
Sys.setenv(LEXIANALYST_R_LIBS_USER = libs_user_norm)

append_log(sprintf("Using CRAN mirror: %s", cran_mirror))
append_log(sprintf("Using R library path: %s", libs_user_norm))
append_log(sprintf("Effective .libPaths: %s", paste(.libPaths(), collapse = " | ")))

core_pkgs <- order_packages_by_dependency(extract_packages(core_manifest))
if (lock_enabled && length(lock_packages) > 0) {
  # Lock packages are authoritative for deterministic runtime.
  core_pkgs <- order_packages_by_dependency(unique(c(lock_packages, core_pkgs)))
}
opt_pkgs <- extract_packages(optional_manifest)

append_log(sprintf("Core package count: %d", length(core_pkgs)))
append_log(sprintf("Optional package count: %d", length(opt_pkgs)))

core_results <- list()
opt_results <- list()
allow_source_fallback <- has_rtools45()
append_log(sprintf("R source fallback allowed: %s", ifelse(allow_source_fallback, "yes", "no")))

for (pkg in core_pkgs) {
  if (check_installed(pkg) && !package_needs_reinstall_for_r(pkg)) {
    append_log(sprintf("[SKIP] %s already installed", pkg))
    core_results[[pkg]] <- list(ok = TRUE, attempts = 0, mirror = "", fallback_source = FALSE, archive_source = "", error = "")
  } else if (!mirror_available) {
    append_log(sprintf("[FAIL] %s missing and no CRAN mirror available (offline mode)", pkg))
    core_results[[pkg]] <- list(
      ok = FALSE,
      attempts = 0,
      mirror = "",
      fallback_source = FALSE,
      error = "offline_no_cran_mirror"
    )
  } else {
    if (check_installed(pkg)) {
      append_log(sprintf("[WARN] %s was built for another R minor version; reinstalling", pkg))
    }
    core_results[[pkg]] <- safe_install(
      pkg,
      mirrors = candidate_mirrors,
      retries = 3,
      timeout_sec = 1200,
      libs_user_path = libs_user_norm,
      allow_source_fallback = allow_source_fallback
    )
  }
}

for (pkg in opt_pkgs) {
  if (check_installed(pkg) && !package_needs_reinstall_for_r(pkg)) {
    append_log(sprintf("[SKIP] %s already installed (optional)", pkg))
    opt_results[[pkg]] <- list(ok = TRUE, attempts = 0, mirror = "", fallback_source = FALSE, archive_source = "", error = "")
  } else if (!mirror_available) {
    append_log(sprintf("[WARN] Optional package %s missing (offline mode without CRAN).", pkg))
    opt_results[[pkg]] <- list(
      ok = FALSE,
      attempts = 0,
      mirror = "",
      fallback_source = FALSE,
      error = "offline_no_cran_mirror"
    )
  } else {
    if (check_installed(pkg)) {
      append_log(sprintf("[WARN] Optional package %s was built for another R minor version; reinstalling", pkg))
    }
    opt_results[[pkg]] <- safe_install(
      pkg,
      mirrors = candidate_mirrors,
      retries = 2,
      timeout_sec = 600,
      libs_user_path = libs_user_norm,
      allow_source_fallback = allow_source_fallback
    )
  }
}

core_failed <- names(core_results)[!vapply(core_results, function(x) isTRUE(x$ok), logical(1))]
opt_failed <- names(opt_results)[!vapply(opt_results, function(x) isTRUE(x$ok), logical(1))]

critical_load_pkgs <- unique(core_pkgs)

critical_load_failed <- character(0)
for (pkg in critical_load_pkgs) {
  append_log(sprintf("Validating package load: %s", pkg))
  loaded_ok <- FALSE
  load_error <- ""
  tryCatch({
    suppressPackageStartupMessages(
      library(pkg, character.only = TRUE, quietly = TRUE, warn.conflicts = FALSE)
    )
    loaded_ok <- TRUE
  }, error = function(e) {
    load_error <<- conditionMessage(e)
  })

  if (!loaded_ok) {
    critical_load_failed <- c(critical_load_failed, pkg)
    if (!nzchar(load_error)) {
      load_error <- "failed to load with no details"
    }
    append_log(sprintf("[FAIL] Could not load '%s': %s", pkg, load_error))
  } else if (package_needs_reinstall_for_r(pkg)) {
    critical_load_failed <- c(critical_load_failed, pkg)
    append_log(
      sprintf(
        "[FAIL] Package '%s' loaded from a library built for another R minor version (Built: %s; current R: %s)",
        pkg,
        package_built_version(pkg),
        current_r_version
      )
    )
  } else {
    append_log(sprintf("[OK] Package '%s' loaded", pkg))
  }
}

functional_smoke_failed <- character(0)
ggwordcloud_github_fallback_used <- FALSE
ggwordcloud_github_fallback_ok <- FALSE
ggwordcloud_shape_smoke_result <- list(
  ok = FALSE,
  reason = "not_run",
  circle_hash = "",
  star_hash = "",
  circle_file = "",
  star_file = ""
)
text_pipeline_smoke_result <- list(
  ok = FALSE,
  reason = "not_run",
  script = ""
)

wordcloud_smoke_error <- ""
wordcloud_smoke_ok <- FALSE
tryCatch({
  suppressPackageStartupMessages(library(wordcloud, quietly = TRUE, warn.conflicts = FALSE))
  png_file <- tempfile(fileext = ".png")
  png(png_file, width = 900, height = 600)
  wordcloud::wordcloud(c("teste", "nuvem", "palavra"), c(10, 5, 3), scale = c(2, 0.5))
  dev.off()
  wordcloud_smoke_ok <- file.exists(png_file) && (file.info(png_file)$size > 0)
}, error = function(e) {
  if (dev.cur() != 1) {
    try(dev.off(), silent = TRUE)
  }
  wordcloud_smoke_error <<- conditionMessage(e)
})

if (!wordcloud_smoke_ok) {
  functional_smoke_failed <- c(functional_smoke_failed, "wordcloud")
  if (!nzchar(wordcloud_smoke_error)) {
    wordcloud_smoke_error <- "wordcloud render output missing"
  }
  append_log(sprintf("[FAIL] wordcloud functional smoke test failed: %s", wordcloud_smoke_error))
} else {
  append_log("[OK] wordcloud functional smoke test passed")
}

if (check_installed("ggwordcloud") && check_installed("ggplot2")) {
  ggwordcloud_shape_smoke_result <- run_ggwordcloud_shape_smoke()
  if (!isTRUE(ggwordcloud_shape_smoke_result$ok)) {
    append_log(
      sprintf(
        "[WARN] ggwordcloud shape smoke failed after CRAN install: %s",
        ggwordcloud_shape_smoke_result$reason
      )
    )
    ggwordcloud_github_fallback_used <- TRUE
    github_fallback <- install_ggwordcloud_from_github(cran_mirror, libs_user_norm)
    ggwordcloud_github_fallback_ok <- isTRUE(github_fallback$ok)
    if (!ggwordcloud_github_fallback_ok) {
      append_log(
        sprintf(
          "[WARN] GitHub fallback for ggwordcloud failed: %s",
          github_fallback$error
        )
      )
    } else {
      append_log("[OK] GitHub fallback for ggwordcloud completed")
      ggwordcloud_shape_smoke_result <- run_ggwordcloud_shape_smoke()
    }
  }

  if (!isTRUE(ggwordcloud_shape_smoke_result$ok)) {
    functional_smoke_failed <- c(functional_smoke_failed, "ggwordcloud_shape")
    append_log(
      sprintf(
        "[FAIL] ggwordcloud shape smoke test failed: %s",
        ggwordcloud_shape_smoke_result$reason
      )
    )
  } else {
    append_log("[OK] ggwordcloud shape smoke test passed")
  }
} else {
  functional_smoke_failed <- c(functional_smoke_failed, "ggwordcloud_missing")
  append_log("[FAIL] ggwordcloud/ggplot2 not available for shape smoke test")
}

if (check_installed("jsonlite") && check_installed("quanteda") && check_installed("stopwords") && check_installed("stringi")) {
  text_pipeline_smoke_result <- run_text_pipeline_smoke(core_manifest)
  if (!isTRUE(text_pipeline_smoke_result$ok)) {
    functional_smoke_failed <- c(functional_smoke_failed, "text_pipeline")
    append_log(sprintf("[FAIL] text_pipeline.R smoke test failed: %s", text_pipeline_smoke_result$reason))
  } else {
    append_log("[OK] text_pipeline.R smoke test passed")
  }
} else {
  functional_smoke_failed <- c(functional_smoke_failed, "text_pipeline_dependencies")
  append_log("[FAIL] text_pipeline.R smoke test skipped because required packages are unavailable")
}

all_runtime_pkgs <- unique(c(core_pkgs, opt_pkgs, critical_load_pkgs))
archive_sources <- setNames(vapply(all_runtime_pkgs, archive_source_url, character(1)), all_runtime_pkgs)
archive_sources <- archive_sources[nzchar(archive_sources)]
package_builds <- setNames(lapply(all_runtime_pkgs, package_built_record), all_runtime_pkgs)
r_packages_built_mismatch <- all_runtime_pkgs[
  vapply(all_runtime_pkgs, package_needs_reinstall_for_r, logical(1))
]

state <- list(
  timestamp = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
  r_version = current_r_version,
  r_version_minor = current_r_minor,
  rscript_path = current_rscript_path,
  cran_mirror = cran_mirror,
  cran_candidates = candidate_mirrors,
  lock_enabled = lock_enabled,
  lock_manifest = lock_manifest,
  lock_snapshot = lock_snapshot,
  lock_snapshot_mirror = lock_snapshot_mirror,
  lock_package_count = length(lock_packages),
  archive_sources = as.list(archive_sources),
  mirror_available = mirror_available,
  libs_user = libs_user_norm,
  lib_paths = .libPaths(),
  core_packages = core_pkgs,
  optional_packages = opt_pkgs,
  core_failed = core_failed,
  optional_failed = opt_failed,
  critical_load_failed = critical_load_failed,
  package_builds = package_builds,
  r_packages_built_mismatch = r_packages_built_mismatch,
  functional_smoke_failed = functional_smoke_failed,
  ggwordcloud_shape_smoke = ggwordcloud_shape_smoke_result,
  text_pipeline_smoke = text_pipeline_smoke_result,
  ggwordcloud_github_fallback_used = ggwordcloud_github_fallback_used,
  ggwordcloud_github_fallback_ok = ggwordcloud_github_fallback_ok,
  core_success = length(core_failed) == 0,
  optional_success = length(opt_failed) == 0,
  critical_load_success = length(critical_load_failed) == 0,
  functional_smoke_success = length(functional_smoke_failed) == 0,
  core_results = core_results,
  optional_results = opt_results
)

write_state(state)
writeLines(log_lines, log_file, useBytes = TRUE)

if (length(core_failed) > 0) {
  append_log(sprintf("Core package installation failed for: %s", paste(core_failed, collapse = ", ")))
  writeLines(log_lines, log_file, useBytes = TRUE)
  quit(status = 1)
}

if (length(critical_load_failed) > 0) {
  append_log(
    sprintf(
      "Critical package load validation failed for: %s",
      paste(critical_load_failed, collapse = ", ")
    )
  )
  writeLines(log_lines, log_file, useBytes = TRUE)
  quit(status = 1)
}

if (length(functional_smoke_failed) > 0) {
  append_log(
    sprintf(
      "Functional smoke validation failed for: %s",
      paste(functional_smoke_failed, collapse = ", ")
    )
  )
  writeLines(log_lines, log_file, useBytes = TRUE)
  quit(status = 1)
}

append_log("Core package installation completed successfully")
writeLines(log_lines, log_file, useBytes = TRUE)
quit(status = 0)
