#!/usr/bin/env Rscript
# =============================================================================
# specificities.R - IRaMuTeQ-like specificities plot (plot.spec)
# =============================================================================

get_script_dir <- function() {
    args <- commandArgs(trailingOnly = FALSE)
    file_arg <- grep("^--file=", args, value = TRUE)
    if (length(file_arg) > 0) {
        return(dirname(normalizePath(sub("^--file=", "", file_arg))))
    }
    return(".")
}
script_dir <- get_script_dir()
source(file.path(script_dir, "utils.R"))

pick_score_column <- function(df) {
    candidates <- c("specificity", "chi2", "score", "value")
    for (name in candidates) {
        if (name %in% colnames(df)) {
            return(name)
        }
    }
    NULL
}

create_specificities_plot <- function(spec_file, output_file,
                                      width = 1200, height = 800,
                                      top_n = 30, bw = FALSE) {
    if (!file.exists(spec_file)) {
        stop("Specificities file not found")
    }

    spec_df <- read.csv(spec_file, stringsAsFactors = FALSE)
    if (!all(c("class_id", "word") %in% colnames(spec_df))) {
        stop("Specificities file must include class_id and word columns")
    }

    score_col <- pick_score_column(spec_df)
    if (is.null(score_col)) {
        stop("Specificities file must include one score column: specificity/chi2/score/value")
    }

    class_ids <- sort(unique(as.integer(spec_df$class_id)))
    class_ids <- class_ids[is.finite(class_ids)]
    if (length(class_ids) == 0) {
        stop("No classes found in specificities data")
    }

    if (bw) {
        class_cols <- rep("black", length(class_ids))
    } else {
        class_cols <- ifelse(seq_along(class_ids) %% 2 == 1, "blue", "red")
    }

    is_svg <- grepl("\\.svg$", output_file, ignore.case = TRUE)
    open_file_graph(output_file, width = width, height = height, svg = is_svg)
    par(bg = "white")

    layout(matrix(seq_along(class_ids), nrow = 1))

    for (idx in seq_along(class_ids)) {
        cid <- class_ids[idx]
        part <- spec_df[as.integer(spec_df$class_id) == cid, , drop = FALSE]
        part <- part[order(part[[score_col]], decreasing = TRUE), , drop = FALSE]
        if (nrow(part) > top_n) {
            part <- part[1:top_n, , drop = FALSE]
        }

        par(mar = c(1, 1, 2, 1), bg = "white")
        plot(0, 0, pch = "", axes = FALSE, xlab = "", ylab = "", xlim = c(-1, 1), ylim = c(-1, 1))
        text(-0.9, -0.5, paste("classe", cid), cex = 1, adj = 0, srt = 90, col = "black")

        if (nrow(part) > 0) {
            scores <- as.numeric(part[[score_col]])
            scores[!is.finite(scores)] <- 0
            cex_vals <- norm.vec(scores, 2, 3)
            y <- 0.92
            for (j in seq_len(nrow(part))) {
                word <- as.character(part$word[j])
                cex <- cex_vals[j]
                y <- y - (strheight(word, cex = cex) + 0.02)
                if (y < -0.95) {
                    break
                }
                text(-0.65, y, word, adj = c(0, 0), cex = cex, col = class_cols[idx], font = 1)
            }
        }
    }

    dev.off()
    message(paste("Specificities plot saved to:", output_file))
}

args <- commandArgs(trailingOnly = TRUE)
if (length(args) >= 1) {
    params <- read_args(args[1])
    create_specificities_plot(
        spec_file = params$spec_file,
        output_file = params$output_file,
        width = ifelse(is.null(params$width), 1200, params$width),
        height = ifelse(is.null(params$height), 800, params$height),
        top_n = ifelse(is.null(params$top_n), 30, params$top_n),
        bw = ifelse(is.null(params$bw), FALSE, params$bw)
    )
}
