#!/usr/bin/env Rscript
# =============================================================================
# dendrogram.R - IRaMuTeQ style dendrogram variants
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

suppressPackageStartupMessages({
    library(ape)
    library(wordcloud)
})

safe_class_ids <- function(tree, class_ids) {
    valid_ids <- suppressWarnings(as.integer(class_ids))
    valid_ids <- sort(unique(valid_ids[is.finite(valid_ids) & valid_ids > 0]))
    n_tips <- max(1, length(tree$tip.label))
    if (length(valid_ids) == 0) {
        valid_ids <- seq_len(n_tips)
    }

    ids <- suppressWarnings(as.integer(tree$tip.label))
    if (length(ids) == n_tips && all(!is.na(ids)) && all(ids %in% valid_ids)) {
        return(ids)
    }
    if (length(valid_ids) >= n_tips) {
        return(valid_ids[seq_len(n_tips)])
    }
    rep(valid_ids, length.out = n_tips)
}

resolve_tip_labels <- function(tree.order, class_ids, lab = NULL) {
    class_ids <- suppressWarnings(as.integer(class_ids))
    class_ids <- class_ids[is.finite(class_ids) & class_ids > 0]
    class_ids <- sort(unique(class_ids))
    default_by_id <- setNames(
        paste("classe", class_ids),
        as.character(class_ids)
    )
    if (is.null(lab)) {
        label_by_id <- default_by_id
    } else if (length(lab) == length(tree.order)) {
        return(as.character(lab))
    } else if (length(lab) == length(class_ids)) {
        label_by_id <- setNames(as.character(lab), as.character(class_ids))
    } else {
        label_by_id <- default_by_id
    }

    out <- character(length(tree.order))
    for (idx in seq_along(tree.order)) {
        cid <- suppressWarnings(as.integer(tree.order[idx]))
        key <- as.character(cid)
        if (is.na(cid) || !(key %in% names(label_by_id))) {
            out[idx] <- paste("classe", tree.order[idx])
        } else {
            out[idx] <- as.character(label_by_id[[key]])
        }
    }
    out
}

build_word_lists <- function(words_file, class_ids, nbbycl) {
    class_ids <- suppressWarnings(as.integer(class_ids))
    class_ids <- class_ids[is.finite(class_ids) & class_ids > 0]
    class_ids <- sort(unique(class_ids))
    lclasses <- vector("list", length(class_ids))
    names(lclasses) <- as.character(class_ids)
    for (key in names(lclasses)) {
        lclasses[[key]] <- numeric(0)
    }
    if (is.null(words_file) || !file.exists(words_file)) {
        return(lclasses)
    }

    words_df <- read.csv(words_file, stringsAsFactors = FALSE)
    if (!all(c("class_id", "word", "chi2") %in% colnames(words_df))) {
        return(lclasses)
    }

    for (classe in class_ids) {
        class_words <- words_df[words_df$class_id == classe, , drop = FALSE]
        class_words <- class_words[order(class_words$chi2, decreasing = TRUE), , drop = FALSE]
        pos_words <- class_words[class_words$chi2 > 0, , drop = FALSE]
        if (nrow(pos_words) == 0) {
            # Fallback for classes with no positive chi2 (e.g., dominant catch-all)
            # Use absolute chi2 to show most associated words
            class_words$chi2 <- abs(class_words$chi2)
            class_words <- class_words[class_words$chi2 > 0, , drop = FALSE]
            class_words <- class_words[order(class_words$chi2, decreasing = TRUE), , drop = FALSE]
        } else {
            class_words <- pos_words
        }
        if (nrow(class_words) > nbbycl) {
            class_words <- class_words[1:nbbycl, , drop = FALSE]
        }
        ntoplot <- round(class_words$chi2, 0)
        names(ntoplot) <- class_words$word
        lclasses[[as.character(classe)]] <- ntoplot
    }
    lclasses
}

