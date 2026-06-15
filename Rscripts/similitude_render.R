#!/usr/bin/env Rscript
# =============================================================================
# similitude_render.R - IRaMuTeQ-style similarity graph renderer
#
# Adapted from IRaMuTeQ simi.R + TextAnalyzerPro similarity.R
# Uses igraph + sna for Fruchterman-Reingold layout with Cairo rendering.
#
# Input: JSON params file with matrix_file, freq_file, output_file, options
# Output: PNG via Cairo (publication quality)
# =============================================================================

suppressPackageStartupMessages({
    library(igraph)
    library(sna)
    library(intergraph)
    library(jsonlite)
})

# =============================================================================
# Helper functions (from IRaMuTeQ Rgraph.R)
# =============================================================================
norm.vec <- function(v, vmin, vmax) {
    vr <- range(v, na.rm = TRUE)
    if (vr[1] == vr[2]) {
        fac <- 1
    } else {
        fac <- (vmax - vmin) / (vr[2] - vr[1])
    }
    (v - vr[1]) * fac + vmin
}

is.yellow <- function(my.color) {
    if ((my.color[1] > 200) && (my.color[2] > 200) && (my.color[3] < 100)) {
        return(TRUE)
    }
    return(FALSE)
}

del.yellow <- function(colors) {
    if (length(colors) == 0) return(colors)
    rgbs <- col2rgb(colors)
    tochange <- apply(rgbs, 2, is.yellow)
    tochange <- which(tochange)
    if (length(tochange) > 0) {
        gr.col <- grey.colors(length(tochange), start = 0.5, end = 0.8)
        compt <- 1
        for (val in tochange) {
            colors[val] <- gr.col[compt]
            compt <- compt + 1
        }
    }
    colors
}

rotate_layout_pca <- function(lo) {
    if (is.null(lo) || nrow(lo) < 2) {
        return(lo)
    }
    centered <- scale(lo, center = TRUE, scale = FALSE)
    sv <- svd(centered)
    rotated <- centered %*% sv$v
    if (ncol(rotated) >= 2) {
        if (diff(range(rotated[, 1])) < diff(range(rotated[, 2]))) {
            rotated <- rotated[, c(2, 1), drop = FALSE]
        }
        if (sum(rotated[, 1]) < 0) {
            rotated[, 1] <- -rotated[, 1]
        }
    }
    rotated
}

choose_device_dimensions <- function(lo) {
    if (is.null(lo) || nrow(lo) == 0) {
        return(list(width = 1100L, height = 1100L))
    }
    xspan <- diff(range(lo[, 1]))
    yspan <- diff(range(lo[, 2]))
    if (is.na(yspan) || yspan <= 1e-9) {
        ratio <- Inf
    } else {
        ratio <- xspan / yspan
    }
    if (ratio > 1.25) {
        return(list(width = 1400L, height = 900L))
    }
    if (ratio < 0.8) {
        return(list(width = 900L, height = 1400L))
    }
    list(width = 1100L, height = 1100L)
}

build_layout_payload <- function(graph, txt.layout, mat.eff, label.cex, membership_vec, device) {
    nodes_payload <- lapply(seq_along(V(graph)$name), function(i) {
        term <- V(graph)$name[i]
        list(
            term = term,
            x = unname(txt.layout[i, 1]),
            y = unname(txt.layout[i, 2]),
            community = as.integer(membership_vec[i]),
            frequency = as.numeric(mat.eff[term]),
            label_cex = as.numeric(label.cex[i])
        )
    })
    edges_payload <- lapply(seq_len(ecount(graph)), function(i) {
        edge_ends <- ends(graph, E(graph)[i])
        list(
            source = edge_ends[1],
            target = edge_ends[2],
            weight = as.numeric(E(graph)$weight[i])
        )
    })
    list(
        nodes = nodes_payload,
        edges = edges_payload,
        layout_bounds = list(
            xmin = unname(min(txt.layout[, 1])),
            xmax = unname(max(txt.layout[, 1])),
            ymin = unname(min(txt.layout[, 2])),
            ymax = unname(max(txt.layout[, 2]))
        ),
        device = device
    )
}

