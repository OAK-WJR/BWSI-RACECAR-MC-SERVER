package com.bwsiracecar.race;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.Display;
import org.bukkit.entity.Entity;
import org.bukkit.entity.TextDisplay;

import java.util.List;

/** The floating leaderboard in the lobby: one TextDisplay, rewritten in place. */
public class Hologram {

    public static final String TAG = "bwsi_race_board";

    private final Leaderboard leaderboard;
    private final int lines;
    private TextDisplay display;

    public Hologram(Leaderboard leaderboard, int lines) {
        this.leaderboard = leaderboard;
        this.lines = lines;
    }

    /** Removes boards left behind by an earlier run, then spawns a fresh one. */
    public void spawn(Location location) {
        World world = location.getWorld();
        for (Entity entity : world.getEntities()) {
            if (entity.getScoreboardTags().contains(TAG)) {
                entity.remove();
            }
        }
        display = world.spawn(location, TextDisplay.class, d -> {
            d.setBillboard(Display.Billboard.CENTER);
            d.setPersistent(true);
            d.setShadowed(true);
            d.addScoreboardTag(TAG);
        });
        refresh();
    }

    public void refresh() {
        if (display == null || !display.isValid()) {
            return;
        }
        Component text = Component.text("RACECAR LEADERBOARD", NamedTextColor.AQUA);
        List<Leaderboard.Entry> ranking = leaderboard.ranking();
        if (ranking.isEmpty()) {
            text = text.append(Component.text("\nno times yet - /race submit",
                    NamedTextColor.GRAY));
        }
        for (int i = 0; i < Math.min(lines, ranking.size()); i++) {
            Leaderboard.Entry entry = ranking.get(i);
            NamedTextColor colour = i == 0 ? NamedTextColor.GOLD : NamedTextColor.WHITE;
            text = text.append(Component.text(
                    String.format("%n%d. %s  %.2fs", i + 1, entry.name(), entry.bestSeconds()),
                    colour));
        }
        display.text(text);
    }

    public void remove() {
        if (display != null && display.isValid()) {
            display.remove();
        }
    }
}
