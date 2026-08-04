package com.bwsiracecar.race;

import com.google.gson.Gson;
import com.google.gson.annotations.SerializedName;
import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.block.data.BlockData;

import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * The voxelised car, produced offline by scripts/voxelize_glb.py from a scan of
 * the real RACECAR and merged into cuboids by scripts/voxels_to_parts.py.
 */
public class CarModel {

    public record Part(int x, int y, int z, int w, int h, int d, BlockData blockData) {}

    private static final class RawPart {
        int x, y, z, w, h, d;
        String block;
    }

    private static final class Raw {
        int[] size;
        @SerializedName("voxel_metres")
        double voxelMetres;
        List<RawPart> parts;
    }

    private final int[] size;
    private final double voxelMetres;
    private final List<Part> parts;

    private CarModel(int[] size, double voxelMetres, List<Part> parts) {
        this.size = size;
        this.voxelMetres = voxelMetres;
        this.parts = parts;
    }

    public static CarModel load(InputStream stream) {
        Raw raw = new Gson().fromJson(
                new InputStreamReader(stream, StandardCharsets.UTF_8), Raw.class);
        List<Part> parts = new ArrayList<>(raw.parts.size());
        for (RawPart rawPart : raw.parts) {
            Material material = Material.matchMaterial(rawPart.block);
            BlockData data = Bukkit.createBlockData(
                    material == null ? Material.GRAY_CONCRETE : material);
            parts.add(new Part(rawPart.x, rawPart.y, rawPart.z,
                    rawPart.w, rawPart.h, rawPart.d, data));
        }
        return new CarModel(raw.size, raw.voxelMetres, parts);
    }

    public int[] size() {
        return size;
    }

    public double voxelMetres() {
        return voxelMetres;
    }

    public List<Part> parts() {
        return parts;
    }

    public double lengthMetres() {
        return size[2] * voxelMetres;
    }
}
