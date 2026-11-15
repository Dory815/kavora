/* SPDX-License-Identifier: LGPL-3.0-only */
package org.edtp.kavora.horizon;

import org.edtp.kavora.horizon.voxel.CoveredVolume;
import org.edtp.kavora.horizon.voxel.VoxelKey;
import org.edtp.kavora.sdk.MeshQuadSurface;
import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;

import static org.junit.jupiter.api.Assertions.*;

class CoverageQuadRunsTest {
    @Test
    void coveredQuadsAreRemovedAndFringeQuadsKeepTheirOriginalIndices() {
        ByteBuffer vertices = ByteBuffer.allocate(4 * 4 * MeshQuadSurface.VERTEX_STRIDE);
        quad(vertices, 1, 2);
        quad(vertices, 3, 4);
        quad(vertices, 15.5f, 16.5f);
        quad(vertices, 17, 18);
        long[] runs = CoverageQuadRuns.pack(VoxelKey.of(0, -1, 0, 0), vertices.flip(), 16);

        CoveredVolume coverage = new CoveredVolume();
        coverage.update(ByteBuffer.wrap(new byte[] {1, 0}), 2, 1, 1);
        var left = CoverageQuadRuns.plan(runs, coverage, 0, 0, 0);
        assertEquals(2, left.removedQuads());
        assertTrue(left.needsCoverage());
        assertArrayEquals(new short[] {2, 3}, left.indices(runs, 4));

        coverage.update(ByteBuffer.wrap(new byte[] {0, 1}), 2, 1, 1);
        var right = CoverageQuadRuns.plan(runs, coverage, 0, 0, 0);
        assertFalse(right.keeps(left));
        assertArrayEquals(new short[] {0, 1, 2}, right.indices(runs, 4));

        coverage.update(ByteBuffer.wrap(new byte[] {1, 1}), 2, 1, 1);
        var both = CoverageQuadRuns.plan(runs, coverage, 0, 0, 0);
        assertTrue(both.keeps(left));
        assertTrue(both.keeps(right));
        assertEquals(4, both.removedQuads());
        assertFalse(both.needsCoverage());
    }

    private static void quad(ByteBuffer vertices, float x0, float x1) {
        vertices.putFloat(x0).putFloat(1).putFloat(3).putInt(0);
        vertices.putFloat(x1).putFloat(1).putFloat(3).putInt(0);
        vertices.putFloat(x1).putFloat(2).putFloat(3).putInt(0);
        vertices.putFloat(x0).putFloat(2).putFloat(3).putInt(0);
    }
}
