package com.lexianalyst.gephi;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.gephi.graph.api.Edge;
import org.gephi.graph.api.Graph;
import org.gephi.graph.api.GraphController;
import org.gephi.graph.api.GraphModel;
import org.gephi.graph.api.Node;
import org.gephi.graph.api.UndirectedGraph;
import org.gephi.layout.plugin.forceAtlas2.ForceAtlas2;
import org.gephi.layout.plugin.forceAtlas2.ForceAtlas2Builder;
import org.gephi.layout.plugin.noverlap.NoverlapLayout;
import org.gephi.layout.plugin.noverlap.NoverlapLayoutBuilder;
import org.gephi.project.api.ProjectController;
import org.gephi.project.api.Workspace;
import org.openide.util.Lookup;

public final class GephiRunner {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private GephiRunner() {
    }

    public static void main(String[] args) throws Exception {
        String paramsPath = parseParamsPath(args);
        Map<String, Object> params = MAPPER.readValue(new File(paramsPath), new TypeReference<Map<String, Object>>() {});

        Path edgesCsv = Path.of(str(params, "edges_csv"));
        Path positionsCsv = Path.of(str(params, "positions_csv"));
        Path diagJson = Path.of(str(params, "diag_json"));

        long started = System.nanoTime();
        Map<String, Object> diagnostics = new HashMap<>();
        diagnostics.put("runner", "gephi-toolkit");
        diagnostics.put("runner_version", "1.0.0");

        // Init Gephi project/workspace
        ProjectController pc = Lookup.getDefault().lookup(ProjectController.class);
        pc.newProject();
        Workspace workspace = pc.getCurrentWorkspace();
        GraphModel graphModel = Lookup.getDefault().lookup(GraphController.class).getGraphModel(workspace);

        // Build graph from edge CSV (source;target;weight)
        CsvGraphBuildResult graphData = loadCsvGraph(graphModel, edgesCsv);
        diagnostics.put("nodes", graphData.nodeCount);
        diagnostics.put("edges", graphData.edgeCount);

        // Deterministic initial positions help reproducibility.
        seedInitialPositions(graphData.nodes);

        // ForceAtlas2
        long fa2Start = System.nanoTime();
        ForceAtlas2 fa2 = new ForceAtlas2Builder().buildLayout();
        fa2.setGraphModel(graphModel);
        fa2.setScalingRatio(d(params, "fa2_scaling", 2.0));
        fa2.setGravity(d(params, "fa2_gravity", 1.0));
        fa2.setStrongGravityMode(b(params, "fa2_strong_gravity_mode", false));
        fa2.setEdgeWeightInfluence(d(params, "fa2_edge_weight_influence", 1.0));
        fa2.setJitterTolerance(d(params, "fa2_jitter_tolerance", 1.0));
        fa2.setBarnesHutTheta(d(params, "fa2_barnes_hut_theta", 1.2));
        fa2.setBarnesHutOptimize(b(params, "fa2_barnes_hut_optimize", graphData.nodeCount > 1000));

        int iterations = i(params, "fa2_iterations", 1000);
        fa2.initAlgo();
        for (int k = 0; k < iterations && fa2.canAlgo(); k++) {
            fa2.goAlgo();
        }
        fa2.endAlgo();
        diagnostics.put("fa2_elapsed_sec", secSince(fa2Start));
        diagnostics.put("fa2_iterations", iterations);

        // Optional Noverlap
        if (b(params, "noverlap_enabled", true)) {
            long noStart = System.nanoTime();
            NoverlapLayout noverlap = (NoverlapLayout) new NoverlapLayoutBuilder().buildLayout();
            noverlap.setGraphModel(graphModel);
            noverlap.setSpeed(d(params, "noverlap_speed", 3.0));
            noverlap.setRatio(d(params, "noverlap_ratio", 1.2));
            noverlap.setMargin(d(params, "noverlap_margin", 5.0));
            int noIterations = i(params, "noverlap_iterations", 50);
            noverlap.initAlgo();
            for (int k = 0; k < noIterations && noverlap.canAlgo(); k++) {
                noverlap.goAlgo();
            }
            noverlap.endAlgo();
            diagnostics.put("noverlap_elapsed_sec", secSince(noStart));
            diagnostics.put("noverlap_iterations", noIterations);
        } else {
            diagnostics.put("noverlap_elapsed_sec", 0.0);
            diagnostics.put("noverlap_iterations", 0);
        }

        writePositionsCsv(graphModel.getGraphVisible(), positionsCsv);

        diagnostics.put("elapsed_sec", secSince(started));
        diagnostics.put("java_version", System.getProperty("java.version"));

        if (diagJson.getParent() != null) {
            Files.createDirectories(diagJson.getParent());
        }
        MAPPER.writerWithDefaultPrettyPrinter().writeValue(diagJson.toFile(), diagnostics);
    }

