package com.bwsiracecar.worldpolicy;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.GameMode;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerChangedWorldEvent;
import org.bukkit.event.player.PlayerGameModeChangeEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.inventory.ItemStack;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.util.io.BukkitObjectInputStream;
import org.bukkit.util.io.BukkitObjectOutputStream;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/**
 * Two sides of the server, kept honest.
 *
 * The survival worlds force survival mode on everyone; the lobby world
 * allows creative freely. Each side has its own inventory (including the
 * ender chest, or creative items would ride it across), swapped on every
 * world change, so nothing built in creative ever reaches survival.
 *
 * A player's first crossing finds no stored inventory for the other side;
 * their current one carries over that once and the sides split from there.
 */
public class WorldPolicyPlugin extends JavaPlugin implements Listener {

    @Override
    public void onEnable() {
        saveDefaultConfig();
        getServer().getPluginManager().registerEvents(this, this);
    }

    private String lobbyWorld() {
        return getConfig().getString("lobby-world", "test");
    }

    private String side(World world) {
        return world.getName().equals(lobbyWorld()) ? "lobby" : "survival";
    }

    private boolean inSurvivalSide(Player player) {
        return side(player.getWorld()).equals("survival");
    }

    // ------------------------------------------------------------ enforcement
    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        if (inSurvivalSide(player) && player.getGameMode() != GameMode.SURVIVAL
                && !player.hasPermission("worldpolicy.bypass")) {
            player.setGameMode(GameMode.SURVIVAL);
        }
    }

    @EventHandler
    public void onWorldChange(PlayerChangedWorldEvent event) {
        Player player = event.getPlayer();
        String from = side(event.getFrom());
        String to = side(player.getWorld());
        if (!from.equals(to)) {
            save(player, from);
            load(player, to);
        }
        if (to.equals("survival") && player.getGameMode() != GameMode.SURVIVAL
                && !player.hasPermission("worldpolicy.bypass")) {
            player.setGameMode(GameMode.SURVIVAL);
        }
    }

    @EventHandler
    public void onGameModeChange(PlayerGameModeChangeEvent event) {
        Player player = event.getPlayer();
        if (event.getNewGameMode() == GameMode.SURVIVAL
                || !inSurvivalSide(player)
                || player.hasPermission("worldpolicy.bypass")) {
            return;
        }
        event.setCancelled(true);
        player.sendMessage(Component.text(
                "Survival is survival. Creative lives in the lobby world.",
                NamedTextColor.RED));
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        save(event.getPlayer(), side(event.getPlayer().getWorld()));
    }

    // ------------------------------------------------------------ inventories
    private Path file(Player player, String sideName) {
        return getDataFolder().toPath().resolve("inv")
                .resolve(player.getUniqueId() + "-" + sideName + ".dat");
    }

    private void save(Player player, String sideName) {
        Path path = file(player, sideName);
        Path tmp = path.resolveSibling(path.getFileName() + ".tmp");
        try {
            Files.createDirectories(path.getParent());
            try (OutputStream out = Files.newOutputStream(tmp);
                 BukkitObjectOutputStream data = new BukkitObjectOutputStream(out)) {
                data.writeObject(player.getInventory().getContents());
                data.writeObject(player.getEnderChest().getContents());
            }
            Files.move(tmp, path, StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            getLogger().warning("Could not save inventory for "
                    + player.getName() + ": " + e.getMessage());
        }
    }

    private void load(Player player, String sideName) {
        Path path = file(player, sideName);
        if (!Files.exists(path)) {
            // first crossing: the current inventory carries over this once
            return;
        }
        try (InputStream in = Files.newInputStream(path);
             BukkitObjectInputStream data = new BukkitObjectInputStream(in)) {
            player.getInventory().setContents((ItemStack[]) data.readObject());
            player.getEnderChest().setContents((ItemStack[]) data.readObject());
        } catch (Exception e) {
            getLogger().warning("Could not load inventory for "
                    + player.getName() + ": " + e.getMessage());
        }
    }
}
