/* SPDX-License-Identifier: LGPL-3.0-only */
package org.edtp.kavora.horizon;

import it.unimi.dsi.fastutil.longs.LongArrayList;
import org.edtp.kavora.horizon.voxel.CoveredVolume;
import org.edtp.kavora.horizon.voxel.VoxelKey;
import org.edtp.kavora.sdk.MeshQuadSurface;

import java.nio.ByteBuffer;
import java.util.BitSet;

/** Consecutive quads with the same conservative section bounds share one coverage query. */
final class CoverageQuadRuns {
    private static final int FIELD_BITS = 6;
    private static final int FIELD_MASK = (1 << FIELD_BITS) - 1;
    private static final int FIELD_BIAS = 8;
    private static final int RANGE_BITS = FIELD_BITS * 6;
    private static final long UNKNOWN = (1L << RANGE_BITS) - 1;

    private CoverageQuadRuns() {}

    record Plan(BitSet removed, int removedQuads, boolean needsCoverage) {
        boolean keeps(Plan applied) {
            if (applied.removedQuads > removedQuads) return false;
            for (int run = applied.removed.nextSetBit(0); run >= 0; run = applied.removed.nextSetBit(run + 1)) {
                if (!removed.get(run)) return false;
            }
            return true;
        }

        short[] indices(long[] runs, int quadCount) {
            short[] indices = new short[quadCount - removedQuads];
            int quad = 0, output = 0;
            for (int run = 0; run < runs.length; run++) {
                int end = quad + quads(runs[run]);
                if (removed.get(run)) quad = end;
                else while (quad < end) indices[output++] = (short) quad++;
            }
            return indices;
        }
    }

    static long[] pack(long key, ByteBuffer vertices, int vertexCount) {
        var runs = new LongArrayList();
        int originX = VoxelKey.blockX(key), originY = VoxelKey.blockY(key), originZ = VoxelKey.blockZ(key);
        float magnitude = Math.max(VoxelKey.size(key), Math.max(Math.abs(originX), Math.max(Math.abs(originY), Math.abs(originZ))));
        double margin = 16 * Math.ulp(magnitude + VoxelKey.size(key));
        for (int first = 0; first < vertexCount; first += 4) {
            long bounds = bounds(vertices, first * MeshQuadSurface.VERTEX_STRIDE, margin);
            int last = runs.size() - 1;
            if (last >= 0 && (runs.getLong(last) & UNKNOWN) == bounds) {
                runs.set(last, runs.getLong(last) + (1L << RANGE_BITS));
            } else {
                runs.add(bounds | (1L << RANGE_BITS));
            }
        }
        return runs.toLongArray();
    }

    static Plan plan(long[] runs, CoveredVolume volume, int x, int y, int z) {
        BitSet removed = new BitSet();
        int removedQuads = 0;
        boolean needsCoverage = false;
        for (int i = 0; i < runs.length; i++) {
            long run = runs[i];
            if (!known(run)) {
                needsCoverage = true;
                continue;
            }
            int overlap = volume.classify(x + section(run, 0), y + section(run, 1), z + section(run, 2),
                    x + section(run, 3), y + section(run, 4), z + section(run, 5));
            if (overlap == CoveredVolume.FULL) {
                removed.set(i);
                removedQuads += quads(run);
            } else if (overlap == CoveredVolume.PARTIAL) needsCoverage = true;
        }
        return new Plan(removed, removedQuads, needsCoverage);
    }

    private static long bounds(ByteBuffer vertices, int first, double margin) {
        long bounds = 0;
        for (int axis = 0; axis < 3; axis++) {
            int offset = first + axis * Float.BYTES;
            float a = vertices.getFloat(offset);
            float b = vertices.getFloat(offset + MeshQuadSurface.VERTEX_STRIDE);
            float c = vertices.getFloat(offset + 2 * MeshQuadSurface.VERTEX_STRIDE);
            float d = vertices.getFloat(offset + 3 * MeshQuadSurface.VERTEX_STRIDE);
            int low = (int) Math.floor((Math.min(Math.min(a, b), Math.min(c, d)) - margin) / 16) + FIELD_BIAS;
            int high = (int) Math.floor((Math.max(Math.max(a, b), Math.max(c, d)) + margin) / 16) + FIELD_BIAS + 1;
            if (low < 0 || high > FIELD_MASK) return UNKNOWN;
            bounds |= (long) low << (axis * FIELD_BITS);
            bounds |= (long) high << ((axis + 3) * FIELD_BITS);
        }
        return bounds;
    }

    static int quads(long run) {
        return (int) (run >>> RANGE_BITS);
    }

    private static boolean known(long run) {
        return (run & UNKNOWN) != UNKNOWN;
    }

    private static int section(long run, int field) {
        return ((int) (run >>> (field * FIELD_BITS)) & FIELD_MASK) - FIELD_BIAS;
    }
}
