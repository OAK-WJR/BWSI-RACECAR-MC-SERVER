package com.bwsiracecar.racecar;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.persistence.PersistentDataType;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.NamespacedKey;

import java.io.InputStream;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;

/**
 * A drivable, real-scale model of the BWSI RACECAR.
 *
 * The real car is 41 cm long and radio controlled, so this one is too: you hold
 * a controller rather than sit in it. Right-click drives, right-click again
 * stops, and the car follows wherever you are looking.
 */
public class RacecarPlugin extends JavaPlugin implements Listener {

    public static final String TAG = "bwsi_racecar";

    private static final double TOP_SPEED = 0.28;   // blocks per tick, ~5.6 m/s
    private static final double ACCELERATION = 0.02;
    private static final float TURN_RATE = 6.0f;    // degrees per tick

    private final Map<UUID, Car> cars = new HashMap<>();
    private final Map<UUID, Boolean> driving = new HashMap<>();
    private CarModel model;
    private NamespacedKey controllerKey;

    @Override
    public void onEnable() {
        controllerKey = new NamespacedKey(this, "controller");
        try (InputStream stream = getResource("car.json")) {
            model = CarModel.load(stream);
        } catch (Exception e) {
            getLogger().severe("Could not load car.json: " + e.getMessage());
            getServer().getPluginManager().disablePlugin(this);
            return;
        }
        getLogger().info(String.format("Model loaded: %d parts, %.2f m long",
                model.parts().size(), model.lengthMetres()));

        getServer().getPluginManager().registerEvents(this, this);
        getServer().getScheduler().runTaskTimer(this, this::tickAll, 1L, 1L);
    }

    @Override
    public void onDisable() {
        cars.values().forEach(Car::remove);
        cars.clear();
    }

    private void tickAll() {
        Iterator<Map.Entry<UUID, Car>> it = cars.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<UUID, Car> entry = it.next();
            Car car = entry.getValue();
            Player owner = getServer().getPlayer(entry.getKey());

            if (owner == null || !owner.isOnline()) {
                car.remove();
                it.remove();
                continue;
            }
            if (driving.getOrDefault(entry.getKey(), false)) {
                car.steerTowards(owner.getLocation().getYaw(), TURN_RATE);
                car.setSpeed(Math.min(TOP_SPEED, car.speed() + ACCELERATION));
            } else {
                car.setSpeed(Math.max(0, car.speed() - ACCELERATION * 2));
            }
            if (!car.tick()) {
                it.remove();
            }
        }
    }

    private ItemStack controller() {
        ItemStack item = new ItemStack(Material.CARROT_ON_A_STICK);
        ItemMeta meta = item.getItemMeta();
        meta.displayName(Component.text("RACECAR Controller", NamedTextColor.AQUA)
                .decoration(net.kyori.adventure.text.format.TextDecoration.ITALIC, false));
        meta.getPersistentDataContainer().set(controllerKey, PersistentDataType.BYTE, (byte) 1);
        item.setItemMeta(meta);
        return item;
    }

    private boolean isController(ItemStack item) {
        return item != null
                && item.hasItemMeta()
                && item.getItemMeta().getPersistentDataContainer()
                        .has(controllerKey, PersistentDataType.BYTE);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Players only.");
            return true;
        }
        if (args.length > 0 && args[0].equalsIgnoreCase("remove")) {
            Car car = cars.remove(player.getUniqueId());
            if (car != null) {
                car.remove();
            }
            player.sendMessage(Component.text("Car removed.", NamedTextColor.GRAY));
            return true;
        }

        Car existing = cars.remove(player.getUniqueId());
        if (existing != null) {
            existing.remove();
        }

        Location spawn = player.getLocation().clone()
                .add(player.getLocation().getDirection().setY(0).normalize().multiply(1.5));
        Car car = new Car(model, spawn);
        car.tag();
        cars.put(player.getUniqueId(), car);
        driving.put(player.getUniqueId(), false);

        if (!player.getInventory().contains(Material.CARROT_ON_A_STICK)) {
            player.getInventory().addItem(controller());
        }
        player.sendMessage(Component.text(
                "RACECAR placed. Hold the controller and right-click to drive; "
                        + "it follows where you look.", NamedTextColor.GREEN));
        return true;
    }

    @EventHandler
    public void onInteract(PlayerInteractEvent event) {
        if (!event.getAction().isRightClick() || !isController(event.getItem())) {
            return;
        }
        event.setCancelled(true);
        UUID id = event.getPlayer().getUniqueId();
        if (!cars.containsKey(id)) {
            event.getPlayer().sendMessage(Component.text(
                    "No car yet — run /racecar", NamedTextColor.RED));
            return;
        }
        boolean now = !driving.getOrDefault(id, false);
        driving.put(id, now);
        event.getPlayer().sendActionBar(Component.text(
                now ? "Driving" : "Stopped",
                now ? NamedTextColor.GREEN : NamedTextColor.GRAY));
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        Car car = cars.remove(event.getPlayer().getUniqueId());
        if (car != null) {
            car.remove();
        }
        driving.remove(event.getPlayer().getUniqueId());
    }
}
