package com.bwsiracecar.race;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.block.Block;
import org.bukkit.block.Container;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.BookMeta;
import org.bukkit.plugin.java.JavaPlugin;

import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Code-controlled racing: players submit Python in a book, a sandbox off the
 * server works out the lap, and the result is replayed on a car and ranked.
 */
public class RacePlugin extends JavaPlugin {

    public static final String CAR_TAG = "bwsi_race_car";

    private CarModel model;
    private CarModel replayModel;
    private Leaderboard leaderboard;
    private SubmissionQueue queue;
    private Hologram hologram;
    private Replay replay;
    private Kiosk kiosk;
    private Portals portals;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        try (InputStream stream = getResource("car.json")) {
            model = CarModel.load(stream);
        } catch (Exception e) {
            getLogger().severe("Could not load car.json: " + e.getMessage());
            getServer().getPluginManager().disablePlugin(this);
            return;
        }
        try (InputStream stream = getResource("car_replay.json")) {
            replayModel = CarModel.load(stream);
        } catch (Exception e) {
            getLogger().severe("Could not load car_replay.json: " + e.getMessage());
            getServer().getPluginManager().disablePlugin(this);
            return;
        }
        getLogger().info(String.format("Replay model: %d parts", replayModel.parts().size()));

        Path data = getDataFolder().toPath();
        leaderboard = new Leaderboard(data.resolve("leaderboard.json"));
        leaderboard.load();
        queue = new SubmissionQueue(data.resolve(getConfig().getString("dirs.queue", "queue")));
        queue.rescan();
        replay = new Replay(this, this::onRunFinished);
        hologram = new Hologram(leaderboard, getConfig().getInt("hologram.lines", 10));
        kiosk = new Kiosk(this);
        kiosk.enable();
        portals = new Portals(this);
        portals.enable();

        Path results = data.resolve(getConfig().getString("dirs.results", "results"));
        try {
            java.nio.file.Files.createDirectories(results);
        } catch (Exception e) {
            getLogger().warning("Could not create " + results + ": " + e.getMessage());
        }
        new ResultPoller(this, results, this::onResult).start();

