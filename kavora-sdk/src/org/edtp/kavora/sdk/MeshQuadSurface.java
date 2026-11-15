/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.sdk;

import java.nio.ByteBuffer;

/**
 * Flat quads in cyclic winding order, with float3 positions and one uint32 material index per quad.
 * Each 40-byte material contains UV origin, S and T float2s, packed half2 bounds, color and axis.
 * All buffers must be direct, native order, and alive until the foreign call returns.
 */
public record MeshQuadSurface(long material, ByteBuffer vertices, ByteBuffer materials,
                              int quadCount, int materialCount, ByteBuffer materialIndices) {
    public static final int POSITION_STRIDE = 3 * Float.BYTES;
    public static final int MATERIAL_STRIDE = 40;
    /** Four float3 positions and one material index; the runtime discards the upload copy. */
    public static final int RESIDENT_QUAD_BYTES = 4 * POSITION_STRIDE + Integer.BYTES;
    public static final int MAX_QUADS = 16384;

    public MeshQuadSurface {
        if (quadCount < 1 || quadCount > MAX_QUADS || materialCount < 1 || materialCount > quadCount
                || vertices == null || !vertices.isDirect()
                || materials == null || !materials.isDirect()
                || vertices.remaining() != (long) quadCount * 4 * POSITION_STRIDE
                || materialIndices == null || !materialIndices.isDirect()
                || materialIndices.remaining() != (long) quadCount * Integer.BYTES
                || materials.remaining() != (long) materialCount * MATERIAL_STRIDE) {
            throw new IllegalArgumentException("Invalid quad surface buffers");
        }
    }
}
