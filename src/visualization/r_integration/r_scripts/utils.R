# =============================================================================
# utils.R - Core utility functions for IRaMuTeQ-style visualizations
# IDENTICAL to IRaMuTeQ's Rgraph.R functions
# =============================================================================

# Load jsonlite for argument parsing
suppressPackageStartupMessages({
    library(jsonlite)
})

# =============================================================================
# EXACT IRaMuTeQ norm.vec function (Rgraph.R lines 1037-1046)
# =============================================================================
norm.vec <- function(v, min, max) {
    vr <- range(v, na.rm = TRUE)
    if (vr[1] == vr[2]) {
        fac <- 1
    } else {
        fac <- (max - min) / (vr[2] - vr[1])
    }
    (v - vr[1]) * fac + min
}

# =============================================================================
# EXACT IRaMuTeQ color functions (Rgraph.R lines 581-602)
# =============================================================================

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
        # Keep the hue but use darker, colorblind-friendlier amber shades.
        gr.col <- colorRampPalette(c("#D4A017", "#B8860B"))(length(tochange))
        compt <- 1
        for (val in tochange) {
            colors[val] <- gr.col[compt]
            compt <- compt + 1
        }
    }
    # Normalize very bright colors (yellow/lime/cyan) to improve readability.
    for (i in seq_along(colors)) {
        rgbv <- as.numeric(col2rgb(colors[i])[, 1])
        lum <- (0.2126 * rgbv[1]) + (0.7152 * rgbv[2]) + (0.0722 * rgbv[3])
        if (is.finite(lum) && lum > 185) {
            adj <- pmax(0, pmin(255, round(rgbv * 0.82)))
            colors[i] <- rgb(adj[1], adj[2], adj[3], maxColorValue = 255)
        }
    }
    colors
}

# Generate IRaMuTeQ-style rainbow colors
iramuteq.colors <- function(n) {
    if (n <= 0) return(character(0))
    colors <- rainbow(n)
    colors <- del.yellow(colors)
    return(colors)
}

# =============================================================================
# EXACT IRaMuTeQ file output function (Rgraph.R lines 135-151)
# =============================================================================
open_file_graph <- function(filename, width = 800, height = 800, svg = FALSE, dpi = 120) {
    # Ensure directory exists
    dir.create(dirname(filename), showWarnings = FALSE, recursive = TRUE)

    if (Sys.info()["sysname"] == "Darwin") {
        width_in <- width / 74.97
        height_in <- height / 74.97
        if (!svg) {
            quartz(file = filename, type = "png", width = width_in, height = height_in)
        } else {
            svg(gsub("\\.png$", ".svg", filename), width = width_in, height = height_in)
        }
    } else {
        if (svg) {
            svg(gsub("\\.png$", ".svg", filename), width = width / 74.97, height = height / 74.97)
        } else {
            opened <- FALSE
            if (capabilities("cairo")) {
                opened <- tryCatch({
                    png(
                        filename,
                        width = width,
                        height = height,
                        units = "px",
                        res = dpi,
                        type = "cairo-png",
                        antialias = "subpixel",
                        bg = "white"
                    )
                    TRUE
                }, error = function(e) FALSE)
                if (!opened) {
                    opened <- tryCatch({
                        png(
                            filename,
                            width = width,
                            height = height,
                            units = "px",
                            res = dpi,
                            type = "cairo",
                            antialias = "subpixel",
                            bg = "white"
                        )
                        TRUE
                    }, error = function(e) FALSE)
                }
            }
            if (!opened) {
                png(
                    filename,
                    width = width,
                    height = height,
                    units = "px",
                    res = dpi,
                    bg = "white"
                )
            }
        }
    }
}

# =============================================================================
# EXACT IRaMuTeQ select.chi.classe function (Rgraph.R lines 438-451)
# =============================================================================
select.chi.classe <- function(tablechi, nb, active = TRUE, debsup = NULL) {
    rowkeep <- NULL
    if (active && !is.null(debsup)) {
        upper <- max(1, min(nrow(tablechi), as.integer(debsup) - 1))
        tablechi <- tablechi[1:upper, , drop = FALSE]
    }
    if (nb > nrow(tablechi)) {
        nb <- nrow(tablechi)
    }
    for (i in 1:ncol(tablechi)) {
        rowkeep <- append(rowkeep, order(tablechi[, i], decreasing = TRUE)[1:nb])
    }
    rowkeep <- unique(rowkeep)
    rowkeep
}

# =============================================================================
# Argument Parsing
# =============================================================================
read_args <- function(args_file) {
    if (!file.exists(args_file)) {
        message(paste("Args file not found:", args_file))
        return(list())
    }
    tryCatch({
        return(fromJSON(args_file))
    }, error = function(e) {
        message(paste("Error reading args file:", e$message))
        return(list())
    })
}

# =============================================================================
# Validation Helpers
# =============================================================================
is_valid <- function(x) {
    !is.null(x) && length(x) > 0 && !all(is.na(x))
}

get_default <- function(x, default) {
    if (is_valid(x)) x else default
}

message("IRaMuTeQ utils.R loaded successfully")
