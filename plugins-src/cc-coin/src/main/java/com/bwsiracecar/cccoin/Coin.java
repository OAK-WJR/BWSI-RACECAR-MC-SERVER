package com.bwsiracecar.cccoin;

import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.BlockDisplay;
import org.bukkit.util.Transformation;
import org.joml.AxisAngle4f;
import org.joml.Vector3f;

import java.util.ArrayList;
import java.util.List;

/**
 * One CC Coin: an invisible base entity carrying the coin as block displays,
 * hovering just above the ground and slowly spinning in place.
 */
public class Coin {

    /** How far the coin floats above the block it was placed on. */
    private static final float HOVER = 0.3f;
    static final int INTERPOLATION_TICKS = 2;

    private final CoinModel model;
    private final ArmorStand base;
    private final List<BlockDisplay> parts = new ArrayList<>();

    private float yaw;

    public Coin(CoinModel model, Location spawn) {
        this.model = model;
        this.yaw = spawn.getYaw();

        World world = spawn.getWorld();
        base = world.spawn(spawn, ArmorStand.class, stand -> {
            stand.setInvisible(true);
            stand.setMarker(true);
            stand.setGravity(false);
            stand.setInvulnerable(true);
            stand.setPersistent(true);
        });

        for (CoinModel.Part part : model.parts()) {
            BlockDisplay display = world.spawn(spawn, BlockDisplay.class, d -> {
                d.setBlock(part.blockData());
                d.setPersistent(true);
                d.setInterpolationDuration(INTERPOLATION_TICKS);
            });
            parts.add(display);
            base.addPassenger(display);
        }
        applyTransforms();
    }

    /** Turn by the given angle and re-place every part. */
    public void spin(float degrees) {
        yaw = (yaw + degrees) % 360f;
        applyTransforms();
    }

    private void applyTransforms() {
        float radians = (float) Math.toRadians(-yaw);
        AxisAngle4f rotation = new AxisAngle4f(radians, 0f, 1f, 0f);
        float scale = (float) model.voxelMetres();

        List<CoinModel.Part> definitions = model.parts();
        for (int i = 0; i < parts.size(); i++) {
            CoinModel.Part part = definitions.get(i);
            BlockDisplay display = parts.get(i);

            // Corner of the part relative to the coin's vertical axis, with the
            // rim hovering just above the base entity.
            Vector3f corner = new Vector3f(
                    (part.x() - model.size()[0] / 2f) * scale,
                    part.y() * scale + HOVER,
                    (part.z() - model.size()[2] / 2f) * scale);
            corner.rotateY(radians);

            display.setInterpolationDelay(0);
            display.setTransformation(new Transformation(
                    corner,
                    rotation,
                    new Vector3f(part.w() * scale, part.h() * scale, part.d() * scale),
                    new AxisAngle4f(0f, 0f, 1f, 0f)));
        }
    }

    public boolean isValid() {
        return base.isValid();
    }

    public void remove() {
        for (BlockDisplay display : parts) {
            display.remove();
        }
        parts.clear();
        base.remove();
    }

    public void tag() {
        base.addScoreboardTag(CCCoinPlugin.TAG);
    }
}
