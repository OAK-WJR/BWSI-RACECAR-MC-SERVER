package com.bwsiracecar.race;

import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.entity.BlockDisplay;
import org.bukkit.util.Transformation;
import org.joml.AxisAngle4f;
import org.joml.Vector3f;

import java.util.ArrayList;
import java.util.List;

/**
 * The car used for replays: block displays only, no vehicle.
 *
 * The client interpolates a display entity's own teleports over
 * teleport_duration ticks, and that is the only movement it interpolates —
 * passengers dragged along by an armour stand snap. So every part sits at
 * the car's origin, places itself with its transformation, and is teleported
 * directly. This is the same architecture the display-based model engines
 * use.
 */
public class ReplayCar {

    /** The camera and /tp target: the first part carries this. */
    public static final String ROOT_TAG = "bwsi_race_replay";
    public static final String PART_TAG = "bwsi_race_replay_part";

    /**
     * Teleports land every STEP_TICKS; the client fills the gap. Every part
     * sends a packet per move, so this is also the throttle that makes a
     * full-detail model affordable.
     */
    public static final int STEP_TICKS = 3;

    private static final float YAW_EPSILON = 1.0f;

    /**
     * The voxel grid's nose sits at low z while a yaw of 0 travels towards
     * +z, so the body is turned around to face where it is going. Shared by
     * ModelCar, which is built from the same grid.
     */
    static final float MODEL_YAW = (float) Math.PI;

    private final CarModel model;
    private final double scaleMultiplier;
    private final List<BlockDisplay> parts = new ArrayList<>();

    private float yaw;
    private float renderedYaw = Float.NaN;

    public ReplayCar(CarModel model, Location spawn, double scaleMultiplier) {
        this.model = model;
        this.scaleMultiplier = scaleMultiplier;
        this.yaw = spawn.getYaw();

        World world = spawn.getWorld();
        boolean first = true;
        for (CarModel.Part part : model.parts()) {
            boolean root = first;
            first = false;
            BlockDisplay display = world.spawn(spawn, BlockDisplay.class, d -> {
                d.setBlock(part.blockData());
                d.setPersistent(true);
                d.setTeleportDuration(STEP_TICKS);
                d.setInterpolationDuration(STEP_TICKS);
                d.addScoreboardTag(PART_TAG);
                if (root) {
                    d.addScoreboardTag(ROOT_TAG);
                }
            });
            parts.add(display);
        }
        applyTransforms();
    }

    /**
     * Move the whole car to the next trajectory point. Call once every
     * STEP_TICKS; each display teleports itself and the client interpolates.
     */
    public void moveTo(Location target, float newYaw) {
        yaw = newYaw;
        // The entity's own rotation turns a display on top of its
        // transformation, so heading must live in exactly one of the two.
        // It lives in the transformation; teleports stay unrotated, or the
        // body spins twice as fast as the car does.
        Location destination = target.clone();
        destination.setYaw(0f);
        destination.setPitch(0f);
        for (BlockDisplay display : parts) {
            display.teleport(destination);
        }
        if (Math.abs(wrapDegrees(yaw - renderedYaw)) > YAW_EPSILON) {
            applyTransforms();
        }
    }

    /** Same maths as Car.applyTransforms: offsets live in the transformation. */
    private void applyTransforms() {
        float radians = (float) Math.toRadians(-yaw) + MODEL_YAW;
        AxisAngle4f rotation = new AxisAngle4f(radians, 0f, 1f, 0f);
        float scale = (float) (model.voxelMetres() * scaleMultiplier);

        List<CarModel.Part> definitions = model.parts();
        for (int i = 0; i < parts.size(); i++) {
            CarModel.Part part = definitions.get(i);
            BlockDisplay display = parts.get(i);

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

    private static float wrapDegrees(float degrees) {
        while (degrees <= -180f) {
            degrees += 360f;
        }
        while (degrees > 180f) {
            degrees -= 360f;
        }
        return degrees;
    }

    public boolean isValid() {
        return !parts.isEmpty() && parts.get(0).isValid();
    }

    public void remove() {
        for (BlockDisplay display : parts) {
            display.remove();
        }
        parts.clear();
    }
}
