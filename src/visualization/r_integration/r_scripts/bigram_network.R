# ==============================================================================
# Bigram Network Visualization using ggraph
# LabiiaLex - R Script for Bigram Co-occurrence Network
# ==============================================================================
# This script reads bigram edges from CSV and creates a beautiful network plot
# using ggraph with a force-directed layout.
# ==============================================================================

# Install and load packages
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

ensure_package("igraph")
ensure_package("ggraph")
ensure_package("ggplot2")
ensure_package("dplyr")
ensure_package("jsonlite")
ensure_package("tidyr")

# ==============================================================================
# Helper Functions
# ==============================================================================

read_args <- function(params_file) {
    if (!file.exists(params_file)) {
        stop(paste("Parameters file not found:", params_file))
    }
    jsonlite::fromJSON(params_file)
}

# ==============================================================================
# Main Plotting Function
# ==============================================================================

create_bigram_network <- function(
  edges_file,
  output_file,
  width = 1200,
  height = 900,
  top_words = 30,
  min_freq = 0.5,
  edge_alpha = 0.5,
  edge_color = "#6B7280",
  vertex_color = "#2563EB",
  vertex_size = 4,
  title = "Rede de Coocorrência por Bigramas"
) {
    message("Loading bigram edges...")

    # Read edges CSV (supports both ; and , separators)
    edges_df <- tryCatch(
        read.csv(edges_file, sep = ";", stringsAsFactors = FALSE),
        error = function(e) read.csv(edges_file, stringsAsFactors = FALSE)
    )

    # Ensure column names are correct
    if (!"word_1" %in% names(edges_df)) {
        names(edges_df) <- c("word_1", "word_2", "frequency")
    }

    # Convert frequency to numeric
    edges_df$frequency <- as.numeric(edges_df$frequency)
    edges_df <- edges_df[!is.na(edges_df$frequency) & edges_df$frequency > 0, ]

    if (nrow(edges_df) == 0) {
        stop("No valid edges found in the input file.")
    }

    message(paste("Loaded", nrow(edges_df), "edges"))

    # Calculate word totals for filtering
    word_totals <- edges_df %>%
        tidyr::pivot_longer(cols = c(word_1, word_2), values_to = "word") %>%
        dplyr::group_by(word) %>%
        dplyr::summarise(total = sum(frequency), .groups = "drop") %>%
        dplyr::arrange(desc(total))

    # Get top N words
    n_top <- min(top_words, nrow(word_totals))
    top_words_list <- word_totals$word[seq_len(n_top)]

    # Filter edges to only include top words
    edges_filtered <- edges_df %>%
        dplyr::filter(word_1 %in% top_words_list & word_2 %in% top_words_list)

    if (nrow(edges_filtered) == 0) {
        stop("No edges remaining after filtering to top words.")
    }

    message(paste("Filtered to", nrow(edges_filtered), "edges with top", n_top, "words"))

    # Create igraph object
    g <- igraph::graph_from_data_frame(
        edges_filtered[, c("word_1", "word_2", "frequency")],
        directed = FALSE
    )

    # Set edge weights
    igraph::E(g)$weight <- edges_filtered$frequency

    # Calculate node degree for sizing
    node_degree <- igraph::degree(g)
    node_strength <- igraph::strength(g)

    # Normalize for visual display
    max_strength <- max(node_strength)
    min_strength <- min(node_strength)
    range_strength <- max_strength - min_strength
    if (range_strength == 0) range_strength <- 1

    # Node sizes scaled between vertex_size and vertex_size * 3
    V(g)$size <- vertex_size + ((node_strength - min_strength) / range_strength) * (vertex_size * 2)

    # Edge widths scaled
    max_weight <- max(E(g)$weight)
    E(g)$width <- 0.5 + (E(g)$weight / max_weight) * 2.5

    message("Generating network plot...")

    # Create the plot using ggraph
    set.seed(42) # For reproducible layout
    p <- ggraph(g, layout = "fr") + # Fruchterman-Reingold layout
        geom_edge_link(
            aes(edge_alpha = weight, edge_width = weight),
            color = edge_color,
            show.legend = FALSE
        ) +
        scale_edge_alpha(range = c(0.3, edge_alpha)) +
        scale_edge_width(range = c(0.5, 2.5)) +
        geom_node_point(
            aes(size = size),
            color = vertex_color,
            alpha = 0.85,
            show.legend = FALSE
        ) +
        scale_size(range = c(vertex_size, vertex_size * 3)) +
        geom_node_text(
            aes(label = name),
            repel = TRUE,
            size = 3.5,
            color = "#1F2937",
            fontface = "bold",
            max.overlaps = 50
        ) +
        labs(title = title) +
        theme_void() +
        theme(
            plot.title = element_text(hjust = 0.5, size = 14, face = "bold"),
            plot.background = element_rect(fill = "white", color = NA),
            panel.background = element_rect(fill = "white", color = NA),
            plot.margin = margin(20, 20, 20, 20)
        )

    # Save the plot
    message(paste("Saving to:", output_file))
    ggsave(
        output_file,
        plot = p,
        width = width / 100,
        height = height / 100,
        dpi = 150,
        bg = "white"
    )

    message("Done!")
    invisible(p)
}

# ==============================================================================
# CLI Entry Point
# ==============================================================================

args <- commandArgs(trailingOnly = TRUE)

if (length(args) >= 1) {
    params <- read_args(args[1])

    # Extract parameters with defaults
    edges_file <- params$edges_file
    output_file <- params$output_file

    if (is.null(edges_file) || is.null(output_file)) {
        stop("edges_file and output_file are required parameters")
    }

    create_bigram_network(
        edges_file = edges_file,
        output_file = output_file,
        width = if (is.null(params$width)) 1200 else params$width,
        height = if (is.null(params$height)) 900 else params$height,
        top_words = if (is.null(params$top_words)) 30 else params$top_words,
        min_freq = if (is.null(params$min_freq)) 0.5 else params$min_freq,
        edge_alpha = if (is.null(params$edge_alpha)) 0.5 else params$edge_alpha,
        edge_color = if (is.null(params$edge_color)) "#6B7280" else params$edge_color,
        vertex_color = if (is.null(params$vertex_color)) "#2563EB" else params$vertex_color,
        vertex_size = if (is.null(params$vertex_size)) 4 else params$vertex_size,
        title = if (is.null(params$title)) "Rede de Coocorrência por Bigramas" else params$title
    )
}
