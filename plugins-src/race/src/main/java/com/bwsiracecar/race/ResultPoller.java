package com.bwsiracecar.race;

import com.google.gson.Gson;

import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import java.util.stream.Collectors;

/**
 * Watches the results directory the host-side runner writes into. Results
 * arrive by atomic rename, so any file listed here is complete.
 */
public class ResultPoller {

    private static final int MAX_PARSE_ATTEMPTS = 10;

    private final RacePlugin plugin;
    private final Path resultsDir;
    private final Consumer<Submission.Result> handler;
    private final Map<String, Integer> failures = new HashMap<>();

    public ResultPoller(RacePlugin plugin, Path resultsDir,
                        Consumer<Submission.Result> handler) {
        this.plugin = plugin;
        this.resultsDir = resultsDir;
        this.handler = handler;
    }

    public void start() {
        plugin.getServer().getScheduler().runTaskTimerAsynchronously(
                plugin, this::poll, 40L, 20L);
    }

    private void poll() {
        List<Path> files;
        try (var stream = Files.list(resultsDir)) {
            files = stream.filter(p -> p.getFileName().toString().endsWith(".json"))
                    .sorted()
                    .collect(Collectors.toList());
        } catch (Exception e) {
            return;
        }
        for (Path file : files) {
            Submission.Result result = null;
            try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                result = new Gson().fromJson(reader, Submission.Result.class);
            } catch (Exception ignored) {
                // fall through to the retry counter below
            }
            String key = file.getFileName().toString();
            if (result == null || result.player_uuid == null) {
                int count = failures.merge(key, 1, Integer::sum);
                if (count >= MAX_PARSE_ATTEMPTS) {
                    plugin.getLogger().warning("Discarding unreadable result " + key);
                    delete(file);
                    failures.remove(key);
                }
                continue;
            }
            failures.remove(key);
            delete(file);
            Submission.Result parsed = result;
            plugin.getServer().getScheduler().runTask(plugin, () -> handler.accept(parsed));
        }
    }

    private void delete(Path file) {
        try {
            Files.deleteIfExists(file);
        } catch (Exception e) {
            plugin.getLogger().warning("Could not delete " + file + ": " + e.getMessage());
        }
    }
}