# =============================================================================
# Main rendering function
# =============================================================================
render_similitude <- function(params) {
    # Extract parameters with defaults
    matrix_file <- params$matrix_file
    freq_file <- params$freq_file
    output_file <- params$output_file
    # Defaults aligned with IRaMuTeQ simitxt.cfg
    width <- ifelse(is.null(params$width), 1000, as.integer(params$width))
    height <- ifelse(is.null(params$height), 1000, as.integer(params$height))
    method <- ifelse(is.null(params$method), "cooc", params$method)
    max_tree <- ifelse(is.null(params$max_tree), TRUE, as.logical(params$max_tree))
    layout_type <- ifelse(is.null(params$layout_type), "frutch", params$layout_type)
    vcexmin <- ifelse(is.null(params$vcexmin), 1.0, as.numeric(params$vcexmin))
    vcexmax <- ifelse(is.null(params$vcexmax), 2.5, as.numeric(params$vcexmax))
    coeff_edge_min <- ifelse(is.null(params$coeff_edge_min), 0.6, as.numeric(params$coeff_edge_min))
    coeff_edge_max <- ifelse(is.null(params$coeff_edge_max), 4.0, as.numeric(params$coeff_edge_max))
    community_method <- ifelse(is.null(params$community_method), "edge_betweenness", params$community_method)
    halo <- ifelse(is.null(params$halo), TRUE, as.logical(params$halo))
    edge_curved <- ifelse(is.null(params$edge_curved), FALSE, as.logical(params$edge_curved))
    grayscale <- ifelse(is.null(params$grayscale), FALSE, as.logical(params$grayscale))
    show_edge_labels <- ifelse(is.null(params$show_edge_labels), FALSE, as.logical(params$show_edge_labels))
    dpi <- ifelse(is.null(params$dpi), 150, as.integer(params$dpi))
    alpha <- ifelse(is.null(params$alpha), 20, as.numeric(params$alpha))
    graph_word <- ifelse(is.null(params$graph_word), "", as.character(params$graph_word))
    layout_output_file <- ifelse(
        is.null(params$layout_output_file),
        "",
        as.character(params$layout_output_file)
    )
    community_sensitivity_file <- ifelse(
        is.null(params$community_sensitivity_file),
        "",
        as.character(params$community_sensitivity_file)
    )

    # 1. Load matrix
    message("Loading similarity matrix: ", matrix_file)
    mat.simi <- as.matrix(read.csv(matrix_file, row.names = 1, check.names = FALSE))
    v.label <- colnames(mat.simi)
    message("  Terms: ", length(v.label))

    # 2. Load frequencies
    if (!is.null(freq_file) && file.exists(freq_file)) {
        freq_df <- read.csv(freq_file, stringsAsFactors = FALSE)
        mat.eff <- freq_df$frequency
        names(mat.eff) <- freq_df$word
        mat.eff <- mat.eff[v.label]
        mat.eff[is.na(mat.eff)] <- 1
    } else {
        mat.eff <- rep(1, length(v.label))
        names(mat.eff) <- v.label
    }

    if (nzchar(graph_word) && graph_word %in% colnames(mat.simi)) {
        index <- which(colnames(mat.simi) == graph_word)[1]
        mat.simi <- graph.word(mat.simi, index)
        cs <- colSums(mat.simi)
        if (length(which(cs == 0))) {
            mat.simi <- mat.simi[, -which(cs == 0), drop = FALSE]
        }
        rs <- rowSums(mat.simi)
        if (length(which(rs == 0))) {
            mat.simi <- mat.simi[-which(rs == 0), , drop = FALSE]
        }
        v.label <- colnames(mat.simi)
        mat.eff <- mat.eff[v.label]
        mat.eff[is.na(mat.eff)] <- 1
        message("  Applied graph_word filter: ", graph_word, " -> ", length(v.label), " terms")
    }

    # 3. Build graph
    message("Creating graph...")
    g1 <- graph_from_adjacency_matrix(mat.simi, mode = "lower", weighted = TRUE, diag = FALSE)
    g.toplot <- g1

    # 4. Maximum spanning tree (exact IRaMuTeQ method)
    if (max_tree && ecount(g1) > 0) {
        weori <- E(g1)$weight
        if (method == "cooc") {
            invw <- ifelse(weori > 0, 1 / weori, .Machine$double.xmax)
        } else {
            invw <- 1 - weori
        }
        E(g1)$weight <- invw
        g.max <- mst(g1)
        # Restore original weights
        if (method == "cooc") {
            E(g.max)$weight <- 1 / E(g.max)$weight
        } else {
            E(g.max)$weight <- 1 - E(g.max)$weight
        }
        g.toplot <- g.max
        message("  MST: ", ecount(g1), " -> ", ecount(g.max), " edges")
    }

    if (vcount(g.toplot) == 0) {
        stop("Empty graph after MST")
    }

    # 5. Label sizes based on frequency
    label.cex <- norm.vec(mat.eff[V(g.toplot)$name], vcexmin, vcexmax)

    # 6. Edge widths
    if (ecount(g.toplot) > 0) {
        we.width <- norm.vec(abs(E(g.toplot)$weight), coeff_edge_min, coeff_edge_max)
    } else {
        we.width <- numeric(0)
    }

    # 7. Layout
    message("Calculating layout (", layout_type, ")...")
    if (layout_type == "frutch") {
        lo <- gplot.layout.fruchtermanreingold(asNetwork(g.toplot), list())
    } else if (layout_type == "kawa") {
        lo <- layout_with_kk(g.toplot, dim = 2)
    } else {
        lo <- layout_with_fr(g.toplot, niter = 1000)
    }
    # IRaMuTeQ does NOT rotate layout after Fruchterman-Reingold.
    # Removing PCA rotation to match IRaMuTeQ visual output.
    # lo <- rotate_layout_pca(lo)
    rownames(lo) <- V(g.toplot)$name
    device_dims <- choose_device_dimensions(lo)
    width <- device_dims$width
    height <- device_dims$height

    # 8. Community detection
    com <- NULL
    vertex.label.color <- rep("black", vcount(g.toplot))
    membership_vec <- rep(0L, vcount(g.toplot))

    message("Detecting communities (", community_method, ")...")
    com <- tryCatch({
        if (community_method == "edge_betweenness") {
            cluster_edge_betweenness(g.toplot)
        } else if (community_method == "fastgreedy") {
            cluster_fast_greedy(as.undirected(g.toplot))
        } else if (community_method == "walktrap") {
            cluster_walktrap(g.toplot)
        } else {
            cluster_louvain(as.undirected(g.toplot))
        }
    }, error = function(e) {
        message("  Community detection failed: ", e$message)
        NULL
    })

    halo.colors <- NULL
    halo.border <- NULL
    if (!is.null(com)) {
        n_comm <- max(membership(com))
        message("  Found ", n_comm, " communities")
        membership_vec <- as.integer(membership(com))
        # Halo transparency from alpha param (IRaMuTeQ default: 20 → 0.20)
        alpha_fill <- alpha / 100
        alpha_border <- min((alpha + 15) / 100, 1.0)
        if (grayscale) {
            rain <- grey.colors(n_comm, start = 0.4, end = 0.7)
            vertex.label.color <- rep("black", vcount(g.toplot))
            halo.colors <- adjustcolor(grey.colors(n_comm, start = 0.7, end = 0.9), alpha.f = alpha_fill)
            halo.border <- adjustcolor(grey.colors(n_comm, start = 0.5, end = 0.7), alpha.f = alpha_border)
        } else {
            rain <- rainbow(n_comm)
            rain <- del.yellow(rain)
            vertex.label.color <- rain[membership(com)]
            # Halo: same colors with transparency controlled by alpha param
            halo.colors <- adjustcolor(rain, alpha.f = alpha_fill)
            halo.border <- adjustcolor(rain, alpha.f = alpha_fill)  # IRaMuTeQ: same as fill
        }
    }

    if (nzchar(community_sensitivity_file) && ecount(g.toplot) > 0) {
        report <- tryCatch({
            build_community_sensitivity_report(g.toplot, community_method)
        }, error = function(e) {
            list(error = e$message)
        })
        write_json(report, community_sensitivity_file, auto_unbox = TRUE, pretty = TRUE)
    }

    # 9. Edge labels (weights on edges)
    edge.labels <- NULL
    if (show_edge_labels && ecount(g.toplot) > 0) {
        weights <- E(g.toplot)$weight
        if (method == "cooc") {
            edge.labels <- as.character(round(weights))
        } else {
            edge.labels <- formatC(weights, format = "f", digits = 2)
        }
    }

    # 10. Render
    message("Rendering to ", output_file, " (", width, "x", height, ")...")
    curved_val <- if (edge_curved) 0.3 else FALSE

    png(output_file, width = width, height = height, res = dpi, pointsize = 8, type = "cairo",
        antialias = "subpixel", bg = "white")
    par(mar = c(2, 2, 2, 2), bg = "white")

    # First pass: graph with edges + halos (no vertex labels)
    if (!is.null(com) && halo) {
        mark.groups <- communities(com)
        plot(com, g.toplot,
            vertex.label = "",
            edge.width = we.width,
            vertex.size = 0,
            vertex.color = "white",
            vertex.label.color = "white",
            edge.color = "gray50",
            vertex.label.cex = 0,
            layout = lo,
            mark.groups = mark.groups,
            edge.curved = curved_val,
            mark.col = halo.colors,
            mark.border = halo.border,
            edge.label = edge.labels,
            edge.label.cex = 0.7,
            edge.label.color = "gray20",
            edge.label.font = 2
        )
    } else {
        plot(g.toplot,
            vertex.label = "",
            edge.width = we.width,
            vertex.size = 0,
            vertex.color = "white",
            vertex.label.color = "white",
            edge.color = "gray50",
            vertex.label.cex = 0,
            layout = lo,
            edge.curved = curved_val,
            edge.label = edge.labels,
            edge.label.cex = 0.7,
            edge.label.color = "gray20",
            edge.label.font = 2
        )
    }

    # Second pass: text labels on top (exact IRaMuTeQ method)
    txt.layout <- layout.norm(lo, -1, 1, -1, 1)
    text(txt.layout[, 1], txt.layout[, 2], V(g.toplot)$name,
        cex = label.cex,
        col = vertex.label.color,
        font = 2
    )

    if (nzchar(layout_output_file)) {
        payload <- build_layout_payload(
            g.toplot,
            txt.layout,
            mat.eff,
            label.cex,
            membership_vec,
            list(
                width = as.integer(width),
                height = as.integer(height),
                dpi = as.integer(dpi),
                pointsize = 8,
                bg = "white"
            )
        )
        write_json(payload, layout_output_file, auto_unbox = TRUE, pretty = TRUE)
    }

    dev.off()
    message("Done: ", output_file)
}

