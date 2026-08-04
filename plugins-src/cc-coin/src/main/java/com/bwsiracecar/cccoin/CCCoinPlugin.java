package com.bwsiracecar.cccoin;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;

import java.io.InputStream;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.UUID;

/**
 * A pixelated CC Coin, voxelised from a scan of the real thing. One per
 * player: /cccoin places it hovering in front of you, /cccoin remove takes
 * it away.
 */
public class CCCoinPlugin extends JavaPlugin implements Listener {

    public static final String TAG = "bwsi_cccoin";

    /** Degrees per update; updates run every INTERPOLATION_TICKS. */
    private static final float SPIN_STEP = 6.0f;

    private final Map<UUID, Coin> coins = new HashMap<>();
    private CoinModel model;

    @Override
    public void onEnable() {
        try (InputStream stream = getResource("coin.json")) {
            model = CoinModel.load(stream);
        } catch (Exception e) {
            getLogger().severe("Could not load coin.json: " + e.getMessage());
            getServer().getPluginManager().disablePlugin(this);
            return;
        }
        getLogger().info(String.format("Model loaded: %d parts", model.parts().size()));

        getServer().getPluginManager().registerEvents(this, this);
        getServer().getScheduler().runTaskTimer(this, this::tickAll,
                Coin.INTERPOLATION_TICKS, Coin.INTERPOLATION_TICKS);
    }

    @Override
    public void onDisable() {
        coins.values().forEach(Coin::remove);
        coins.clear();
    }

    private void tickAll() {
        Iterator<Map.Entry<UUID, Coin>> it = coins.entrySet().iterator();
        while (it.hasNext()) {
            Coin coin = it.next().getValue();
            if (!coin.isValid()) {
                it.remove();
                continue;
            }
            coin.spin(SPIN_STEP);
        }
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Players only.");
            return true;
        }
        if (args.length > 0 && args[0].equalsIgnoreCase("remove")) {
            Coin coin = coins.remove(player.getUniqueId());
            if (coin != null) {
                coin.remove();
            }
            player.sendMessage(Component.text("Coin removed.", NamedTextColor.GRAY));
            return true;
        }

        Coin existing = coins.remove(player.getUniqueId());
        if (existing != null) {
            existing.remove();
        }

        Location spawn = player.getLocation().clone()
                .add(player.getLocation().getDirection().setY(0).normalize().multiply(2));
        Coin coin = new Coin(model, spawn);
        coin.tag();
        coins.put(player.getUniqueId(), coin);

        player.sendMessage(Component.text("CC Coin placed.", NamedTextColor.GOLD));
        return true;
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        Coin coin = coins.remove(event.getPlayer().getUniqueId());
        if (coin != null) {
            coin.remove();
        }
    }
}
