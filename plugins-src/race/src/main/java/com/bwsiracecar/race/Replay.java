package com.bwsiracecar.race;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.Entity;
import org.bukkit.scheduler.BukkitTask;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.function.Consumer;

/**
 * Plays finished runs back on a real car, one at a time. The trajectory is
 * already one point per tick, so each tick simply moves to the next point.
 */
public class Replay {

    public static final String TAG = "bwsi_race_replay";

    private final RacePlugin plugin;
    private final Deque<Submission.Result> pending = new ArrayDeque<>();
    private final Consumer<Submission.Result> onFinished;

    private Car car;
    private BukkitTask task;
    private boolean running;

    public Replay(RacePlugin plugin, Consumer<Submission.Result> onFinished) {
        this.plugin = plugin;
        this.onFinished = onFinished;
    }

    /** Removes cars left behind by a crash mid-replay. */
    public void cleanup(World world) {
        for (Entity entity : world.getEntities()) {
            if (entity.getScoreboardTags().contains(TAG)) {
                entity.getPassengers().forEach(Entity::remove);
                entity.remove();
            }
        }
    }

    public void enqueue(Submission.Result result) {
        pending.add(result);
        startNext();
    }

    public boolean busy() {
        return running;
    }

    private void startNext() {
        if (running || pending.isEmpty()) {
            return;
        }
        Submission.Result result = pending.poll();
        World world = plugin.raceWorld();
        if (world == null || plugin.getConfig().getBoolean("replay.enabled", true) == false) {
            onFinished.accept(result);
            startNext();
            return;
        }

        running = true;
        plugin.getServer().broadcast(Component.text(
                "Now racing: " + result.player_name, NamedTextColor.AQUA));

        Location start = plugin.startLocation();
        car = new Car(plugin.model(), start);
        car.baseEntity().addScoreboardTag(TAG);

        List<List<Double>> points = result.trajectory;
        double y = start.getY();
        int[] index = {0};
        task = plugin.getServer().getScheduler().runTaskTimer(plugin, () -> {
            if (index[0] >= points.size()) {
                finish(result);
                return;
            }
            List<Double> p = points.get(index[0]++);
            float yaw = p.get(2).floatValue();
            car.setPose(new Location(world, p.get(0), y, p.get(1), yaw, 0f), yaw);
        }, 1L, 1L);
    }

    private void finish(Submission.Result result) {
        task.cancel();
        onFinished.accept(result);
        // leave the car standing for a moment so spectators can look at it
        long podium = plugin.getConfig().getLong("replay.podium-seconds", 10) * 20L;
        Car finished = car;
        car = null;
        plugin.getServer().getScheduler().runTaskLater(plugin, () -> {
            finished.remove();
            running = false;
            startNext();
        }, podium);
    }

    public void stop() {
        if (task != null) {
            task.cancel();
        }
        if (car != null) {
            car.remove();
        }
        pending.clear();
        running = false;
    }
}
