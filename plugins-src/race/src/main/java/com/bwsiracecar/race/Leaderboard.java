package com.bwsiracecar.race;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Best lap time per player, kept in one JSON file next to the plugin config. */
public class Leaderboard {

    public static final class Entry {
        String name;
        double best_time_s;
        String set_at;
        int runs;

        public String name() {
            return name;
        }

        public double bestSeconds() {
            return best_time_s;
        }

        public int runs() {
            return runs;
        }
    }

    private static final class Store {
        Map<String, Entry> entries = new HashMap<>();
    }

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    private final Path file;
    private Store store = new Store();

    public Leaderboard(Path file) {
        this.file = file;
    }

    public void load() {
        if (!Files.exists(file)) {
            return;
        }
        try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            Store loaded = GSON.fromJson(reader, Store.class);
            if (loaded != null && loaded.entries != null) {
                store = loaded;
            }
        } catch (Exception e) {
            throw new IllegalStateException("could not read " + file, e);
        }
    }

    /** Records a run. Returns true when it beat the player's previous best. */
    public boolean record(UUID id, String name, double seconds) {
        Entry entry = store.entries.get(id.toString());
        boolean best = entry == null || seconds < entry.best_time_s;
        if (entry == null) {
            entry = new Entry();
            store.entries.put(id.toString(), entry);
        }
        entry.name = name;
        entry.runs++;
        if (best) {
            entry.best_time_s = seconds;
            entry.set_at = Instant.now().toString();
        }
        save();
        return best;
    }

    public void clear(UUID id) {
        store.entries.remove(id.toString());
        save();
    }

    public void clearAll() {
        store.entries.clear();
        save();
    }

    /** Entries sorted fastest first. */
    public List<Entry> ranking() {
        List<Entry> all = new ArrayList<>(store.entries.values());
        all.sort(Comparator.comparingDouble(e -> e.best_time_s));
        return all;
    }

    private void save() {
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        try {
            Files.createDirectories(file.getParent());
            try (Writer writer = Files.newBufferedWriter(tmp, StandardCharsets.UTF_8)) {
                GSON.toJson(store, writer);
            }
            Files.move(tmp, file, StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception e) {
            throw new IllegalStateException("could not write " + file, e);
        }
    }
}