    private static CsvGraphBuildResult loadCsvGraph(GraphModel graphModel, Path edgesCsv) throws IOException {
        if (!Files.exists(edgesCsv)) {
            throw new IOException("edges.csv nao encontrado: " + edgesCsv);
        }
        UndirectedGraph graph = graphModel.getUndirectedGraph();
        var factory = graphModel.factory();
        Map<String, Node> nodeById = new HashMap<>();
        int edgeCount = 0;

        try (BufferedReader reader = Files.newBufferedReader(edgesCsv, StandardCharsets.UTF_8)) {
            String header = reader.readLine();
            if (header == null) {
                return new CsvGraphBuildResult(new ArrayList<>(), 0, 0);
            }
            String line;
            while ((line = reader.readLine()) != null) {
                String raw = line.trim();
                if (raw.isEmpty()) {
                    continue;
                }
                String[] parts = raw.split(";");
                if (parts.length < 3) {
                    parts = raw.split(",");
                }
                if (parts.length < 3) {
                    continue;
                }

                String sourceId = parts[0].trim();
                String targetId = parts[1].trim();
                if (sourceId.isEmpty() || targetId.isEmpty()) {
                    continue;
                }
                double weight = parseDouble(parts[2].trim(), 1.0);

                Node source = nodeById.computeIfAbsent(sourceId, id -> {
                    Node created = factory.newNode(id);
                    created.setLabel(id);
                    graph.addNode(created);
                    return created;
                });
                Node target = nodeById.computeIfAbsent(targetId, id -> {
                    Node created = factory.newNode(id);
                    created.setLabel(id);
                    graph.addNode(created);
                    return created;
                });

                Edge existing = graph.getEdge(source, target);
                if (existing != null) {
                    existing.setWeight((float) (existing.getWeight() + weight));
                } else {
                    Edge edge = factory.newEdge(source, target, 0, (float) weight, false);
                    if (graph.addEdge(edge)) {
                        edgeCount += 1;
                    }
                }
            }
        }

        List<Node> nodes = new ArrayList<>();
        for (Node node : graph.getNodes()) {
            nodes.add(node);
        }
        nodes.sort((a, b) -> String.valueOf(a.getId()).compareTo(String.valueOf(b.getId())));

        return new CsvGraphBuildResult(nodes, nodes.size(), edgeCount);
    }

    private static void seedInitialPositions(List<Node> nodes) {
        int n = nodes.size();
        if (n == 0) {
            return;
        }
        double radius = 100.0;
        for (int idx = 0; idx < n; idx++) {
            Node node = nodes.get(idx);
            double angle = (2.0 * Math.PI * idx) / n;
            node.setX((float) (radius * Math.cos(angle)));
            node.setY((float) (radius * Math.sin(angle)));
        }
    }

    private static String parseParamsPath(String[] args) {
        if (args == null || args.length < 2) {
            throw new IllegalArgumentException("Usage: java -jar gephi-runner.jar --params <params.json>");
        }
        for (int i = 0; i < args.length - 1; i++) {
            if ("--params".equals(args[i])) {
                return args[i + 1];
            }
        }
        throw new IllegalArgumentException("Missing --params argument");
    }

    private static void writePositionsCsv(Graph graph, Path output) throws IOException {
        if (output.getParent() != null) {
            Files.createDirectories(output.getParent());
        }
        try (BufferedWriter writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)) {
            writer.write("id;x;y\n");
            for (Node node : graph.getNodes()) {
                String id = String.valueOf(node.getId());
                float x = node.x();
                float y = node.y();
                writer.write(String.format(Locale.US, "%s;%.8f;%.8f%n", id, x, y));
            }
        }
    }

    private static double secSince(long startedNano) {
        return (System.nanoTime() - startedNano) / 1_000_000_000.0;
    }

    private static String str(Map<String, Object> params, String key) {
        Object value = params.get(key);
        if (value == null) {
            throw new IllegalArgumentException("Missing required param: " + key);
        }
        return String.valueOf(value);
    }

    private static double d(Map<String, Object> params, String key, double fallback) {
        Object value = params.get(key);
        if (value == null) {
            return fallback;
        }
        if (value instanceof Number num) {
            return num.doubleValue();
        }
        return parseDouble(String.valueOf(value), fallback);
    }

    private static int i(Map<String, Object> params, String key, int fallback) {
        Object value = params.get(key);
        if (value == null) {
            return fallback;
        }
        if (value instanceof Number num) {
            return num.intValue();
        }
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (NumberFormatException exc) {
            return fallback;
        }
    }

    private static boolean b(Map<String, Object> params, String key, boolean fallback) {
        Object value = params.get(key);
        if (value == null) {
            return fallback;
        }
        if (value instanceof Boolean flag) {
            return flag;
        }
        String raw = String.valueOf(value).trim().toLowerCase(Locale.ROOT);
        if ("true".equals(raw) || "1".equals(raw) || "yes".equals(raw) || "sim".equals(raw)) {
            return true;
        }
        if ("false".equals(raw) || "0".equals(raw) || "no".equals(raw) || "nao".equals(raw)) {
            return false;
        }
        return fallback;
    }

    private static double parseDouble(String value, double fallback) {
        try {
            return Double.parseDouble(value);
        } catch (NumberFormatException exc) {
            return fallback;
        }
    }

    private record CsvGraphBuildResult(List<Node> nodes, int nodeCount, int edgeCount) {
    }
}
