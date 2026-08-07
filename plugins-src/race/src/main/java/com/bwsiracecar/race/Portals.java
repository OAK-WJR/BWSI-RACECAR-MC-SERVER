package com.bwsiracecar.race;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.player.PlayerQuitEvent;

import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * The plate that sends you back where you were.
 *
 * Everyone came from a different place in the survival world, so a plate
 * that teleports to one fixed spot is wrong. Whenever a player leaves that
 * world we remember exactly where they stood, and the plate puts them back.
 */
public class Portals implements Listener {

    private static final class Spot {
        String world;
        double x, y, z;
        float yaw, pitch;
    }

    private final RacePlugin plugin;
    private final Path file;
    private final Map<String, Spot> spots = new HashMap<>();
    /** Where each player stood a moment ago, outside the lobby. */
    private final Map<String, Spot> live = new HashMap<>();

    public Portals(RacePlugin plugin) {
        this.plugin = plugin;
        this.file = plugin.getDataFolder().toPath().resolve("return-spots.json");
    }

    public void enable() {
        load();
        plugin.getServer().getPluginManager().registerEvents(this, plugin);
        // A world-change event fires once the player is already in the new
        // world, so their old position has to be remembered as they go.
        plugin.getServer().getScheduler().runTaskTimer(plugin, this::track, 20L, 20L);
    }

    private void track() {
        String lobby = plugin.getConfig().getString("world", "test");
        for (Player player : plugin.getServer().getOnlinePlayers()) {
            if (!player.getWorld().getName().equals(lobby)) {
                live.put(player.getUniqueId().toString(), spotOf(player.getLocation()));
            }
        }
    }

    /** Leaving the lobby world for anywhere else is what we remember. */
    @EventHandler
    public void onWorldChange(PlayerChangedWorldEvent event) {
        if (event.getFrom().getName().equals(plugin.getConfig().getString("world", "test"))) {
            return;
        }
        // The player is already standing in the new world by now, so keep the
        // position the tracker saw a moment before they left.
        Spot spot = live.get(event.getPlayer().getUniqueId().toString());
        if (spot != null) {
            spots.put(event.getPlayer().getUniqueId().toString(), spot);
            save();
        }
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        Location location = event.getPlayer().getLocation();
        if (!location.getWorld().getName().equals(plugin.getConfig().getString("world", "test"))) {
            remember(event.getPlayer(), location);
        }
    }

    private static Spot spotOf(Location location) {
        Spot spot = new Spot();
        spot.world = location.getWorld().getName();
        spot.x = location.getX();
        spot.y = location.getY();
        spot.z = location.getZ();
        spot.yaw = location.getYaw();
        spot.pitch = location.getPitch();
        return spot;
    }

    private void remember(Player player, Location location) {
        spots.put(player.getUniqueId().toString(), spotOf(location));
        save();
    }

    @EventHandler
    public void onStep(PlayerInteractEvent event) {
        if (!plugin.getConfig().getBoolean("portals.enabled", false)
                || event.getAction() != Action.PHYSICAL
                || event.getClickedBlock() == null) {
            return;
        }
        World world = plugin.raceWorld();
        if (world == null) {
            return;
        }
        Location plate = new Location(world,
                plugin.getConfig().getInt("portals.home-plate.x"),
                plugin.getConfig().getInt("portals.home-plate.y"),
                plugin.getConfig().getInt("portals.home-plate.z"));
        // Compare block coordinates: a Location also carries yaw and pitch,
        // and equals() checks those too.
        Location clicked = event.getClickedBlock().getLocation();
        if (clicked.getBlockX() != plate.getBlockX()
                || clicked.getBlockY() != plate.getBlockY()
                || clicked.getBlockZ() != plate.getBlockZ()) {
            return;
        }
        send(event.getPlayer());
    }

    /** Back to where this player last stood outside the lobby. */
    public void send(Player player) {
        plugin.getLogger().info("Return plate used by " + player.getName());
        Spot spot = spots.get(player.getUniqueId().toString());
        String lobby = plugin.getConfig().getString("world", "test");
        if (spot != null && lobby.equals(spot.world)) {
            spot = null;                    // a lobby spot is not a way home
        }
        Location target = null;
        if (spot != null) {
            World world = Bukkit.getWorld(spot.world);
            if (world != null) {
                target = new Location(world, spot.x, spot.y, spot.z, spot.yaw, spot.pitch);
            }
        }
        if (target == null) {
            World fallback = Bukkit.getWorld(
                    plugin.getConfig().getString("portals.fallback.world", ""));
            if (fallback == null) {
                player.sendMessage(Component.text(
                        "Nowhere to send you back to yet.", NamedTextColor.RED));
                return;
            }
            target = new Location(fallback,
                    plugin.getConfig().getDouble("portals.fallback.x"),
                    plugin.getConfig().getDouble("portals.fallback.y"),
                    plugin.getConfig().getDouble("portals.fallback.z"));
            player.sendMessage(Component.text(
                    "No saved spot, sending you to the world spawn.", NamedTextColor.GRAY));
        }
        player.teleport(target);
    }

    private void load() {
        if (!Files.exists(file)) {
            return;
        }
        try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            Map<String, Spot> loaded = new Gson().fromJson(
                    reader, new TypeToken<Map<String, Spot>>() {}.getType());
            if (loaded != null) {
                spots.putAll(loaded);
            }
        } catch (Exception e) {
            plugin.getLogger().warning("Could not read " + file + ": " + e.getMessage());
        }
    }

    private void save() {
        Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
        try {
            Files.createDirectories(file.getParent());
            try (Writer writer = Files.newBufferedWriter(tmp, StandardCharsets.UTF_8)) {
                new Gson().toJson(spots, writer);
            }
            Files.move(tmp, file, StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (Exception e) {
            plugin.getLogger().warning("Could not write " + file + ": " + e.getMessage());
        }
    }
}