run_community_method <- function(graph, community_method, weighted = TRUE) {
    if (community_method == "edge_betweenness") {
        if (weighted) {
            return(cluster_edge_betweenness(graph))
        }
        return(cluster_edge_betweenness(graph, weights = NA))
    }
    if (community_method == "fastgreedy") {
        if (weighted) {
            return(cluster_fast_greedy(as.undirected(graph)))
        }
        return(cluster_fast_greedy(as.undirected(graph), weights = NA))
    }
    if (community_method == "walktrap") {
        if (weighted) {
            return(cluster_walktrap(graph))
        }
        return(cluster_walktrap(graph, weights = NA))
    }
    if (community_method == "label_propagation") {
        return(cluster_label_prop(graph))
    }
    if (community_method == "leading_eigenvector") {
        if (weighted) {
            return(cluster_leading_eigen(as.undirected(graph)))
        }
        return(cluster_leading_eigen(as.undirected(graph), weights = NA))
    }
    if (community_method == "multilevel" || community_method == "louvain") {
        if (weighted) {
            return(cluster_louvain(as.undirected(graph)))
        }
        return(cluster_louvain(as.undirected(graph), weights = NA))
    }
    if (community_method == "optimal") {
        if (weighted) {
            return(cluster_optimal(as.undirected(graph)))
        }
        return(cluster_optimal(as.undirected(graph), weights = NA))
    }
    if (community_method == "spinglass") {
        if (weighted) {
            return(cluster_spinglass(as.undirected(graph)))
        }
        return(cluster_spinglass(as.undirected(graph), weights = NA))
    }
    cluster_edge_betweenness(graph)
}