make_palette <- function(class_ids, tree.order, bw = FALSE, publication_mode = FALSE) {
    class_ids <- suppressWarnings(as.integer(class_ids))
    class_ids <- class_ids[is.finite(class_ids) & class_ids > 0]
    class_ids <- sort(unique(class_ids))
    n_classes <- length(class_ids)
    if (n_classes == 0) {
        class_ids <- 1
        n_classes <- 1
    }

    safe_palette <- c(
        "#B22222", "#1E3A8A", "#0B6E4F", "#6A1B9A", "#8B5A00",
        "#005F73", "#7A0019", "#3D348B", "#2A9D8F", "#4A4A4A"
    )
    pub_palette <- c(
        "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
        "#56B4E9", "#F0E442", "#000000", "#999999", "#44AA99"
    )

    if (publication_mode) {
        safe_palette <- pub_palette
    }

    if (bw) {
        base_col <- setNames(rep("black", n_classes), as.character(class_ids))
        bar_col <- setNames(rep("grey55", n_classes), as.character(class_ids))
        cloud_col <- setNames(rep("grey35", n_classes), as.character(class_ids))
    } else {
        raw_cols <- rep(safe_palette, length.out = n_classes)
        base_col <- setNames(raw_cols, as.character(class_ids))
        bar_col <- base_col
        cloud_col <- base_col
    }

    tree_col <- rep(base_col[1], length(tree.order))
    for (idx in seq_along(tree.order)) {
        cid <- suppressWarnings(as.integer(tree.order[idx]))
        key <- as.character(cid)
        if (!is.na(cid) && key %in% names(base_col)) {
            tree_col[idx] <- base_col[[key]]
        }
    }
    list(tree = tree_col, base = base_col, bars = bar_col, cloud = cloud_col)
}

contrast_text_color <- function(color_hex) {
    rgb <- col2rgb(color_hex)
    r <- rgb[1, 1]; g <- rgb[2, 1]; b <- rgb[3, 1]
    srgb_to_linear <- function(c) {
        c <- c / 255
        ifelse(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ^ 2.4)
    }
    L <- 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)
    contrast_white <- (1.05) / (L + 0.05)
    contrast_black <- (L + 0.05) / 0.05
    if (contrast_black >= 4.5) return("black")
    return("white")
}