        // worlds managed by Multiverse are not loaded yet at onEnable
        getServer().getScheduler().runTaskLater(this, () -> {
            World world = raceWorld();
            if (world == null) {
                getLogger().warning("World '" + getConfig().getString("world")
                        + "' not found; races cannot be replayed");
                return;
            }
            replay.cleanup(world);
            if (getConfig().getBoolean("hologram.enabled", true)) {
                hologram.spawn(new Location(world,
                        getConfig().getDouble("hologram.x"),
                        getConfig().getDouble("hologram.y"),
                        getConfig().getDouble("hologram.z")));
            }
        }, 100L);
    }

    @Override
    public void onDisable() {
        if (replay != null) {
            replay.stop();
        }
    }

    public CarModel model() {
        return model;
    }

    public CarModel replayModel() {
        return replayModel;
    }

    /** Beside the submission plate: where a watcher lands after the replay. */
    public Location deskLocation() {
        World world = raceWorld();
        if (world == null || !getConfig().isConfigurationSection("kiosk.plate")) {
            return null;
        }
        return new Location(world,
                getConfig().getInt("kiosk.plate.x") + 0.5,
                getConfig().getInt("kiosk.plate.y") + 1.0,
                getConfig().getInt("kiosk.plate.z") + 2.5);
    }

    public World raceWorld() {
        return getServer().getWorld(getConfig().getString("world", "test"));
    }

    public Location startLocation() {
        return new Location(raceWorld(),
                getConfig().getDouble("start.x"),
                getConfig().getDouble("start.y"),
                getConfig().getDouble("start.z"),
                (float) getConfig().getDouble("start.yaw"), 0f);
    }

    /** A result came back from the sandbox. */
    private void onResult(Submission.Result result) {
        UUID player = result.uuid();
        Player online = getServer().getPlayer(player);
        if (!result.ok()) {
            queue.finish(player);
            String message = result.error == null ? "your run failed" : result.error;
            if (online != null) {
                online.sendMessage(Component.text("Race failed: " + message,
                        NamedTextColor.RED));
            }
            getLogger().info("Run failed for " + result.player_name + ": " + message);
            return;
        }
        replay.enqueue(result);
    }

    /** The replay finished (or was skipped) — record the time. */
    private void onRunFinished(Submission.Result result) {
        UUID player = result.uuid();
        queue.finish(player);
        boolean best = leaderboard.record(player, result.player_name, result.time_s);
        hologram.refresh();

        Component message = Component.text(
                String.format("%s finished in %.2fs", result.player_name, result.time_s),
                best ? NamedTextColor.GOLD : NamedTextColor.WHITE);
        if (best) {
            message = message.append(Component.text("  NEW BEST", NamedTextColor.GOLD));
        }
        getServer().broadcast(message);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        String sub = args.length == 0 ? "help" : args[0].toLowerCase();
        switch (sub) {
            case "submit":
                return submit(sender);
            case "top":
                return top(sender);
            case "status":
                return status(sender);
            case "admin":
                return admin(sender, args);
            default:
                sender.sendMessage(Component.text(
                        "/race submit | /race top | /race status", NamedTextColor.GRAY));
                return true;
        }
    }

    private boolean submit(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Players only.");
            return true;
        }
        submitHeldBook(player);
        return true;
    }

    /** Queue a player's code. Shared by /race submit and the kiosk. */
    public void submitHeldBook(Player player) {
        // A book page holds a couple of hundred characters, so long code goes
        // in the code box: every book in it, in slot order, is one program.
        List<ItemStack> books = new ArrayList<>();
        ItemStack held = player.getInventory().getItemInMainHand();
        if (held.getType() == Material.WRITABLE_BOOK
                || held.getType() == Material.WRITTEN_BOOK) {
            books.add(held);
        } else {
            books.addAll(codeBoxBooks());
        }
        if (books.isEmpty()) {
            player.sendMessage(Component.text(
                    "Hold a book with your code, or put your books in the code box.",
                    NamedTextColor.RED));
            return;
        }
        if (queue.hasInFlight(player.getUniqueId())) {
            player.sendMessage(Component.text("You already have a run in progress.",
                    NamedTextColor.RED));
            return;
        }
        long cooldown = queue.cooldownLeft(player.getUniqueId(),
                getConfig().getLong("submit.cooldown-seconds", 10));
        if (cooldown > 0) {
            player.sendMessage(Component.text("Wait " + cooldown + "s before submitting again.",
                    NamedTextColor.RED));
            return;
        }

        int pages = 0;
        StringBuilder builder = new StringBuilder();
        for (ItemStack book : books) {
            BookMeta meta = (BookMeta) book.getItemMeta();
            for (Component page : meta.pages()) {
                if (builder.length() > 0) {
                    builder.append('\n');
                }
                builder.append(PlainTextComponentSerializer.plainText().serialize(page));
                pages++;
            }
        }
        String code = builder.toString();
        int limit = getConfig().getInt("submit.max-code-bytes", 32768);
        if (code.isBlank()) {
            player.sendMessage(Component.text("That book is empty.", NamedTextColor.RED));
            return;
        }
        if (code.getBytes().length > limit) {
            player.sendMessage(Component.text("Your code is over " + limit + " bytes.",
                    NamedTextColor.RED));
            return;
        }

        try {
            queue.enqueue(player.getUniqueId(), player.getName(), code);
        } catch (Exception e) {
            player.sendMessage(Component.text("Could not queue your run: " + e.getMessage(),
                    NamedTextColor.RED));
            return;
        }
        player.sendMessage(Component.text(String.format(
                "Submitted %d characters from %d page%s. Simulating your lap...",
                code.length(), pages, pages == 1 ? "" : "s"), NamedTextColor.GREEN));
    }

    /** Books sitting in the configured code box, in slot order. */
    private List<ItemStack> codeBoxBooks() {
        List<ItemStack> books = new ArrayList<>();
        World world = raceWorld();
        if (world == null || !getConfig().isConfigurationSection("kiosk.code-box")) {
            return books;
        }
        Block block = new Location(world,
                getConfig().getInt("kiosk.code-box.x"),
                getConfig().getInt("kiosk.code-box.y"),
                getConfig().getInt("kiosk.code-box.z")).getBlock();
        if (block.getState() instanceof Container container) {
            for (ItemStack item : container.getInventory().getContents()) {
                if (item != null && (item.getType() == Material.WRITABLE_BOOK
                        || item.getType() == Material.WRITTEN_BOOK)) {
                    books.add(item);
                }
            }
        }
        return books;
    }

    private boolean top(CommandSender sender) {
        List<Leaderboard.Entry> ranking = leaderboard.ranking();
        if (ranking.isEmpty()) {
            sender.sendMessage(Component.text("No times yet.", NamedTextColor.GRAY));
            return true;
        }
        sender.sendMessage(Component.text("RACECAR LEADERBOARD", NamedTextColor.AQUA));
        for (int i = 0; i < Math.min(10, ranking.size()); i++) {
            Leaderboard.Entry entry = ranking.get(i);
            sender.sendMessage(Component.text(
                    String.format("%d. %s  %.2fs  (%d runs)",
                            i + 1, entry.name(), entry.bestSeconds(), entry.runs()),
                    i == 0 ? NamedTextColor.GOLD : NamedTextColor.WHITE));
        }
        return true;
    }

    private boolean status(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Players only.");
            return true;
        }
        String id = queue.idOf(player.getUniqueId());
        if (id == null) {
            sender.sendMessage(Component.text("Nothing in progress.", NamedTextColor.GRAY));
        } else if (replay.busy()) {
            sender.sendMessage(Component.text("A race is being replayed.", NamedTextColor.GRAY));
        } else {
            sender.sendMessage(Component.text("Your lap is being simulated.",
                    NamedTextColor.GRAY));
        }
        return true;
    }

    private boolean admin(CommandSender sender, String[] args) {
        if (!sender.hasPermission("race.admin")) {
            sender.sendMessage(Component.text("No permission.", NamedTextColor.RED));
            return true;
        }
        String action = args.length > 1 ? args[1].toLowerCase() : "";
        switch (action) {
            case "reload":
                reloadConfig();
                World world = raceWorld();
                if (world != null && getConfig().getBoolean("hologram.enabled", true)) {
                    hologram.spawn(new Location(world,
                            getConfig().getDouble("hologram.x"),
                            getConfig().getDouble("hologram.y"),
                            getConfig().getDouble("hologram.z")));
                }
                sender.sendMessage(Component.text("Reloaded.", NamedTextColor.GREEN));
                return true;
            case "clear":
                if (args.length < 3) {
                    sender.sendMessage(Component.text("/race admin clear <player|all>",
                            NamedTextColor.GRAY));
                    return true;
                }
                if (args[2].equalsIgnoreCase("all")) {
                    leaderboard.clearAll();
                } else {
                    Player target = getServer().getPlayer(args[2]);
                    if (target == null) {
                        sender.sendMessage(Component.text("Player not online.",
                                NamedTextColor.RED));
                        return true;
                    }
                    leaderboard.clear(target.getUniqueId());
                }
                hologram.refresh();
                sender.sendMessage(Component.text("Cleared.", NamedTextColor.GREEN));
                return true;
            case "cancel":
                if (sender instanceof Player player && queue.cancel(player.getUniqueId())) {
                    sender.sendMessage(Component.text("Cancelled.", NamedTextColor.GREEN));
                } else {
                    sender.sendMessage(Component.text("Nothing to cancel.",
                            NamedTextColor.GRAY));
                }
                return true;
            default:
                sender.sendMessage(Component.text(
                        "/race admin reload | clear <player|all> | cancel",
                        NamedTextColor.GRAY));
                return true;
        }
    }
}
