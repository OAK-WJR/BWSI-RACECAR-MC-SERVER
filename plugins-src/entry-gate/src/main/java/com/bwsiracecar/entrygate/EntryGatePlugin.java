package com.bwsiracecar.entrygate;

import io.papermc.paper.event.player.AsyncChatEvent;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import net.kyori.adventure.title.Title;
import org.bukkit.entity.Player;
import org.bukkit.potion.PotionEffect;
import org.bukkit.potion.PotionEffectType;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerMoveEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Asks a few questions before letting someone play.
 *
 * Minecraft has no way to prompt during the login handshake -- a player is
 * already in the world by the time a plugin can talk to them. The next best
 * thing, and what auth plugins do, is to hold them the moment they arrive:
 * blind, frozen, and unable to build until they answer. Short of running a
 * proxy with a separate limbo server, nothing gets closer to gating entry.
 *
 * The questions and answers live in config.yml on the server and are not part
 * of this repository. Without a config the gate stays open, so a fresh checkout
 * never locks anyone out by accident.
 */
public class EntryGatePlugin extends JavaPlugin implements Listener {

    private record Question(String prompt, String answer) {}

    private final List<Question> questions = new ArrayList<>();
    private final Map<UUID, Integer> position = new HashMap<>();
    private final Map<UUID, Integer> attempts = new HashMap<>();
    private int maxAttempts;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        loadQuestions();
        getServer().getPluginManager().registerEvents(this, this);
        getLogger().info(questions.isEmpty()
                ? "No questions configured, entry is open"
                : "Entry gate active with " + questions.size() + " question(s)");
    }

    private void loadQuestions() {
        questions.clear();
        maxAttempts = getConfig().getInt("max-attempts", 3);
        for (Map<?, ?> entry : getConfig().getMapList("questions")) {
            Object prompt = entry.get("prompt");
            Object answer = entry.get("answer");
            if (prompt != null && answer != null && !answer.toString().isBlank()) {
                questions.add(new Question(prompt.toString(), answer.toString()));
            }
        }
    }

    private boolean gated(Player player) {
        return position.containsKey(player.getUniqueId());
    }

    /** Blind and immobilise, so the world is not visible before answering. */
    private void hold(Player player) {
        player.addPotionEffect(new PotionEffect(
                PotionEffectType.BLINDNESS, PotionEffect.INFINITE_DURATION, 0, false, false));
        player.setInvulnerable(true);
    }

    private void ask(Player player) {
        int index = position.getOrDefault(player.getUniqueId(), 0);
        String prompt = questions.get(index).prompt();
        // The title line is rendered huge and does not wrap, so a question of
        // any length runs off both edges. Keep the counter up there and put the
        // question in the smaller subtitle, plus chat, which wraps properly.
        player.showTitle(Title.title(
                Component.text((index + 1) + " / " + questions.size(), NamedTextColor.YELLOW),
                Component.text(prompt, NamedTextColor.AQUA),
                Title.Times.times(Duration.ZERO, Duration.ofDays(1), Duration.ZERO)));
        player.sendMessage(Component.text(prompt, NamedTextColor.AQUA));
        player.sendActionBar(Component.text("Type your answer in chat", NamedTextColor.GRAY));
    }

    private void release(Player player) {
        position.remove(player.getUniqueId());
        attempts.remove(player.getUniqueId());
        player.removePotionEffect(PotionEffectType.BLINDNESS);
        player.setInvulnerable(false);
        player.clearTitle();
        player.sendMessage(Component.text("Welcome to BWSI Racecar.", NamedTextColor.GREEN));
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        if (questions.isEmpty()) {
            return;
        }
        Player player = event.getPlayer();
        if (player.hasPermission("entrygate.bypass")) {
            return;
        }
        position.put(player.getUniqueId(), 0);
        attempts.put(player.getUniqueId(), 0);
        hold(player);
        getServer().getScheduler().runTaskLater(this, () -> {
            if (player.isOnline()) {
                ask(player);
            }
        }, 10L);
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        position.remove(event.getPlayer().getUniqueId());
        attempts.remove(event.getPlayer().getUniqueId());
    }

    @EventHandler(priority = EventPriority.LOWEST)
    public void onChat(AsyncChatEvent event) {
        Player player = event.getPlayer();
        if (!gated(player)) {
            return;
        }
        // Answers must never reach public chat.
        event.setCancelled(true);

        String given = PlainTextComponentSerializer.plainText()
                .serialize(event.message()).trim();
        UUID id = player.getUniqueId();
        int index = position.getOrDefault(id, 0);

        getServer().getScheduler().runTask(this, () -> {
            if (!player.isOnline()) {
                return;
            }
            if (given.equalsIgnoreCase(questions.get(index).answer().trim())) {
                if (index + 1 >= questions.size()) {
                    release(player);
                } else {
                    position.put(id, index + 1);
                    ask(player);
                }
                return;
            }
            int used = attempts.merge(id, 1, Integer::sum);
            if (used >= maxAttempts) {
                player.kick(Component.text("Wrong answer.", NamedTextColor.RED));
            } else {
                player.sendMessage(Component.text(
                        "Not right. " + (maxAttempts - used) + " attempt(s) left.",
                        NamedTextColor.RED));
                ask(player);
            }
        });
    }

    @EventHandler
    public void onMove(PlayerMoveEvent event) {
        if (!gated(event.getPlayer())) {
            return;
        }
        // Looking around is fine; walking off is not.
        if (event.getFrom().getBlockX() != event.getTo().getBlockX()
                || event.getFrom().getBlockY() != event.getTo().getBlockY()
                || event.getFrom().getBlockZ() != event.getTo().getBlockZ()) {
            event.setCancelled(true);
        }
    }

    @EventHandler
    public void onCommand(PlayerCommandPreprocessEvent event) {
        if (gated(event.getPlayer())) {
            event.setCancelled(true);
            event.getPlayer().sendMessage(Component.text(
                    "Answer the question first.", NamedTextColor.RED));
        }
    }

    @EventHandler
    public void onBreak(BlockBreakEvent event) {
        if (gated(event.getPlayer())) {
            event.setCancelled(true);
        }
    }

    @EventHandler
    public void onPlace(BlockPlaceEvent event) {
        if (gated(event.getPlayer())) {
            event.setCancelled(true);
        }
    }
}
