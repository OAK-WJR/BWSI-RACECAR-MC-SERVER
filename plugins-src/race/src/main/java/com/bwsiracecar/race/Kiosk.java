package com.bwsiracecar.race;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.Container;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemStack;

/**
 * The submission desk: stand on the plate holding your book to submit, and
 * take a fresh book from the chest beside it.
 *
 * Locations are read from the config on every use, so the desk can be built
 * and wired up with /race admin reload — no restart.
 */
public class Kiosk implements Listener {

    private final RacePlugin plugin;

    public Kiosk(RacePlugin plugin) {
        this.plugin = plugin;
    }

    public void enable() {
        plugin.getServer().getPluginManager().registerEvents(this, plugin);
        plugin.getServer().getScheduler().runTaskTimer(plugin, this::restock, 100L, 200L);
    }

    private boolean off() {
        return !plugin.getConfig().getBoolean("kiosk.enabled", false);
    }

    private Location configured(String key) {
        World world = plugin.raceWorld();
        if (world == null) {
            return null;
        }
        return new Location(world,
                plugin.getConfig().getInt("kiosk." + key + ".x"),
                plugin.getConfig().getInt("kiosk." + key + ".y"),
                plugin.getConfig().getInt("kiosk." + key + ".z"));
    }

    /** Keep a stack of blank books in the chest so nobody has to craft one. */
    private void restock() {
        if (off()) {
            return;
        }
        Location chest = configured("chest");
        if (chest == null || !chest.getChunk().isLoaded()) {
            return;
        }
        Block block = chest.getBlock();
        if (!(block.getState() instanceof Container container)) {
            return;
        }
        int want = plugin.getConfig().getInt("kiosk.books", 16);
        Inventory inventory = container.getInventory();
        int have = 0;
        for (ItemStack item : inventory.getContents()) {
            if (item != null && item.getType() == Material.WRITABLE_BOOK) {
                have += item.getAmount();
            }
        }
        if (have < want) {
            inventory.addItem(new ItemStack(Material.WRITABLE_BOOK, want - have));
        }
    }

    @EventHandler
    public void onStep(PlayerInteractEvent event) {
        if (off() || event.getAction() != Action.PHYSICAL || event.getClickedBlock() == null) {
            return;
        }
        Location plate = configured("plate");
        if (plate == null || !event.getClickedBlock().getLocation().equals(plate)) {
            return;
        }
        ItemStack held = event.getPlayer().getInventory().getItemInMainHand();
        if (held.getType() != Material.WRITABLE_BOOK
                && held.getType() != Material.WRITTEN_BOOK) {
            event.getPlayer().sendActionBar(Component.text(
                    "Hold your code book, then step on the plate", NamedTextColor.GRAY));
            return;
        }
        plugin.submitHeldBook(event.getPlayer());
    }
}
