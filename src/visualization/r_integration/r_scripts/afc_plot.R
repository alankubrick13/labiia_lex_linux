#!/usr/bin/env Rscript
# =============================================================================
# afc_plot.R - IDENTICAL to IRaMuTeQ's PlotAfc2dCoul (Rgraph.R lines 46-128)
# =============================================================================

# Get script directory and source utils
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

# Load wordcloud for stopoverlap
suppressPackageStartupMessages({
    library(wordcloud)
})

safe_class_palette <- function(n) {
    iramuteq.colors(n)
}

# Shared helpers are provided by utils.R (norm.vec, is.yellow, del.yellow, select.chi.classe)

# =============================================================================
# EXACT IRaMuTeQ overlap function using wordcloud C implementation
# (Rgraph.R lines 155-191)
# =============================================================================
.overlap <- function(x11, y11, sw11, sh11, boxes1) {
    if (as.character(packageVersion("wordcloud")) >= "2.6") {
        .Call("_wordcloud_is_overlap", x11, y11, sw11, sh11, boxes1)
    } else {
        .Call("is_overlap", x11, y11, sw11, sh11, boxes1)
    }
}

overlap <- function(x1, y1, sw1, sh1, boxes) {
    use.r.layout <- FALSE
    if (!use.r.layout) {
        return(.overlap(x1, y1, sw1, sh1, boxes))
    }
    s <- 0
    if (length(boxes) == 0) {
        return(FALSE)
    }
    for (i in 1:length(boxes)) {
        bnds <- boxes[[i]]
        x2 <- bnds[1]
        y2 <- bnds[2]
        sw2 <- bnds[3]
        sh2 <- bnds[4]
        if (x1 < x2) {
            h_overlap <- x1 + sw1 > x2 - s
        } else {
            h_overlap <- x2 + sw2 > x1 - s
        }
        if (y1 < y2) {
            v_overlap <- h_overlap && (y1 + sh1 > y2 - s)
        } else {
            v_overlap <- h_overlap && (y2 + sh2 > y1 - s)
        }
        if (v_overlap) {
            return(TRUE)
        }
    }
    FALSE
}

# =============================================================================
# EXACT IRaMuTeQ stopoverlap function (Rgraph.R lines 193-248)
# =============================================================================
stopoverlap <- function(x, cex.par = NULL, xlim = NULL, ylim = NULL) {
    tails <- "g|j|p|q|y"
    rot.per <- 0
    last <- 1
    thetaStep <- .1
    rStep <- .5
    toplot <- NULL
    notplot <- NULL

    plot(x[, 1], x[, 2], pch = "", xlim = xlim, ylim = ylim)

    words <- rownames(x)
    if (is.null(cex.par)) {
        size <- rep(0.9, nrow(x))
    } else {
        size <- cex.par
    }

    boxes <- list()
    for (i in 1:nrow(x)) {
        rotWord <- runif(1) < rot.per
        r <- 0
        theta <- runif(1, 0, 2 * pi)
        x1 <- x[i, 1]
        y1 <- x[i, 2]
        wid <- strwidth(words[i], cex = size[i])
        ht <- strheight(words[i], cex = size[i])
        isOverlaped <- TRUE
        while (isOverlaped) {
            if (!overlap(x1 - 0.5 * wid, y1 - 0.5 * ht, wid, ht, boxes)) {
                toplot <- rbind(toplot, c(x1, y1, size[i], i))
                boxes[[length(boxes) + 1]] <- c(x1 - 0.5 * wid, y1 - 0.5 * ht, wid, ht)
                isOverlaped <- FALSE
            } else {
                if (r > sqrt(.5)) {
                    notplot <- rbind(notplot, c(words[i], x[i, 1], x[i, 2], size[i], i))
                    isOverlaped <- FALSE
                }
                theta <- theta + thetaStep
                r <- r + rStep * thetaStep / (2 * pi)
                x1 <- x[i, 1] + r * cos(theta)
                y1 <- x[i, 2] + r * sin(theta)
            }
        }
    }
    nbnot <- nrow(notplot)
    if (!is.null(nbnot)) {
        message(paste(nbnot, "words not plotted"))
    }
    if (!is.null(toplot)) {
        row.names(toplot) <- words[toplot[, 4]]
    }
    return(list(toplot = toplot, notplot = notplot))
}

