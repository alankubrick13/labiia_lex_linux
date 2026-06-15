# network_text_fa2.R - Optional fallback for textual network rendering
# Uses igraph Fruchterman-Reingold layout and Louvain communities.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: Rscript network_text_fa2.R <params.json>")
}

params_file <- args[1]
params <- jsonlite::fromJSON(params_file)

suppressPackageStartupMessages({
  library(igraph)
})

edges_df <- read.csv(params$edges_csv, sep = ";", stringsAsFactors = FALSE)
g <- graph_from_data_frame(edges_df, directed = FALSE)
E(g)$weight <- edges_df$weight

lo <- layout_with_fr(g, weights = E(g)$weight, niter = 2000)
com <- cluster_louvain(g, weights = E(g)$weight, resolution = params$resolution)

deg <- degree(g)
wdeg <- strength(g)
betw <- betweenness(g, weights = E(g)$weight)
clos <- closeness(g, weights = E(g)$weight)

png(params$output_file, width = params$width, height = params$height, res = params$dpi)
par(mar = c(0, 0, 0, 0))

palette <- c(
  "#E63946", "#457B9D", "#2A9D8F", "#E9C46A", "#F4A261",
  "#264653", "#A8DADC", "#6A0572", "#1D3557", "#F77F00"
)
vertex_colors <- palette[(membership(com) %% length(palette)) + 1]
label_cex <- 0.4 + 1.6 * (deg - min(deg)) / max(max(deg) - min(deg), 1)

plot(
  g,
  layout = lo,
  vertex.size = 0,
  vertex.label = V(g)$name,
  vertex.label.cex = label_cex,
  vertex.label.color = vertex_colors,
  vertex.label.font = 2,
  edge.width = 0.3 + 1.5 * (E(g)$weight - min(E(g)$weight)) /
    max(max(E(g)$weight) - min(E(g)$weight), 1),
  edge.color = adjustcolor("#AAAAAA", alpha.f = 0.2),
  edge.curved = FALSE
)

dev.off()

nodes_df <- data.frame(
  id = V(g)$name,
  label = V(g)$name,
  degree = deg,
  weighted_degree = wdeg,
  betweenness = betw,
  closeness = clos,
  community = membership(com),
  x = lo[, 1],
  y = lo[, 2],
  stringsAsFactors = FALSE
)
write.csv(nodes_df, params$nodes_csv, row.names = FALSE)

edges_out <- as_data_frame(g, what = "edges")
edges_out$weight <- E(g)$weight
write.csv(edges_out, params$edges_csv_out, row.names = FALSE)

cat("OK\n")
