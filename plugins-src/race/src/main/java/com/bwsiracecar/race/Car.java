package com.bwsiracecar.race;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.entity.ArmorStand;
import org.bukkit.entity.BlockDisplay;
import org.bukkit.entity.Display;
import org.bukkit.entity.EntityType;
import org.bukkit.util.Transformation;
import org.bukkit.util.Vector;
import org.joml.AxisAngle4f;
import org.joml.Vector3f;

import java.util.ArrayList;
import java.util.List;

/**
 * One RACECAR: an invisible base entity carrying the body as block displays.
 *
 * The displays ride the base, so straight-line driving costs nothing — the
 * client moves passengers along with their vehicle. Only a change of heading
 * needs the parts re-transformed, and those updates are interpolated so the
 * turn still looks smooth.
 */
public class Car {

    /** Heading change that is worth re-transforming the whole body for. */
    private static final float YAW_EPSILON = 1.0f;
    private static final int INTERPOLATION_TICKS = 2;

    /** Body re-transforms are the expensive part, so they stay throttled;
     * the interpolation duration below hides the step. */

    /**
     * The model's nose points along +z, the same way a yaw of 0 travels, so
     * the body needs no extra turn. (It rendered backwards until a chase
     * camera made that obvious.)
     */
    private static final float MODEL_FLIP = 0f;

    private final CarModel model;
    private final ArmorStand base;
    private final List<BlockDisplay> parts = new ArrayList<>();

    private final double scaleMultiplier;

    private float yaw;
    private float renderedYaw = Float.NaN;
    private double speed;
    private int ticks;

    public Car(CarModel model, Location spawn) {
        this(model, spawn, 1.0);
    }

    public Car(CarModel model, Location spawn, double scaleMultiplier) {
        this.model = model;
        this.scaleMultiplier = scaleMultiplier;
        this.yaw = spawn.getYaw();

        World world = spawn.getWorld();
        base = world.spawn(spawn, ArmorStand.class, stand -> {
            stand.setInvisible(true);
            stand.setMarker(true);
            stand.setGravity(false);
            stand.setInvulnerable(true);
            stand.setPersistent(true);
        });

        for (CarModel.Part part : model.parts()) {
            BlockDisplay display = world.spawn(spawn, BlockDisplay.class, d -> {
                d.setBlock(part.blockData());
                d.setPersistent(true);
                d.setInterpolationDuration(INTERPOLATION_TICKS);
                d.setTeleportDuration(INTERPOLATION_TICKS);
            });
            parts.add(display);
            base.addPassenger(display);
        }
        applyTransforms();
    }

    /** Re-place every part for the current heading. */
    private void applyTransforms() {
        float radians = (float) Math.toRadians(-yaw) + MODEL_FLIP;
        AxisAngle4f rotation = new AxisAngle4f(radians, 0f, 1f, 0f);
        float scale = (float) (model.voxelMetres() * scaleMultiplier);

        List<CarModel.Part> definitions = model.parts();
        for (int i = 0; i < parts.size(); i++) {
            CarModel.Part part = definitions.get(i);
            BlockDisplay display = parts.get(i);

            // Corner of the part relative to the middle of the car footprint,
            // with y=0 sitting on the ground.
            Vector3f corner = new Vector3f(
                    (part.x() - model.size()[0] / 2f) * scale,
                    part.y() * scale,
                    (part.z() - model.size()[2] / 2f) * scale);
            corner.rotateY(radians);

            display.setInterpolationDelay(0);
            display.setTransformation(new Transformation(
                    corner,
                    rotation,
                    new Vector3f(part.w() * scale, part.h() * scale, part.d() * scale),
                    new AxisAngle4f(0f, 0f, 1f, 0f)));
        }
        renderedYaw = yaw;
    }

    /**
     * Move the car to the next replayed trajectory point. Bypasses tick()
     * physics: the simulator already decided where the car goes.
     *
     * Teleporting is the only thing that moves it: an armour stand with
     * gravity off ignores velocity entirely, so the clever-looking version
     * of this that set velocity instead simply left the car standing still
     * between resyncs. Clients interpolate entity teleports, and passengers
     * ride along, so one teleport per tick is what smooth looks like here.
     */
    public void setPose(Location target, float newYaw) {
        yaw = newYaw;
        base.teleport(target);
        if (++ticks % INTERPOLATION_TICKS == 0
                && Math.abs(wrapDegrees(yaw - renderedYaw)) > YAW_EPSILON) {
            applyTransforms();
        }
    }

    private static float wrapDegrees(float degrees) {
        while (degrees <= -180f) {
            degrees += 360f;
        }
        while (degrees > 180f) {
            degrees -= 360f;
        }
        return degrees;
    }

    public void steerTowards(float targetYaw, float maxTurn) {
        float delta = targetYaw - yaw;
        while (delta <= -180f) {
            delta += 360f;
        }
        while (delta > 180f) {
            delta -= 360f;
        }
        yaw += Math.max(-maxTurn, Math.min(maxTurn, delta));
    }

    public void setSpeed(double speed) {
        this.speed = speed;
    }

    public double speed() {
        return speed;
    }

    /** Advance one tick. Returns false once the car no longer exists. */
    public boolean tick() {
        if (!base.isValid()) {
            return false;
        }
        if (speed != 0) {
            Location location = base.getLocation();
            double radians = Math.toRadians(yaw);
            Vector step = new Vector(-Math.sin(radians), 0, Math.cos(radians)).multiply(speed);
            Location target = location.clone().add(step);

            if (isBlocked(target)) {
                Location stepUp = target.clone().add(0, 1, 0);
                if (isBlocked(stepUp)) {
                    speed = 0;
                } else {
                    target = stepUp;
                }
            }
            while (target.getY() > target.getWorld().getMinHeight()
                    && !isBlocked(target.clone().add(0, -0.2, 0))) {
                target.add(0, -0.2, 0);
            }
            if (speed != 0) {
                base.teleport(target);
            }
        }
        // With thousands of parts, retransforming every tick would flood the
        // client; every INTERPOLATION_TICKS is enough, interpolation hides it.
        if (++ticks % INTERPOLATION_TICKS == 0
                && Math.abs(yaw - renderedYaw) > YAW_EPSILON) {
            applyTransforms();
        }
        return true;
    }

    private boolean isBlocked(Location location) {
        Material material = location.getBlock().getType();
        return material.isSolid();
    }

    public Location location() {
        return base.getLocation();
    }

    public void remove() {
        for (BlockDisplay display : parts) {
            display.remove();
        }
        parts.clear();
        base.remove();
    }

    public static boolean isCarBase(org.bukkit.entity.Entity entity) {
        return entity.getType() == EntityType.ARMOR_STAND
                && entity.getScoreboardTags().contains(RacePlugin.CAR_TAG);
    }

    public void tag() {
        base.addScoreboardTag(RacePlugin.CAR_TAG);
    }

    /** The entity the parts ride, for extra tagging by the replay. */
    public ArmorStand baseEntity() {
        return base;
    }
}