# =============================================================================
# EXACT IRaMuTeQ make_afc_graph function (Rgraph.R lines 604-644)
# =============================================================================
make_afc_graph <- function(toplot, classes, clnb, xlab, ylab,
                           cex.txt = NULL, leg = FALSE, cmd = FALSE,
                           black = FALSE, xminmax = NULL, yminmax = NULL,
                           color = NULL, show_class_labels = FALSE,
                           publication_mode = FALSE, col_coords = NULL) {
    if (isTRUE(publication_mode)) {
        pub_palette <- c("#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
                         "#56B4E9", "#F0E442", "#000000", "#999999", "#44AA99")
        rain <- rep(pub_palette, length.out = clnb)
    } else {
        rain <- safe_class_palette(clnb)
    }
    cl.color <- rain[classes]
    if (black) {
        cl.color <- "black"
    }
    if (!is.null(color)) {
        cl.color <- color
    }

    plot(toplot[, 1], toplot[, 2],
        pch = "",
        xlab = xlab, ylab = ylab,
        xlim = xminmax, ylim = yminmax
    )

    if (isTRUE(publication_mode)) {
        abline(h = 0, col = "#D9D9D9", lwd = 0.8)
        abline(v = 0, col = "#D9D9D9", lwd = 0.8)
    } else {
        abline(h = 0, v = 0, lty = "dashed")
    }

    if (is.null(cex.txt)) {
        text(toplot[, 1], toplot[, 2], rownames(toplot), col = cl.color, offset = 0)
    } else {
        text(toplot[, 1], toplot[, 2], rownames(toplot), col = cl.color, cex = cex.txt, offset = 0)
    }

    # Add class labels in corners (like IRaMuTeQ)
    if (show_class_labels && clnb > 1) {
        # Class color names in Portuguese
        color_names <- c(
            "vermelho", "cinza", "verde", "azul claro", "azul escuro",
            "roxo", "laranja", "rosa", "marrom", "ciano"
        )

        # Position labels in different corners/edges
        x_range <- diff(xminmax)
        y_range <- diff(yminmax)

        # Corner positions for up to 6 classes
        corner_pos <- list(
            c(xminmax[2] - x_range * 0.15, yminmax[1] + y_range * 0.08), # bottom-right
            c(xminmax[2] - x_range * 0.15, yminmax[1] + y_range * 0.55), # middle-right
            c(xminmax[1] + x_range * 0.05, yminmax[2] - y_range * 0.15), # top-left
            c(xminmax[2] - x_range * 0.15, yminmax[2] - y_range * 0.15), # top-right
            c(xminmax[1] + x_range * 0.05, yminmax[1] + y_range * 0.15), # bottom-left
            c(xminmax[1] + x_range * 0.05, yminmax[1] + y_range * 0.55) # middle-left
        )

        for (i in 1:min(clnb, length(corner_pos))) {
            col_name <- ifelse(i <= length(color_names), color_names[i], paste("cor", i))
            label <- paste0("Classe ", i, "\n(", col_name, ")")
            pos <- corner_pos[[i]]
            text(pos[1], pos[2], label, col = rain[i], cex = 0.82, font = 2, adj = c(0.5, 0.5))
        }
    }

    # Centroids disabled — user wants terms only, no class labels in AFC

    if (!cmd) {
        dev.off()
    }
}