plot_profile_dendrogram <- function(tree, tree.order, tip_labels, sum.cl, lclasses,
                                    col.tree, colcloud, type.dendro,
                                    direction = "downwards") {
    vec.mat <- matrix(1, nrow = 3, ncol = length(tree.order))
    vec.mat[2, ] <- 2
    vec.mat[3, ] <- 3:(length(tree.order) + 2)
    layout(matrix(vec.mat, nrow = 3, ncol = length(tree.order)), heights = c(2, 1, 6))

    # Tree
    par(mar = c(0, 1, 1, 1), bg = "white")
    tree_dir <- if (direction %in% c("downwards", "upwards")) direction else "downwards"
    # Both cladogram and phylogram render as "phylogram" for rectangular H+V lines.
    # Cladogram: use.edge.length=FALSE (equal spacing — no missing branches from 0-length tips)
    # Phylogram: use.edge.length=TRUE (proportional to distance)
    requested_type <- as.character(type.dendro)[1]
    use_edge_length <- (requested_type == "phylogram" && length(tree$tip.label) > 2)
    plot.phylo(
        tree,
        type = "phylogram",
        direction = tree_dir,
        edge.width = 1.8,
        edge.color = "#202020",
        node.pos = 1,
        use.edge.length = use_edge_length,
        show.tip.label = FALSE
    )

    # Class labels + percentage bars
    # xlim matches plot.phylo tip positions (1, 2, ..., n)
    par(mar = c(0, 0, 0, 0), bg = "white")
    n_tips <- length(tree.order)
    bar_height <- 16
    plot(
        0, 0, type = "n",
        xlim = c(0.5, n_tips + 0.5),
        ylim = c(-bar_height - 3, 9),
        axes = FALSE, xlab = "", ylab = ""
    )

    bar_width <- 0.82
    for (idx in seq_along(tree.order)) {
        x_center <- idx  # matches plot.phylo tip positions
        cid <- suppressWarnings(as.integer(tree.order[idx]))
        pct <- if (!is.na(cid) && cid >= 1 && cid <= length(sum.cl)) sum.cl[cid] else 0
        text(x_center, 5.8, tip_labels[idx], col = col.tree[idx], font = 2, cex = 1.35)
        pct_col <- contrast_text_color(col.tree[idx])
        rect(
            x_center - bar_width / 2, 0,
            x_center + bar_width / 2, -bar_height,
            col = col.tree[idx], border = "#1F1F1F", lwd = 1.5
        )
        text(
            x_center, -bar_height / 2,
            paste0(round(pct, 1), "%"),
            cex = 1.2, col = pct_col, font = 2
        )
    }

    # Word columns
    for (cid in tree.order) {
        par(mar = c(0, 0, 1, 0), cex = 0.7, bg = "white")
        yval <- 1.1
        plot(0, 0, pch = "", axes = FALSE, xlim = c(-1, 1), ylim = c(-0.1, 1.2))

        class_id <- suppressWarnings(as.integer(cid))
        class_key <- as.character(class_id)
        words <- if (!is.na(class_id) && class_key %in% names(lclasses)) lclasses[[class_key]] else numeric(0)
        if (length(words) > 0) {
            vcex <- norm.vec(words, 1.6, 2.6)
            for (j in seq_along(words)) {
                word <- names(words)[j]
                word_cex <- vcex[j]
                yval <- yval - (strheight(word, cex = word_cex) + 0.02)
                if (yval > -0.1) {
                    cloud_col <- if (!is.na(class_id) && class_key %in% names(colcloud)) colcloud[[class_key]] else "black"
                    text(-0.9, yval, word, cex = word_cex, col = cloud_col, adj = 0, font = 1)
                }
            }
        }
    }
}

plot_cloud_dendrogram <- function(tree, tree.order, tip_labels, sum.cl, lclasses,
                                  col.tree, colcloud, type.dendro,
                                  direction = "rightwards") {
    n <- length(tree.order)
    mat <- cbind(rep(1, n), 2:(n + 1))
    layout(mat, widths = c(1.1, 2.2))

    tree_plot <- tree
    tree_plot$tip.label <- tip_labels
    par(mar = c(2, 1, 2, 1), bg = "white")
    tree_dir <- if (direction %in% c("rightwards", "leftwards", "downwards", "upwards")) direction else "rightwards"
    req_type <- as.character(type.dendro)[1]
    use_el <- (req_type == "phylogram" && length(tree_plot$tip.label) > 2)
    plot.phylo(
        tree_plot,
        type = "phylogram",
        direction = tree_dir,
        edge.width = 1.8,
        edge.color = "#202020",
        tip.color = col.tree,
        font = 2,
        cex = 1.2,
        use.edge.length = use_el,
        label.offset = 0.55
    )

    for (i in rev(tree.order)) {
        par(mar = c(0.5, 0.5, 0.5, 0.5), bg = "white")
        class_id <- suppressWarnings(as.integer(i))
        class_key <- as.character(class_id)
        words <- if (!is.na(class_id) && class_key %in% names(lclasses)) lclasses[[class_key]] else numeric(0)
        if (length(words) > 0) {
            wordcloud(
                words = names(words),
                freq = as.numeric(words),
                scale = c(2.5, 0.5),
                random.order = FALSE,
                colors = rep(ifelse(class_key %in% names(colcloud), colcloud[[class_key]], "black"), length(words))
            )
        } else {
            plot.new()
            text(0.5, 0.5, "sem termos", cex = 1)
        }
        pct <- if (!is.na(class_id) && class_id >= 1 && class_id <= length(sum.cl)) sum.cl[class_id] else 0
        lab_idx <- which(tree.order == i)[1]
        lbl <- if (!is.na(lab_idx)) tip_labels[lab_idx] else paste("classe", i)
        title(main = paste(lbl, "-", round(pct, 1), "%"), cex.main = 0.9)
    }
}

