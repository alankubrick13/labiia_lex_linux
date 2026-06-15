#!/usr/bin/env Rscript
# =============================================================================
# similarity.R - IRaMuTeQ style similarity graph
# Based on simi.R from IRaMuTeQ 0.8a7
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

# Load required package
suppressPackageStartupMessages({
    library(igraph)
})

norm_coords <- function(coords, xmin = -1, xmax = 1, ymin = -1, ymax = 1) {
    if (is.null(coords) || nrow(coords) == 0) {
        return(coords)
    }
    out <- coords
    xr <- range(coords[, 1], na.rm = TRUE)
    if (!all(is.finite(xr)) || xr[1] == xr[2]) {
        out[, 1] <- 0
    } else {
        out[, 1] <- (coords[, 1] - xr[1]) / (xr[2] - xr[1]) * (xmax - xmin) + xmin
    }
    yr <- range(coords[, 2], na.rm = TRUE)
    if (!all(is.finite(yr)) || yr[1] == yr[2]) {
        out[, 2] <- 0
    } else {
        out[, 2] <- (coords[, 2] - yr[1]) / (yr[2] - yr[1]) * (ymax - ymin) + ymin
    }
    out
}

spirale_layout <- function(g, index.word = 1) {
    n <- vcount(g)
    if (n <= 1) {
        return(matrix(c(0, 0), ncol = 2))
    }
    center <- max(1, min(as.integer(index.word), n))
    dist_center <- distances(g, v = center, to = V(g), weights = NA)[1, ]
    dist_center[!is.finite(dist_center)] <- max(dist_center[is.finite(dist_center)], na.rm = TRUE) + 1
    ord <- order(dist_center, decreasing = FALSE)
    theta <- seq(0, 6 * pi, length.out = n)
    radius <- seq(0.05, 1, length.out = n)
    lo <- matrix(0, nrow = n, ncol = 2)
    lo[ord, 1] <- radius * cos(theta)
    lo[ord, 2] <- radius * sin(theta)
    lo
}

normalize_community_method <- function(communities) {
    if (is.null(communities) || (length(communities) == 1 && is.na(communities))) {
        return(NULL)
    }

    if (is.numeric(communities)) {
        code <- as.integer(communities[1])
        if (code == 0) {
            return("edge_betweenness")
        }
        if (code == 1) {
            return("fastgreedy")
        }
        if (code == 2) {
            return("label_propagation")
        }
        if (code == 3) {
            return("leading_eigenvector")
        }
        if (code == 4) {
            return("multilevel")
        }
        if (code == 5) {
            return("optimal")
        }
        if (code == 6) {
            return("spinglass")
        }
        if (code == 7) {
            return("walktrap")
        }
        return("multilevel")
    }

    method <- tolower(as.character(communities[1]))
    aliases <- c(
        "edge_betweenness" = "edge_betweenness",
        "betweenness" = "edge_betweenness",
        "fastgreedy" = "fastgreedy",
        "label_propagation" = "label_propagation",
        "leading_eigenvector" = "leading_eigenvector",
        "multilevel" = "multilevel",
        "louvain" = "multilevel",
        "optimal" = "optimal",
        "spinglass" = "spinglass",
        "walktrap" = "walktrap"
    )
    if (method %in% names(aliases)) {
        return(aliases[[method]])
    }
    "multilevel"
}

detect_communities <- function(g, method) {
    if (is.null(method) || vcount(g) <= 1) {
        return(NULL)
    }
    tryCatch(
        {
            if (method == "edge_betweenness") {
                return(cluster_edge_betweenness(g))
            }
            if (method == "fastgreedy") {
                return(cluster_fast_greedy(as.undirected(g)))
            }
            if (method == "label_propagation") {
                return(cluster_label_prop(g))
            }
            if (method == "leading_eigenvector") {
                return(cluster_leading_eigen(as.undirected(g)))
            }
            if (method == "multilevel") {
                return(cluster_louvain(as.undirected(g)))
            }
            if (method == "optimal") {
                return(cluster_optimal(as.undirected(g)))
            }
            if (method == "spinglass") {
                return(cluster_spinglass(as.undirected(g)))
            }
            if (method == "walktrap") {
                return(cluster_walktrap(g))
            }
            cluster_louvain(as.undirected(g))
        },
        error = function(e) {
            message(paste("Community detection failed:", e$message))
            NULL
        }
    )
}