membership_named_list <- function(community_obj) {
    membership_vec <- membership(community_obj)
    out <- as.list(as.integer(membership_vec))
    names(out) <- names(membership_vec)
    out
}

safe_compare_partition <- function(com_a, com_b, method) {
    tryCatch(
        as.numeric(compare(com_a, com_b, method = method)),
        error = function(e) NA_real_
    )
}

build_community_sensitivity_report <- function(graph, community_method) {
    display_com <- run_community_method(graph, community_method, weighted = TRUE)

    inverse_graph <- graph
    if (ecount(inverse_graph) > 0) {
        E(inverse_graph)$weight <- 1 / pmax(E(inverse_graph)$weight, 1e-10)
    }
    inverse_com <- run_community_method(inverse_graph, community_method, weighted = TRUE)
    unweighted_com <- run_community_method(graph, community_method, weighted = FALSE)

    list(
        method = community_method,
        node_count = vcount(graph),
        edge_count = ecount(graph),
        display_partition = membership_named_list(display_com),
        inverse_distance_partition = membership_named_list(inverse_com),
        unweighted_partition = membership_named_list(unweighted_com),
        comparisons = list(
            display_vs_inverse = list(
                vi = safe_compare_partition(display_com, inverse_com, "vi"),
                nmi = safe_compare_partition(display_com, inverse_com, "nmi"),
                adjusted_rand = safe_compare_partition(display_com, inverse_com, "adjusted.rand")
            ),
            display_vs_unweighted = list(
                vi = safe_compare_partition(display_com, unweighted_com, "vi"),
                nmi = safe_compare_partition(display_com, unweighted_com, "nmi"),
                adjusted_rand = safe_compare_partition(display_com, unweighted_com, "adjusted.rand")
            ),
            inverse_vs_unweighted = list(
                vi = safe_compare_partition(inverse_com, unweighted_com, "vi"),
                nmi = safe_compare_partition(inverse_com, unweighted_com, "nmi"),
                adjusted_rand = safe_compare_partition(inverse_com, unweighted_com, "adjusted.rand")
            )
        )
    )
}

graph.word <- function(mat.simi, index) {
    nm <- matrix(
        0,
        ncol = ncol(mat.simi),
        nrow = nrow(mat.simi),
        dimnames = list(row.names(mat.simi), colnames(mat.simi))
    )
    nm[, index] <- mat.simi[, index]
    nm[index, ] <- mat.simi[index, ]
    nm
}

# =============================================================================
# CLI: read JSON params and run
# =============================================================================
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
    stop("Usage: Rscript similitude_render.R params.json")
}

params <- fromJSON(args[1])
render_similitude(params)