plot_side_dendrogram <- function(tree, tree.order, tip_labels, sum.cl, col.tree,
                                 mode = "pie", type.dendro = "cladogram",
                                 direction = "rightwards") {
    layout(matrix(c(1, 2), nrow = 1), widths = c(2.0, 1.4))

    tree_plot <- tree
    tree_plot$tip.label <- tip_labels
    par(mar = c(2, 1, 2, 1), bg = "white")
    tree_dir <- if (direction %in% c("rightwards", "leftwards", "downwards", "upwards")) direction else "rightwards"
    side_type <- "cladogram"
    plot.phylo(
        tree_plot,
        type = side_type,
        direction = tree_dir,
        edge.width = 1.8,
        edge.color = "#202020",
        tip.color = col.tree,
        font = 2,
        cex = 1.14,
        label.offset = 0.55
    )

    if (mode == "pie") {
        old_par <- par(no.readonly = TRUE)
        on.exit(par(old_par), add = TRUE)
        par(mfrow = c(length(tree.order), 1), mar = c(0.6, 0.8, 0.6, 0.8), bg = "white")
        for (i in rev(tree.order)) {
            cid <- suppressWarnings(as.integer(i))
            pct <- if (!is.na(cid) && cid >= 1 && cid <= length(sum.cl)) sum.cl[cid] else 0
            lab_idx <- which(tree.order == i)[1]
            tip_col <- if (!is.na(lab_idx) && lab_idx <= length(col.tree)) col.tree[lab_idx] else "grey"
            tip_lbl <- if (!is.na(lab_idx) && lab_idx <= length(tip_labels)) tip_labels[lab_idx] else paste("classe", i)
            pie(
                c(pct, 100 - pct),
                col = c(tip_col, "white"),
                radius = 1,
                labels = "",
                clockwise = TRUE,
                main = paste(tip_lbl, "-", round(pct, 1), "%"),
                cex.main = 0.9
            )
        }
    } else {
        par(mar = c(2, 1, 2, 1), bg = "white")
        to.plot <- as.numeric(sum.cl[as.integer(tree.order)])
        to.plot[!is.finite(to.plot)] <- 0
        x_max <- max(100, max(to.plot, na.rm = TRUE) * 1.08)
        bp <- barplot(
            to.plot,
            horiz = TRUE,
            col = col.tree,
            border = "#1F1F1F",
            lwd = 1.5,
            names.arg = "",
            axes = FALSE,
            xlim = c(0, x_max)
        )
        for (idx in seq_along(bp)) {
            pct <- to.plot[idx]
            txt_col <- contrast_text_color(col.tree[idx])
            text(
                x = max(2.5, pct / 2),
                y = bp[idx],
                labels = paste0(round(pct, 1), "%"),
                cex = 1.12,
                col = txt_col,
                font = 2
            )
        }
    }
}