create_similarity_plot <- function(matrix_file, freq_file = NULL, output_file,
                                   width = 1000, height = 1000,
                                   method = "cooc", max.tree = TRUE,
                                   layout.type = "frutch",
                                   vcexmin = 1.0, vcexmax = 2.5,
                                   coeff.edge.min = 1, coeff.edge.max = 10,
                                   communities = NULL, halo = FALSE,
                                   edge.curved = FALSE,
                                   grayscale = FALSE,
                                   seuil = 0,
                                   minmaxeff = c(5, 30),
                                   show_edge_labels = FALSE,
                                   cexalpha = FALSE,
                                   index.word = 1,
                                   graph_word = NULL,
                                   communities_out = NULL,
                                   centrality_out = NULL,
                                   gexf_output = NULL) {
    message("Loading similarity matrix...")

    mat.simi <- tryCatch(
        as.matrix(read.csv(matrix_file, row.names = 1, sep = ";", check.names = FALSE)),
        error = function(e) as.matrix(read.csv(matrix_file, row.names = 1, check.names = FALSE))
    )
    v.label <- colnames(mat.simi)

    if (is.null(v.label) || length(v.label) == 0) {
        stop("Similarity matrix has no labels")
    }

    # Load frequencies
    if (!is.null(freq_file) && file.exists(freq_file)) {
        freq_df <- tryCatch(
            read.csv(freq_file, sep = ";", stringsAsFactors = FALSE),
            error = function(e) read.csv(freq_file, stringsAsFactors = FALSE)
        )
        mat.eff <- freq_df$frequency
        names(mat.eff) <- freq_df$word
        mat.eff <- mat.eff[v.label]
        mat.eff[is.na(mat.eff)] <- 1
    } else {
        mat.eff <- rep(1, length(v.label))
        names(mat.eff) <- v.label
    }

    message("Creating graph...")
    g1 <- graph.adjacency(mat.simi, mode = "lower", weighted = TRUE)
    g.toplot <- g1

    # Maximum spanning tree (IRaMuTeQ simi.R lines 143-157)
    if (max.tree && ecount(g1) > 0) {
        weori <- E(g1)$weight
        if (method == "cooc") {
            invw <- 1 / weori
        } else {
            invw <- 1 - weori
        }
        E(g1)$weight <- invw
        g.max <- minimum.spanning.tree(g1)
        if (method == "cooc") {
            E(g.max)$weight <- 1 / E(g.max)$weight
        } else {
            E(g.max)$weight <- 1 - E(g.max)$weight
        }
        g.toplot <- g.max
    }

    # Threshold filtering (IRaMuTeQ simi.R lines 159-175)
    seuil <- suppressWarnings(as.numeric(seuil))
    if (!is.na(seuil) && seuil > 0 && ecount(g.toplot) > 0) {
        w <- E(g.toplot)$weight
        tovire <- which(w <= seuil)
        if (length(tovire) > 0) {
            g.toplot <- delete.edges(g.toplot, E(g.toplot)[tovire])
        }
        if (ecount(g.toplot) > 0) {
            g.toplot <- delete.vertices(g.toplot, degree(g.toplot) == 0)
        }
    }

    # Single-word subgraph (IRaMuTeQ graph.word analogue)
    if (!is.null(graph_word)) {
        center_word <- trimws(as.character(graph_word)[1])
        if (nzchar(center_word) && center_word %in% V(g.toplot)$name) {
            center_vid <- which(V(g.toplot)$name == center_word)[1]
            neighbors_vid <- as.integer(neighbors(g.toplot, center_vid, mode = "all"))
            keep_vid <- unique(c(center_vid, neighbors_vid))
            g.toplot <- induced_subgraph(g.toplot, vids = keep_vid)
        }
    }

    if (vcount(g.toplot) == 0 || ecount(g.toplot) == 0) {
        stop("Empty graph after filtering")
    }

    v.label <- V(g.toplot)$name
    mat.eff <- mat.eff[v.label]
    mat.eff[is.na(mat.eff)] <- 1

    label.cex <- norm.vec(mat.eff, vcexmin, vcexmax)
    # Text-first style to mirror the default IRaMuTeQ static plot look.
    vertex.size.val <- rep(0, length(mat.eff))

    if (ecount(g.toplot) > 0) {
        we.width <- norm.vec(abs(E(g.toplot)$weight), coeff.edge.min, coeff.edge.max)
        if (tolower(method) == "binom") {
            we.label <- round(E(g.toplot)$weight, 4)
        } else {
            we.label <- round(E(g.toplot)$weight, 3)
        }
    } else {
        we.width <- numeric(0)
        we.label <- NA
    }

    # Layouts
    if (layout.type == "fruchterman") layout.type <- "frutch"
    if (layout.type == "kamada") layout.type <- "kawa"
    if (layout.type == "circular") layout.type <- "circle"

    message("Calculating layout...")
    if (layout.type == "frutch") {
        lo <- tryCatch(
            {
                if (!requireNamespace("sna", quietly = TRUE) || !requireNamespace("intergraph", quietly = TRUE)) {
                    stop("sna/intergraph unavailable")
                }
                sna::gplot.layout.fruchtermanreingold(intergraph::asNetwork(g.toplot), list())
            },
            error = function(e) {
                layout_with_fr(g.toplot, niter = 2000)
            }
        )
    } else if (layout.type == "kawa") {
        lo <- tryCatch(
            {
                layout_with_kk(g.toplot, weights = 1 / E(g.toplot)$weight)
            },
            error = function(e) {
                layout_with_kk(g.toplot)
            }
        )
    } else if (layout.type == "random") {
        lo <- layout_on_grid(g.toplot)
    } else if (layout.type == "circle") {
        lo <- layout_in_circle(g.toplot)
    } else if (layout.type == "graphopt") {
        lo <- layout_as_tree(g.toplot, circular = TRUE)
    } else if (layout.type == "spirale" || layout.type == "spirale3D") {
        lo <- spirale_layout(g.toplot, index.word = index.word)
    } else {
        lo <- layout_with_fr(g.toplot, niter = 2000)
    }
    rownames(lo) <- V(g.toplot)$name

    # Community detection
    com <- NULL
    vertex.label.color <- rep("black", vcount(g.toplot))
    vertex.color.val <- rep("red", vcount(g.toplot))

    method_name <- normalize_community_method(communities)
    if (!is.null(method_name)) {
        message("Detecting communities...")
        com <- detect_communities(g.toplot, method_name)
    }

    if (isTRUE(cexalpha)) {
        alpha_vec <- norm.vec(label.cex, 0.25, 1)
        vertex.label.color <- mapply(
            function(colv, aval) adjustcolor(colv, alpha.f = aval),
            vertex.label.color,
            alpha_vec,
            USE.NAMES = FALSE
        )
    }

    # Optional exports
    if (!is.null(communities_out)) {
        if (!is.null(com)) {
            write.csv(
                data.frame(term = V(g.toplot)$name, community = membership(com)),
                file = communities_out,
                row.names = FALSE
            )
        } else {
            write.csv(
                data.frame(term = character(), community = integer()),
                file = communities_out,
                row.names = FALSE
            )
        }
    }
    if (!is.null(centrality_out)) {
        deg <- degree(g.toplot, mode = "all")
        wdeg <- strength(g.toplot, mode = "all")
        write.csv(
            data.frame(term = V(g.toplot)$name, degree = as.numeric(deg), weighted_degree = as.numeric(wdeg)),
            file = centrality_out,
            row.names = FALSE
        )
    }
    if (!is.null(gexf_output) && nzchar(gexf_output) && requireNamespace("rgexf", quietly = TRUE)) {
        nodes <- data.frame(label = V(g.toplot)$name, stringsAsFactors = FALSE)
        edges <- as_data_frame(g.toplot, what = "edges")
        edges$source <- as.integer(match(edges$from, V(g.toplot)$name)) - 1
        edges$target <- as.integer(match(edges$to, V(g.toplot)$name)) - 1
        rg <- rgexf::gexf(
            nodes = nodes,
            edges = edges[, c("source", "target"), drop = FALSE],
            edgesWeight = as.numeric(edges$weight)
        )
        rgexf::write.gexf(rg, output = gexf_output)
    }

    # Plot
    message("Generating plot...")
    is_svg <- grepl("\\.svg$", output_file, ignore.case = TRUE)
    open_file_graph(output_file, width = width, height = height, svg = is_svg)
    par(mar = c(2, 2, 2, 2), bg = "white")
    curved_val <- FALSE

    # Edge color (IRaMuTeQ cola = rgb(200,200,200))
    edge_col <- rgb(200, 200, 200, maxColorValue = 255)
    # Always render a clean text-first graph (no halos, no edge labels).
    plot(g.toplot,
        vertex.label = "",
        edge.width = we.width,
        vertex.size = vertex.size.val,
        vertex.color = vertex.color.val,
        vertex.frame.color = NA,
        edge.color = edge_col,
        edge.label = NA,
        edge.label.cex = 0.7,
        vertex.label.cex = 0,
        layout = lo,
        edge.curved = curved_val
    )

    txt.layout <- norm_coords(lo, -1, 1, -1, 1)
    text(txt.layout[, 1], txt.layout[, 2], V(g.toplot)$name,
        cex = label.cex,
        col = vertex.label.color,
        font = 2
    )

    dev.off()
    message(paste("Graph saved to:", output_file))
}