export_afc_gexf <- function(coords, labels, classes, gexf_output) {
    if (is.null(gexf_output) || !nzchar(gexf_output)) {
        return(invisible(FALSE))
    }
    if (!requireNamespace("rgexf", quietly = TRUE)) {
        message("rgexf not installed, skipping AFC GEXF export")
        return(invisible(FALSE))
    }
    if (is.null(coords) || nrow(coords) == 0) {
        return(invisible(FALSE))
    }

    labels <- as.character(labels)
    classes <- as.integer(classes)
    classes[!is.finite(classes)] <- 1L

    n_words <- nrow(coords)
    class_ids <- sort(unique(classes))
    class_ids <- class_ids[class_ids > 0]
    if (length(class_ids) == 0) {
        class_ids <- 1L
    }

    class_centers <- matrix(0, nrow = length(class_ids), ncol = 2)
    for (idx in seq_along(class_ids)) {
        cid <- class_ids[idx]
        sel <- which(classes == cid)
        if (length(sel) > 0) {
            class_centers[idx, ] <- colMeans(coords[sel, , drop = FALSE], na.rm = TRUE)
        }
    }

    class_labels <- paste0("Classe ", class_ids)
    all_labels <- c(labels, class_labels)
    node_ids <- as.character(seq_along(all_labels))
    nodes <- data.frame(
        id = node_ids,
        label = all_labels,
        stringsAsFactors = FALSE
    )

    edges <- data.frame(source = character(0), target = character(0), weight = numeric(0))
    for (i in seq_len(n_words)) {
        cid <- classes[i]
        class_idx <- match(cid, class_ids)
        if (is.na(class_idx)) {
            next
        }
        source <- as.character(i)
        target <- as.character(n_words + class_idx)
        edges <- rbind(edges, data.frame(source = source, target = target, weight = 1))
    }

    g <- rgexf::gexf(
        nodes = nodes,
        edges = edges[, c("source", "target"), drop = FALSE],
        edgesWeight = as.numeric(edges$weight)
    )
    rgexf::write.gexf(g, output = gexf_output)
    invisible(TRUE)
}