create_dendrogram <- function(tree_file, classes_file, words_file = NULL,
                              output_file, width = 1400, height = 1200,
                              dpi = 220,
                              nbbycl = 60, type.dendro = "phylogram",
                              bw = FALSE, lab = NULL,
                              dendro_type = "profile",
                              direction = "downwards",
                              publication_mode = FALSE) {
    message("Loading tree...")
    tree_text <- readLines(tree_file, warn = FALSE)
    tree_text <- paste(tree_text, collapse = "")
    if (nchar(tree_text) < 3) {
        stop("Invalid tree file")
    }
    tree <- read.tree(text = tree_text)

    classes_df <- read.csv(classes_file, stringsAsFactors = FALSE)
    if (!("class_id" %in% colnames(classes_df))) {
        classes_df$class_id <- seq_len(nrow(classes_df))
    }
    classes_df$class_id <- suppressWarnings(as.integer(classes_df$class_id))
    classes_df$percentage <- suppressWarnings(as.numeric(classes_df$percentage))
    if ("n_segments" %in% colnames(classes_df)) {
        classes_df$n_segments <- suppressWarnings(as.integer(classes_df$n_segments))
    }
    classes_df <- classes_df[!is.na(classes_df$class_id) & classes_df$class_id > 0, , drop = FALSE]
    classes_df <- classes_df[!is.na(classes_df$percentage), , drop = FALSE]
    if ("n_segments" %in% colnames(classes_df)) {
        classes_df <- classes_df[is.na(classes_df$n_segments) | classes_df$n_segments > 0, , drop = FALSE]
    }
    classes_df <- classes_df[!duplicated(classes_df$class_id), , drop = FALSE]
    classes_df <- classes_df[order(classes_df$class_id), , drop = FALSE]
    num_classes <- nrow(classes_df)
    if (num_classes == 0) {
        stop("No classes data")
    }

    class_ids <- as.integer(classes_df$class_id)
    sum.cl <- classes_df$percentage
    names(sum.cl) <- as.character(class_ids)

    # Publication mode overrides
    total_terms_shown <- 0
    total_terms_clipped <- 0
    if (publication_mode) {
        n_cl <- length(class_ids)
        width <- max(2400, min(4200, 320 * n_cl))
        height <- max(1700, min(2800, 1100 + 120 * n_cl))
        dpi <- 240
        per_class_cap <- max(12, min(36, floor(120 / n_cl)))
        if (n_cl <= 3) per_class_cap <- 36
        if (n_cl >= 8) per_class_cap <- 12
        nbbycl <- per_class_cap
    }

    tree.order <- safe_class_ids(tree, class_ids)
    tip_labels <- resolve_tip_labels(tree.order, class_ids, lab = lab)
    palette <- make_palette(class_ids, tree.order, bw = bw, publication_mode = publication_mode)
    lclasses <- build_word_lists(words_file, class_ids, nbbycl)

    # Publication mode: filter and count terms
    if (publication_mode) {
        for (cname in names(lclasses)) {
            words <- lclasses[[cname]]
            if (length(words) > 0) {
                # Only chi2 > 0 (already filtered in build_word_lists)
                # Order: chi2 desc (already done), then clip
                n_before <- length(words)
                if (n_before > nbbycl) {
                    words <- words[1:nbbycl]
                }
                total_terms_shown <- total_terms_shown + length(words)
                total_terms_clipped <- total_terms_clipped + (n_before - length(words))
                lclasses[[cname]] <- words
            }
        }
    }

    is_svg <- grepl("\\.svg$", output_file, ignore.case = TRUE)
    open_file_graph(output_file, width = width, height = height, svg = is_svg, dpi = dpi)
    par(bg = "white")

    dt <- tolower(as.character(dendro_type)[1])
    if (!(dt %in% c("profile", "cloud", "pie", "barplot"))) {
        dt <- "profile"
    }
    direction <- tolower(as.character(direction)[1])
    if (dt == "profile" && !(direction %in% c("downwards", "upwards"))) {
        message("Warning: profile dendrogram only supports downwards/upwards direction. Forcing downwards.")
        direction <- "downwards"
    }

    if (dt == "cloud") {
        plot_cloud_dendrogram(
            tree = tree,
            tree.order = tree.order,
            tip_labels = tip_labels,
            sum.cl = sum.cl,
            lclasses = lclasses,
            col.tree = palette$tree,
            colcloud = palette$cloud,
            type.dendro = type.dendro,
            direction = direction
        )
    } else if (dt == "pie") {
        plot_side_dendrogram(
            tree = tree,
            tree.order = tree.order,
            tip_labels = tip_labels,
            sum.cl = sum.cl,
            col.tree = palette$tree,
            mode = "pie",
            type.dendro = type.dendro,
            direction = direction
        )
    } else if (dt == "barplot") {
        plot_side_dendrogram(
            tree = tree,
            tree.order = tree.order,
            tip_labels = tip_labels,
            sum.cl = sum.cl,
            col.tree = palette$tree,
            mode = "barplot",
            type.dendro = type.dendro,
            direction = direction
        )
    } else {
        plot_profile_dendrogram(
            tree = tree,
            tree.order = tree.order,
            tip_labels = tip_labels,
            sum.cl = sum.cl,
            lclasses = lclasses,
            col.tree = palette$tree,
            colcloud = palette$cloud,
            type.dendro = type.dendro,
            direction = direction
        )
    }

    dev.off()
    message(paste("Dendrogram saved to:", output_file))

    # Write metrics JSON when in publication mode
    if (publication_mode) {
        metrics_file <- sub("\\.[^.]+$", "_metrics.json", output_file)
        metrics <- list(
            terms_shown = total_terms_shown,
            terms_clipped = total_terms_clipped,
            n_classes = length(class_ids),
            variant = type.dendro
        )
        jsonlite::write_json(metrics, metrics_file, auto_unbox = TRUE)
        message(paste("Metrics saved to:", metrics_file))
    }
}