# =============================================================================
# CLI Interface
# =============================================================================
args <- commandArgs(trailingOnly = TRUE)
if (length(args) >= 1) {
    params <- read_args(args[1])

    detect_communities <- if (is.null(params$detect_communities)) FALSE else params$detect_communities
    community_value <- if (is.null(params$community_method)) {
        if (is.null(params$communities)) NULL else params$communities
    } else {
        params$community_method
    }
    if (!isTRUE(detect_communities)) {
        community_value <- NULL
    }

    halo_value <- if (is.null(params$halos)) {
        if (is.null(params$show_halo)) FALSE else params$show_halo
    } else {
        params$halos
    }

    seuil_value <- if (is.null(params$seuil)) {
        if (is.null(params$min_edge)) 0 else params$min_edge
    } else {
        params$seuil
    }

    minmaxeff_value <- if (is.null(params$minmaxeff)) {
        c(
            if (is.null(params$vertex_size_min)) 2 else params$vertex_size_min,
            if (is.null(params$vertex_size_max)) 20 else params$vertex_size_max
        )
    } else {
        params$minmaxeff
    }

    show_edge_labels_value <- if (is.null(params$edge_label)) {
        if (is.null(params$show_edge_labels)) FALSE else params$show_edge_labels
    } else {
        params$edge_label
    }

    communities_out <- if (is.null(params$communities_out)) NULL else params$communities_out
    centrality_out <- if (is.null(params$centrality_out)) NULL else params$centrality_out
    gexf_output <- if (is.null(params$gexf_output)) NULL else params$gexf_output
    graph_word_value <- if (is.null(params$graph_word)) NULL else params$graph_word

    create_similarity_plot(
        matrix_file = params$matrix_file,
        freq_file = params$freq_file,
        output_file = params$output_file,
        width = ifelse(is.null(params$width), 1000, params$width),
        height = ifelse(is.null(params$height), 1000, params$height),
        method = ifelse(is.null(params$method), "cooc", params$method),
        max.tree = ifelse(is.null(params$max_tree), TRUE, params$max_tree),
        layout.type = ifelse(is.null(params$layout), "frutch", params$layout),
        vcexmin = ifelse(is.null(params$vcexmin), 1.0, params$vcexmin),
        vcexmax = ifelse(is.null(params$vcexmax), 2.5, params$vcexmax),
        coeff.edge.min = ifelse(is.null(params$coeff_edge_min), 1, params$coeff_edge_min),
        coeff.edge.max = ifelse(is.null(params$coeff_edge_max), 10, params$coeff_edge_max),
        communities = community_value,
        halo = halo_value,
        edge.curved = ifelse(is.null(params$edge_curved), TRUE, params$edge_curved),
        grayscale = ifelse(is.null(params$grayscale), FALSE, params$grayscale),
        seuil = seuil_value,
        minmaxeff = minmaxeff_value,
        show_edge_labels = show_edge_labels_value,
        cexalpha = ifelse(is.null(params$cexalpha), FALSE, params$cexalpha),
        index.word = ifelse(is.null(params$index_word), 1, params$index_word),
        graph_word = graph_word_value,
        communities_out = communities_out,
        centrality_out = centrality_out,
        gexf_output = gexf_output
    )
}