# =============================================================================
# EXACT IRaMuTeQ PlotAfc2dCoul function (Rgraph.R lines 46-128)
# =============================================================================
create_afc_plot <- function(coords_file, chi2_file = NULL, output_file,
                            width = 900, height = 900, dpi = 180, axes = c(1, 2),
                            max_words = 120, nbbycl = 80, inertia = NULL, PARCEX = 1,
                            debsup = NULL, what = "coord", col = FALSE,
                            col_coords_file = NULL, gexf_output = NULL,
                            show_class_labels = FALSE,
                            adaptive_label_scaling = FALSE,
                            min_visible_words = 60,
                            publication_mode = FALSE) {
    message("Loading AFC coordinates...")

    # Publication mode overrides (size only; nbbycl comes from caller)
    if (isTRUE(publication_mode)) {
        width <- 1600
        height <- 1400
        dpi <- 180
    }

    coords_target <- coords_file
    if (isTRUE(col) && !is.null(col_coords_file) && file.exists(col_coords_file)) {
        coords_target <- col_coords_file
    }
    coords <- read.csv(coords_target, row.names = 1, stringsAsFactors = FALSE)

    if (nrow(coords) == 0) {
        stop("No coordinates data")
    }

    x <- axes[1]
    y <- axes[2]
    if (max(x, y) > ncol(coords)) {
        stop("Selected AFC axes are out of bounds for coordinates file")
    }

    # Get coordinates for selected axes
    rowcoord <- as.matrix(coords[, c(x, y), drop = FALSE])
    rownames(rowcoord) <- rownames(coords)

    what_mode <- tolower(as.character(what)[1])
    if (!(what_mode %in% c("coord", "crl"))) {
        what_mode <- "coord"
    }
    if (what_mode == "crl") {
        row_norm <- sqrt(rowSums(rowcoord^2))
        row_norm[!is.finite(row_norm) | row_norm == 0] <- 1
        rowcoord <- rowcoord / row_norm
    }

    # Load chi-square table for class coloring
    if (!isTRUE(col) && !is.null(chi2_file) && file.exists(chi2_file)) {
        chitable <- as.matrix(read.csv(chi2_file, row.names = 1, stringsAsFactors = FALSE))
        if (nrow(chitable) == 0 || ncol(chitable) == 0) {
            stop("Invalid chi-square table")
        }
        common_words <- intersect(rownames(rowcoord), rownames(chitable))
        if (length(common_words) > 0) {
            rowcoord <- rowcoord[common_words, , drop = FALSE]
            chitable <- chitable[common_words, , drop = FALSE]
        }
        clnb <- ncol(chitable)

        # Determine class (maximum chi-square)
        classes <- as.integer(apply(chitable, 1, which.max))

        cex.par <- norm.vec(apply(chitable, 1, max), 0.8, 3)

        # Select top words per class
        words_per_class <- as.integer(nbbycl)
        if (!is.finite(words_per_class) || words_per_class <= 0) {
            words_per_class <- 80
        }
        row.keep <- select.chi.classe(chitable, words_per_class, active = TRUE, debsup = debsup)
        row.keep <- intersect(row.keep, 1:nrow(rowcoord))

        # Filter to selected words
        if (length(row.keep) > 0 && length(row.keep) < nrow(rowcoord)) {
            rowcoord <- rowcoord[row.keep, , drop = FALSE]
            classes <- classes[row.keep]
            cex.par <- cex.par[row.keep]
        }
    } else {
        if (isTRUE(col)) {
            clnb <- max(1, nrow(rowcoord))
            classes <- seq_len(nrow(rowcoord))
            cex.par <- rep(1.3, nrow(rowcoord))
        } else {
            clnb <- 1
            classes <- rep(1, nrow(rowcoord))
            cex.par <- rep(1.0, nrow(rowcoord))
        }
    }

    if (nrow(rowcoord) == 0) {
        stop("No AFC points available after filtering")
    }

    # Publication mode: compress font range for better word density
    if (isTRUE(publication_mode)) {
        always_keep_per_class <- 3
        # Recompute cex with narrower range — avoids giant words crowding out smaller ones
        if (!isTRUE(col) && length(cex.par) > 1) {
            chi_max_vals <- apply(chitable[rownames(rowcoord), , drop = FALSE], 1, max)
            cex.par <- norm.vec(chi_max_vals, 0.65, 2.0)
        }
    }

    # Load col_coords for publication centroids
    pub_col_coords <- NULL
    if (isTRUE(publication_mode) && !is.null(col_coords_file) && file.exists(col_coords_file)) {
        col_coords_raw <- read.csv(col_coords_file, row.names = 1, stringsAsFactors = FALSE)
        if (nrow(col_coords_raw) > 0 && ncol(col_coords_raw) >= max(axes[1], axes[2])) {
            pub_col_coords <- as.matrix(col_coords_raw[, c(axes[1], axes[2]), drop = FALSE])
        }
    }

    # Calculate axis limits with margin
    table.in <- rowcoord
    margin_fac <- max(cex.par) / 10
    # Publication: extra padding (15%) so edge words aren't clipped
    if (isTRUE(publication_mode)) margin_fac <- max(margin_fac, 0.15)
    xminmax <- c(
        min(table.in[, 1], na.rm = TRUE) * (1 + margin_fac) - 0.5,
        max(table.in[, 1], na.rm = TRUE) * (1 + margin_fac) + 0.5
    )
    xmin <- xminmax[1]
    xmax <- xminmax[2]

    yminmax <- c(
        min(table.in[, 2], na.rm = TRUE) * (1 + margin_fac) - 0.5,
        max(table.in[, 2], na.rm = TRUE) * (1 + margin_fac) + 0.5
    )
    ymin <- yminmax[1]
    ymax <- yminmax[2]
    # Guard against degenerate Y range (e.g., 1D AFC with 2 classes)
    if (!is.finite(ymin) || !is.finite(ymax) || abs(ymax - ymin) < 1e-10) {
        x_span <- abs(xmax - xmin)
        if (!is.finite(x_span) || x_span < 1e-10) x_span <- 1.0
        y_pad <- x_span * 0.5
        ymin <- -y_pad
        ymax <- y_pad
        yminmax <- c(ymin, ymax)
    }

    # Axis labels with inertia (EXACT IRaMuTeQ format)
    if (!is.null(inertia) && length(inertia) >= max(x, y)) {
        pct_x <- round(inertia[x] * 100, 2)
        pct_y <- round(inertia[y] * 100, 2)
    } else {
        pct_x <- 0
        pct_y <- 0
    }
    xlab <- paste("fator ", x, " - ", pct_x, " %", sep = "")
    ylab <- paste("fator ", y, " - ", pct_y, " %", sep = "")

    # Open output device
    # Open output device
    is_svg <- grepl("\\.svg$", output_file, ignore.case = TRUE)
    open_file_graph(output_file, width = width, height = height, svg = is_svg, dpi = dpi)
    par(cex = PARCEX)

    # Preserve base arrays for adaptive re-runs.
    rowcoord.base <- rowcoord
    classes.base <- as.integer(classes)
    cex.base <- cex.par

    # Sort by cex (largest first for stopoverlap priority)
    ord <- order(cex.par, decreasing = TRUE)
    table.in <- rowcoord[ord, , drop = FALSE]
    classes <- as.integer(classes[ord])
    cex.par <- cex.par[ord]

    # Apply stopoverlap algorithm (EXACT IRaMuTeQ method)
    table.out <- stopoverlap(table.in,
        cex.par = cex.par,
        xlim = c(xmin, xmax), ylim = c(ymin, ymax)
    )

    toplot <- table.out$toplot
    notplot <- table.out$notplot

    # Optional readability pass: if too many labels were discarded,
    # rerun stopoverlap with a softer font range to keep more words visible.
    if (isTRUE(adaptive_label_scaling) && !isTRUE(col) && nrow(rowcoord) > 0) {
        n_visible <- if (!is.null(toplot)) nrow(toplot) else 0
        target_visible <- min(as.integer(min_visible_words), nrow(rowcoord))
        if (!is.finite(target_visible) || target_visible < 1) {
            target_visible <- min(60L, nrow(rowcoord))
        }
        if (n_visible < target_visible) {
            ranges <- list(
                c(0.68, 2.00),
                c(0.55, 1.65),
                c(0.45, 1.35)
            )
            best_visible <- n_visible
            best_table_in <- table.in
            best_classes <- classes
            best_cex <- cex.par
            best_out <- table.out

            for (r in ranges) {
                cex_try_base <- norm.vec(cex.base, r[1], r[2])
                ord_try <- order(cex_try_base, decreasing = TRUE)
                table_try <- rowcoord.base[ord_try, , drop = FALSE]
                classes_try <- as.integer(classes.base[ord_try])
                cex_try <- cex_try_base[ord_try]
                out_try <- stopoverlap(
                    table_try,
                    cex.par = cex_try,
                    xlim = c(xmin, xmax), ylim = c(ymin, ymax)
                )
                visible_try <- if (!is.null(out_try$toplot)) nrow(out_try$toplot) else 0
                if (visible_try > best_visible) {
                    best_visible <- visible_try
                    best_table_in <- table_try
                    best_classes <- classes_try
                    best_cex <- cex_try
                    best_out <- out_try
                }
                if (visible_try >= target_visible) {
                    break
                }
            }

            if (best_visible > n_visible) {
                message(
                    paste(
                        "Adaptive AFC labels:",
                        n_visible, "->", best_visible,
                        "palavras visiveis"
                    )
                )
                table.in <- best_table_in
                classes <- best_classes
                cex.par <- best_cex
                table.out <- best_out
                toplot <- table.out$toplot
                notplot <- table.out$notplot
            }
        }
    }

    if (!is.null(notplot)) {
        message(paste(nrow(notplot), "words not plotted due to overlap"))
        notplot_df <- as.data.frame(notplot, stringsAsFactors = FALSE)
        if (ncol(notplot_df) >= 5) {
            colnames(notplot_df)[1:5] <- c("word", "x", "y", "cex", "index")
        }
        write.csv(notplot_df, file = paste(output_file, "_notplotted.csv", sep = ""), row.names = FALSE)
    }

    # Get classes for placed words
    plot_coords <- NULL
    plot_labels <- character(0)
    plot_classes <- integer(0)
    if (!is.null(toplot) && nrow(toplot) > 0) {
        placed_indices <- as.integer(toplot[, 4])
        classes <- classes[placed_indices]
        cex.par <- cex.par[placed_indices]
        plot_coords <- as.matrix(toplot[, c(1, 2), drop = FALSE])
        plot_labels <- rownames(toplot)
        plot_classes <- as.integer(classes)

        # Generate plot using make_afc_graph (EXACT IRaMuTeQ)
        make_afc_graph(toplot, classes, clnb, xlab, ylab,
            cex.txt = toplot[, 3],
            xminmax = c(xmin, xmax),
            yminmax = c(ymin, ymax),
            show_class_labels = show_class_labels,
            publication_mode = publication_mode,
            col_coords = pub_col_coords
        )
    } else {
        # Fallback: plot all words without overlap prevention
        rain <- safe_class_palette(clnb)

        plot(rowcoord[, 1], rowcoord[, 2],
            pch = "",
            xlab = xlab, ylab = ylab,
            xlim = c(xmin, xmax), ylim = c(ymin, ymax)
        )
        abline(h = 0, v = 0, lty = "dashed")
        text(rowcoord[, 1], rowcoord[, 2], rownames(rowcoord),
            col = rain[classes], cex = cex.par, offset = 0
        )
        plot_coords <- as.matrix(rowcoord[, c(1, 2), drop = FALSE])
        plot_labels <- rownames(rowcoord)
        plot_classes <- as.integer(classes)
        dev.off()
    }

    export_afc_gexf(plot_coords, plot_labels, plot_classes, gexf_output)

    # Write publication metrics JSON
    if (isTRUE(publication_mode)) {
        visible_count <- if (!is.null(toplot)) nrow(toplot) else 0L
        total_count <- visible_count + (if (!is.null(notplot)) nrow(notplot) else 0L)
        hidden_count <- total_count - visible_count
        metrics <- list(
            visible_labels = visible_count,
            hidden_labels = hidden_count,
            overlap_ratio = if (total_count > 0) hidden_count / total_count else 0,
            target_overlap_ratio = 0.12,
            total_terms_selected = total_count,
            class_count = clnb
        )
        metrics_file <- sub("\\.[^.]+$", "_metrics.json", output_file)
        if (requireNamespace("jsonlite", quietly = TRUE)) {
            jsonlite::write_json(metrics, metrics_file, auto_unbox = TRUE)
            message(paste("Publication metrics saved to:", metrics_file))
        } else {
            # Fallback: write JSON manually
            json_str <- paste0(
                '{"visible_labels":', metrics$visible_labels,
                ',"hidden_labels":', metrics$hidden_labels,
                ',"overlap_ratio":', round(metrics$overlap_ratio, 4),
                ',"target_overlap_ratio":', metrics$target_overlap_ratio,
                ',"total_terms_selected":', metrics$total_terms_selected,
                ',"class_count":', metrics$class_count, '}'
            )
            writeLines(json_str, metrics_file)
            message(paste("Publication metrics saved to:", metrics_file, "(fallback)"))
        }
    }

    message(paste("AFC plot saved to:", output_file))
}

