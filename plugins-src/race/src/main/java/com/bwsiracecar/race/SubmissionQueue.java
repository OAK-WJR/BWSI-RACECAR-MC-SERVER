package com.bwsiracecar.race;

import com.google.gson.Gson;

import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Writes submissions where the host-side runner picks them up, and tracks
 * who has one in flight. The file appears atomically so the runner never
 * reads a half-written submission.
 */
public class SubmissionQueue {

    private final Path queueDir;
    private final Map<UUID, String> inFlight = new HashMap<>();
    private final Map<UUID, Long> lastSubmit = new HashMap<>();

    public SubmissionQueue(Path queueDir) {
        this.queueDir = queueDir;
    }

    public boolean hasInFlight(UUID player) {
        return inFlight.containsKey(player);
    }

    public String idOf(UUID player) {
        return inFlight.get(player);
    }

    /** Seconds until this player may submit again, 0 when they may now. */
    public long cooldownLeft(UUID player, long cooldownSeconds) {
        Long last = lastSubmit.get(player);
        if (last == null) {
            return 0;
        }
        long elapsed = (System.currentTimeMillis() - last) / 1000;
        return Math.max(0, cooldownSeconds - elapsed);
    }

    public String enqueue(UUID player, String name, String code) throws Exception {
        String id = System.currentTimeMillis() + "_" + player;
        Submission.Payload payload = new Submission.Payload();
        payload.id = id;
        payload.player_uuid = player.toString();
        payload.player_name = name;
        payload.submitted_at = System.currentTimeMillis() / 1000.0;
        payload.code = code;

        Files.createDirectories(queueDir);
        Path tmp = queueDir.resolve(".tmp-" + id + ".json");
        try (Writer writer = Files.newBufferedWriter(tmp, StandardCharsets.UTF_8)) {
            new Gson().toJson(payload, writer);
        }
        Files.move(tmp, queueDir.resolve(id + ".json"), StandardCopyOption.ATOMIC_MOVE);

        inFlight.put(player, id);
        lastSubmit.put(player, System.currentTimeMillis());
        return id;
    }

    public void finish(UUID player) {
        inFlight.remove(player);
    }

    /** Drops a pending submission, deleting its queue file if it is still there. */
    public boolean cancel(UUID player) {
        String id = inFlight.remove(player);
        if (id == null) {
            return false;
        }
        try {
            Files.deleteIfExists(queueDir.resolve(id + ".json"));
        } catch (Exception e) {
            return false;
        }
        return true;
    }

    /** After a restart: anything still queued belongs to its player again. */
    public void rescan() {
        try (var stream = Files.list(queueDir)) {
            stream.filter(p -> p.getFileName().toString().endsWith(".json"))
                    .forEach(p -> {
                        String id = p.getFileName().toString().replace(".json", "");
                        int split = id.indexOf('_');
                        if (split > 0) {
                            try {
                                inFlight.put(UUID.fromString(id.substring(split + 1)), id);
                            } catch (IllegalArgumentException ignored) {
                                // not one of ours, the runner will clean it up
                            }
                        }
                    });
        } catch (Exception ignored) {
            // no queue directory yet
        }
    }
}
