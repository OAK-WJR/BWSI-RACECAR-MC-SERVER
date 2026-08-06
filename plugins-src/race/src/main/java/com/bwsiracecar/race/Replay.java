package com.bwsiracecar.race;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.GameMode;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.Display;
import org.bukkit.entity.Entity;
import org.bukkit.entity.ItemDisplay;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitTask;
import org.bukkit.util.Vector;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;

/**
 * Plays finished runs back on a car, one at a time, and puts the player
 * whose run it is behind a chase camera for the duration.
 *
 * The camera is an item display teleported along behind the car, so the
 * client interpolates it exactly like the car; the player just spectates
 * it. The plugin owns the whole lifecycle: spectator mode starts when the
 * replay starts — not when the code is submitted — and ends at the finish.
 */
public class Replay {

    public static final String TAG = ReplayCar.ROOT_TAG;

    private static final double CAMERA_BACK = 7.0;
    private static final double CAMERA_UP = 2.5;
    private static final float CAMERA_PITCH = 12f;

    private final RacePlugin plugin;
    private final Deque<Submission.Result> pending = new ArrayDeque<>();
    private final Consumer<Submission.Result> onFinished;

    private ReplayCar voxelCar;
    private ModelCar modelCar;
    private ItemDisplay camera;
    private BukkitTask task;
    private boolean running;

    private UUID watcher;
    private GameMode watcherMode;

    public Replay(RacePlugin plugin, Consumer<Submission.Result> onFinished) {
        this.plugin = plugin;
        this.onFinished = onFinished;
    }

    /** Removes cars and cameras left behind by a crash mid-replay. */
    public void cleanup(World world) {
        for (Entity entity : world.getEntities()) {
            if (entity.getScoreboardTags().contains(ReplayCar.PART_TAG)) {
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
        if (world == null || !plugin.getConfig().getBoolean("replay.enabled", true)) {
            onFinished.accept(result);
            startNext();
            return;
        }

        running = true;
        plugin.getServer().broadcast(Component.text(
                "Now racing: " + result.player_name, NamedTextColor.AQUA));

        Location start = plugin.startLocation();
        // One entity when the resource pack supplies the model, thousands of
        // block displays when it does not.
        double carScale = plugin.getConfig().getDouble("replay.car-scale", 1.0);
        if (plugin.getConfig().getBoolean("replay.use-model-pack", false)) {
            modelCar = new ModelCar(start, plugin.getConfig()
                    .getDouble("replay.model-blocks-long", 3.5));
        } else {
            voxelCar = new ReplayCar(plugin.replayModel(), start, carScale);
        }
        camera = world.spawn(cameraSpot(world, start.toVector(), start.getYaw()),
                ItemDisplay.class, d -> {
                    d.setTeleportDuration(ReplayCar.STEP_TICKS);
                    d.setBillboard(Display.Billboard.FIXED);
                    d.addScoreboardTag(ReplayCar.PART_TAG);
                });
        attachWatcher(result);

        List<List<Double>> points = result.trajectory;
        double y = start.getY();
        // Trajectory points are one per tick; teleports land every STEP_TICKS
        // and the client interpolates across the gap. replay.speed above 1
        // consumes extra points per teleport, trading smoothness for pace.
        int speed = Math.max(1,
                (int) Math.round(plugin.getConfig().getDouble("replay.speed", 1.0)));
        int step = ReplayCar.STEP_TICKS * speed;
        int[] index = {0};
        task = plugin.getServer().getScheduler().runTaskTimer(plugin, () -> {
            if (index[0] >= points.size()) {
                finish(result);
                return;
            }
            List<Double> p = points.get(index[0]);
            index[0] += step;
            float yaw = p.get(2).floatValue();
            Location target = new Location(world, p.get(0), y, p.get(1));
            if (modelCar != null) {
                modelCar.moveTo(target, yaw);
            } else {
                voxelCar.moveTo(target, yaw);
            }
            camera.teleport(cameraSpot(world, target.toVector(), yaw));
        }, 1L, (long) ReplayCar.STEP_TICKS);
    }

    /** Behind and above the car, looking down its heading. */
    private Location cameraSpot(World world, Vector carPos, float yaw) {
        double radians = Math.toRadians(yaw);
        Vector back = new Vector(Math.sin(radians), 0, -Math.cos(radians))
                .multiply(CAMERA_BACK);
        Vector spot = carPos.clone().add(back).add(new Vector(0, CAMERA_UP, 0));
        return new Location(world, spot.getX(), spot.getY(), spot.getZ(),
                yaw, CAMERA_PITCH);
    }

    /** The player whose run this is rides the camera for the duration. */
    private void attachWatcher(Submission.Result result) {
        if (!plugin.getConfig().getBoolean("replay.spectate", true)) {
            return;
        }
        Player player = plugin.getServer().getPlayer(result.uuid());
        if (player == null || !player.isOnline()) {
            return;
        }
        watcher = player.getUniqueId();
        watcherMode = player.getGameMode();
        player.teleport(camera.getLocation());
        player.setGameMode(GameMode.SPECTATOR);
        player.setSpectatorTarget(camera);
        player.sendMessage(Component.text("Chase camera on - enjoy your lap.",
                NamedTextColor.AQUA));
    }

    private void releaseWatcher() {
        if (watcher == null) {
            return;
        }
        Player player = plugin.getServer().getPlayer(watcher);
        watcher = null;
        if (player == null || !player.isOnline()
                || player.getGameMode() != GameMode.SPECTATOR) {
            return;
        }
        player.setSpectatorTarget(null);
        player.setGameMode(watcherMode == null ? GameMode.SURVIVAL : watcherMode);
        Location desk = plugin.deskLocation();
        if (desk != null) {
            player.teleport(desk);
        }
    }

    private void finish(Submission.Result result) {
        task.cancel();
        onFinished.accept(result);
        releaseWatcher();
        if (camera != null) {
            camera.remove();
            camera = null;
        }
        // leave the car standing for a moment so spectators can look at it
        long podium = plugin.getConfig().getLong("replay.podium-seconds", 10) * 20L;
        ReplayCar finishedVoxel = voxelCar;
        ModelCar finishedModel = modelCar;
        voxelCar = null;
        modelCar = null;
        plugin.getServer().getScheduler().runTaskLater(plugin, () -> {
            if (finishedVoxel != null) {
                finishedVoxel.remove();
            }
            if (finishedModel != null) {
                finishedModel.remove();
            }
            running = false;
            startNext();
        }, podium);
    }

    public void stop() {
        if (task != null) {
            task.cancel();
        }
        releaseWatcher();
        if (camera != null) {
            camera.remove();
        }
        if (voxelCar != null) {
            voxelCar.remove();
        }
        if (modelCar != null) {
            modelCar.remove();
        }
        pending.clear();
        running = false;
    }
}
