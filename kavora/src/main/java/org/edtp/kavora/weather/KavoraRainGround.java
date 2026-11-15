/* SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors.
 * SPDX-License-Identifier: Apache-2.0 */
package org.edtp.kavora.weather;

import java.lang.ref.WeakReference;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Arrays;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.core.QuartPos;
import net.minecraft.util.Mth;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.phys.Vec3;
import org.edtp.kavora.sdk.RainGroundFrame;

/** Render-thread snapshot of the columns that receive liquid precipitation. */
public final class KavoraRainGround {
    private static final int SIZE = RainGroundFrame.GRID_SIZE;
    private static final int CHUNKS = SIZE / 16;
    private static final int DRY = Integer.MAX_VALUE;
    private static final Heightmap.Types PRECIPITATION_HEIGHT = Heightmap.Types.MOTION_BLOCKING;
    private static boolean enabled = true;

    private final RainGroundFrame frame = new RainGroundFrame();
    private final ChunkColumns[] cache = new ChunkColumns[CHUNKS * CHUNKS];
    private final BlockPos.MutableBlockPos sample = new BlockPos.MutableBlockPos();
    private ByteBuffer columns;
    private ClientLevel level;
    private long lastScan = Long.MIN_VALUE;
    private boolean dirty;

    private record ChunkColumns(WeakReference<LevelChunk> chunk, int x, int z, long[] heights, long[] skyHeights) {}

    public static void setEnabled(boolean value) {
        enabled = value;
    }

    public RainGroundFrame capture(ClientLevel world, Vec3 cameraPosition, float partialTick) {
        if (world != level) reset(world);
        float rain = enabled && world.dimensionType().hasSkyLight() ? world.getRainLevel(partialTick) : 0;
        if (rain <= 0) {
            lastScan = Long.MIN_VALUE;
            return null;
        }
        if (columns == null) columns = ByteBuffer.allocateDirect(RainGroundFrame.GRID_BYTES).order(ByteOrder.nativeOrder());
        int chunkX = (Mth.floor(cameraPosition.x) >> 4) - CHUNKS / 2;
        int chunkZ = (Mth.floor(cameraPosition.z) >> 4) - CHUNKS / 2;
        long tick = world.getGameTime();
        if (tick != lastScan || frame.originX != (chunkX << 4) || frame.originZ != (chunkZ << 4)) {
            updateColumns(world, chunkX, chunkZ);
            lastScan = tick;
        }
        frame.originX = chunkX << 4;
        frame.originZ = chunkZ << 4;
        frame.rain = rain;
        frame.columns = dirty ? columns : null;
        return frame;
    }

    public void submitted() {
        dirty = false;
        frame.columns = null;
    }

    public void reset() {
        reset(null);
    }

    private void reset(ClientLevel world) {
        Arrays.fill(cache, null);
        level = world;
        lastScan = Long.MIN_VALUE;
        dirty = true;
        frame.columns = null;
    }

    private void updateColumns(ClientLevel world, int chunkX, int chunkZ) {
        for (int z = chunkZ; z < chunkZ + CHUNKS; z++) {
            for (int x = chunkX; x < chunkX + CHUNKS; x++) {
                int index = (z & (CHUNKS - 1)) * CHUNKS + (x & (CHUNKS - 1));
                LevelChunk chunk = world.getChunkSource().getChunk(x, z, false);
                Heightmap heightmap = chunk != null && chunk.hasPrimedHeightmap(PRECIPITATION_HEIGHT)
                        ? chunk.getOrCreateHeightmapUnprimed(PRECIPITATION_HEIGHT) : null;
                Heightmap skyHeightmap = chunk != null && chunk.hasPrimedHeightmap(Heightmap.Types.WORLD_SURFACE)
                        ? chunk.getOrCreateHeightmapUnprimed(Heightmap.Types.WORLD_SURFACE) : null;
                long[] heights = heightmap == null ? null : heightmap.getRawData();
                long[] skyHeights = skyHeightmap == null ? null : skyHeightmap.getRawData();
                ChunkColumns previous = cache[index];
                if (previous != null && previous.chunk().get() == chunk && previous.x() == x && previous.z() == z
                        && Arrays.equals(previous.heights(), heights) && Arrays.equals(previous.skyHeights(), skyHeights)) continue;
                writeChunk(world, heightmap == null ? null : chunk, heightmap, x << 4, z << 4);
                cache[index] = new ChunkColumns(new WeakReference<>(chunk), x, z,
                        heights == null ? null : heights.clone(), skyHeights == null ? null : skyHeights.clone());
                dirty = true;
            }
        }
    }

    private void writeChunk(ClientLevel world, LevelChunk chunk, Heightmap heights, int startX, int startZ) {
        for (int z = 0; z < 16; z++) {
            int worldZ = startZ + z;
            int row = (worldZ & (SIZE - 1)) * SIZE;
            for (int x = 0; x < 16; x++) {
                int worldX = startX + x;
                int exposureY = DRY;
                if (chunk != null) {
                    int y = Math.max(heights.getFirstAvailable(x, z), chunk.getSkyLightSources().getLowestSourceY(x, z));
                    sample.set(worldX, y, worldZ);
                    Biome biome = chunk.getNoiseBiome(QuartPos.fromBlock(worldX), QuartPos.fromBlock(y), QuartPos.fromBlock(worldZ)).value();
                    if (biome.getPrecipitationAt(sample, world.getSeaLevel()) == Biome.Precipitation.RAIN) exposureY = y;
                }
                columns.putInt((row + (worldX & (SIZE - 1))) * Integer.BYTES, exposureY);
            }
        }
    }
}
