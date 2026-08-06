package com.bwsiracecar.race;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.NamespacedKey;
import org.bukkit.World;
import org.bukkit.entity.Display;
import org.bukkit.entity.ItemDisplay;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.ItemMeta;
import org.bukkit.util.Transformation;
import org.joml.AxisAngle4f;
import org.joml.Vector3f;

/**
 * The car as a single entity, drawn from the model in the resource pack.
 *
 * The voxel version needs one block display per cuboid — thousands of
 * entities, thousands of packets per move. A resource pack can carry the
 * whole shape as one item model, so the car becomes one item display that
 * interpolates its own teleports. Players who decline the pack see nothing
 * here, which is why ReplayCar is kept as the fallback.
 */
public class ModelCar {

    /** Item model key provided by the pack: assets/bwsi/items/racecar.json */
    public static final NamespacedKey MODEL_KEY =
            new NamespacedKey("bwsi", "racecar");

    /** Teleports land every STEP_TICKS; the client fills the gap. */
    public static final int STEP_TICKS = 2;

    private final ItemDisplay display;
    private final float scale;

    public ModelCar(Location spawn, double blocksLong) {
        // the model fills three blocks, so this is how many of those it takes
        this.scale = (float) (blocksLong / 3.0);

        ItemStack item = new ItemStack(Material.PAPER);
        ItemMeta meta = item.getItemMeta();
        meta.setItemModel(MODEL_KEY);
        item.setItemMeta(meta);

        World world = spawn.getWorld();
        display = world.spawn(spawn, ItemDisplay.class, d -> {
            d.setItemStack(item);
            d.setItemDisplayTransform(ItemDisplay.ItemDisplayTransform.HEAD);
            d.setBillboard(Display.Billboard.FIXED);
            d.setTeleportDuration(STEP_TICKS);
            d.setInterpolationDuration(STEP_TICKS);
            d.setPersistent(true);
            d.addScoreboardTag(ReplayCar.PART_TAG);
            d.addScoreboardTag(ReplayCar.ROOT_TAG);
        });
        apply(spawn.getYaw());
    }

    public void moveTo(Location target, float yaw) {
        Location destination = target.clone();
        destination.setYaw(0f);
        destination.setPitch(0f);
        display.teleport(destination);
        apply(yaw);
    }

    /** Heading and size live in the transformation, never in the entity yaw. */
    private void apply(float yaw) {
        float radians = (float) Math.toRadians(-yaw) + ReplayCar.MODEL_YAW;
        display.setInterpolationDelay(0);
        display.setTransformation(new Transformation(
                new Vector3f(0f, scale * 1.5f, 0f),
                new AxisAngle4f(radians, 0f, 1f, 0f),
                new Vector3f(scale * 3f, scale * 3f, scale * 3f),
                new AxisAngle4f(0f, 0f, 1f, 0f)));
    }

    public boolean isValid() {
        return display.isValid();
    }

    public void remove() {
        display.remove();
    }
}
