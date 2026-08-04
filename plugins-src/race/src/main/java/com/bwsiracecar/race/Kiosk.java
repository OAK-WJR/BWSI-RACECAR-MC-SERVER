package com.bwsiracecar.race;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.block.Block;
import org.bukkit.block.Container;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.block.Action;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.inventory.Inventory;
import org.bukkit.inventory.ItemStack;

/**
 * The submission desk by the start line: stand on the plate holding your
 * book to submit, and take a fresh book from the chest beside it.
 */
public class Kiosk implements Listener {

    private final RacePlugin plugin;
    private Location plate;
    private Location chest;
    private int stock;

    public Kiosk(RacePlugin plugin) {
        this.plugin = plugin;
    }

    public void enable() {
        if (!plugin.getConfig().getBoolean("kiosk.enabled", false)) {
            return;
        }
        var world = plugin.raceWorld();
        if (world == null) {
            return;
        }
        plate = new Location(world,
                plugin.getConfig().getInt("kiosk.plate.x"),
                plugin.getConfig().getInt("kiosk.plate.y"),
                plugin.getConfig().getInt("kiosk.plate.z"));
        chest = new Location(world,
                plugin.getConfig().getInt("kiosk.chest.x"),
                plugin.getConfig().getInt("kiosk.chest.y"),
                plugin.getConfig().getInt("kiosk.chest.z"));
        stock = plugin.getConfig().getInt("kiosk.books", 16);

        plugin.getServer().getPluginManager().registerEvents(this, plugin);
        plugin.getServer().getScheduler().runTaskTimer(plugin, this::restock, 100L, 200L);
    }

    /** Keep a stack of blank books in the chest so nobody has to craft one. */
    private void restock() {
        Block block = chest.getBlock();
        if (!(block.getState() instanceof Container container)) {
            return;
        }
        Inventory inventory = container.getInventory();
        int have = 0;
        for (ItemStack item : inventory.getContents()) {
            if (item != null && item.getType() == Material.WRITABLE_BOOK) {
                have += item.getAmount();
            }
        }
        if (have < stock) {
            inventory.addItem(new ItemStack(Material.WRITABLE_BOOK, stock - have));
        }
    }

    @EventHandler
    public void onStep(PlayerInteractEvent event) {
        if (event.getAction() != Action.PHYSICAL || plate == null
                || event.getClickedBlock() == null
                || !event.getClickedBlock().getLocation().equals(plate)) {
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