create_simple_dendrogram <- function(tree_file, classes_file, output_file,
                                     width = 800, height = 600,
        dpi = 220,
                                     type.dendro = "phylogram",
                                     bw = FALSE, lab = NULL,
                                     dendro_type = "barplot",
                                     direction = "rightwards",
                                     publication_mode = FALSE) {
    create_dendrogram(
        tree_file = tree_file,
        classes_file = classes_file,
        words_file = NULL,
        output_file = output_file,
        width = width,
        height = height,
        dpi = dpi,
        nbbycl = 60,
        type.dendro = type.dendro,
        bw = bw,
        lab = lab,
        dendro_type = dendro_type,
        direction = direction,
        publication_mode = publication_mode
    )
}

# =============================================================================
# CLI Interface
# =============================================================================
args <- commandArgs(trailingOnly = TRUE)

if (length(args) >= 1) {
    args_file <- args[1]
    params <- read_args(args_file)

    type.dendro <- if (is.null(params$type.dendro)) {
        if (is.null(params$type_dendro)) "phylogram" else params$type_dendro
    } else {
        params$type.dendro
    }
    dendro_type <- if (is.null(params$dendro_type)) {
        if (is.null(params$words_file)) "barplot" else "profile"
    } else {
        params$dendro_type
    }
    bw <- if (is.null(params$bw)) FALSE else params$bw
    direction <- if (is.null(params$direction)) "downwards" else params$direction
    words_file <- if (is.null(params$words_file)) NULL else params$words_file
    lab <- if (is.null(params$lab)) NULL else params$lab
    publication_mode <- if (is.null(params$publication_mode)) FALSE else as.logical(params$publication_mode)

    create_dendrogram(
        tree_file = params$tree_file,
        classes_file = params$classes_file,
        words_file = words_file,
        output_file = params$output_file,
        width = ifelse(is.null(params$width), 1400, params$width),
        height = ifelse(is.null(params$height), 1200, params$height),
        dpi = ifelse(is.null(params$dpi), 220, params$dpi),
        nbbycl = ifelse(is.null(params$nbbycl), 60, params$nbbycl),
        type.dendro = type.dendro,
        bw = bw,
        lab = lab,
        dendro_type = dendro_type,
        direction = direction,
        publication_mode = publication_mode
    )
} else {
    message("Usage: Rscript dendrogram.R <args.json>")
}