# =============================================================================
# CLI Interface
# =============================================================================
args <- commandArgs(trailingOnly = TRUE)

if (length(args) >= 1) {
    args_file <- args[1]
    params <- read_args(args_file)

    width <- ifelse(is.null(params$width), 900, params$width)
    height <- ifelse(is.null(params$height), 900, params$height)
    dpi <- ifelse(is.null(params$dpi), 180, params$dpi)
    axes <- if (is.null(params$axes)) c(1, 2) else params$axes
    max_words <- ifelse(is.null(params$max_words), 120, params$max_words)
    nbbycl <- ifelse(
        is.null(params$nbbycl),
        ifelse(is.null(params$nb_per_class), 80, params$nb_per_class),
        params$nbbycl
    )
    debsup <- if (is.null(params$debsup)) NULL else params$debsup
    col_coords_file <- if (is.null(params$col_coords_file)) NULL else params$col_coords_file
    gexf_output <- if (is.null(params$gexf_output)) NULL else params$gexf_output
    show_class_labels <- if (is.null(params$show_class_labels)) FALSE else params$show_class_labels
    adaptive_label_scaling <- if (is.null(params$adaptive_label_scaling)) FALSE else params$adaptive_label_scaling
    min_visible_words <- if (is.null(params$min_visible_words)) 60 else params$min_visible_words
    publication_mode <- if (is.null(params$publication_mode)) FALSE else params$publication_mode

    create_afc_plot(
        coords_file = params$coords_file,
        chi2_file = params$chi2_file,
        output_file = params$output_file,
        width = width,
        height = height,
        dpi = dpi,
        axes = axes,
        max_words = max_words,
        nbbycl = nbbycl,
        inertia = params$inertia,
        PARCEX = ifelse(is.null(params$PARCEX), 1, params$PARCEX),
        debsup = debsup,
        what = ifelse(is.null(params$what), "coord", params$what),
        col = ifelse(is.null(params$col), FALSE, params$col),
        col_coords_file = col_coords_file,
        gexf_output = gexf_output,
        show_class_labels = show_class_labels,
        adaptive_label_scaling = adaptive_label_scaling,
        min_visible_words = min_visible_words,
        publication_mode = publication_mode
    )

    if (!file.exists(params$output_file)) {
        stop(paste("AFC plot output not generated:", params$output_file))
    }
    out_info <- file.info(params$output_file)
    if (is.na(out_info$size) || out_info$size <= 0) {
        stop(paste("AFC plot output is empty:", params$output_file))
    }
} else {
    message("Usage: Rscript afc_plot.R <args.json>")
}
