/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.asset;

import org.edtp.kavora.sdk.MeshQuadSurface;
import org.edtp.kavora.sdk.RemixAPI;
import org.edtp.kavora.util.DirectBufferPool;
import java.lang.ref.Reference;
import java.nio.ByteBuffer;

/** Static flat quads keep one shared attribute table and use the runtime's common quad indices. */
public final class KavoraQuadMesh extends KavoraMesh {
    private final KavoraMaterial material;
    private final int quads, materialCount;
    private final long bytes;
    private ByteBuffer vertices, attributes, materialIndices;

    public KavoraQuadMesh(KavoraMaterial material, int quads, int materialCount,
                         ByteBuffer vertices, ByteBuffer attributes, ByteBuffer materialIndices) {
        super(new KavoraMeshSurface[0]);
        this.material = material;
        this.quads = quads;
        this.materialCount = materialCount;
        this.vertices = vertices;
        this.attributes = attributes;
        this.materialIndices = materialIndices;
        bytes = (long) quads * MeshQuadSurface.RESIDENT_QUAD_BYTES
                + (long) materialCount * MeshQuadSurface.MATERIAL_STRIDE;
    }

    @Override
    protected long doCreate(RemixAPI api, long hash) {
        var surface = new MeshQuadSurface(material.getHandle(), vertices, attributes,
                quads, materialCount, materialIndices);
        try { return api.createQuadMesh(hash, surface); }
        finally { Reference.reachabilityFence(this); }
    }

    @Override
    protected void doDisposeData() {
        if (vertices != null) DirectBufferPool.release(vertices);
        if (attributes != null) DirectBufferPool.release(attributes);
        if (materialIndices != null) DirectBufferPool.release(materialIndices);
        vertices = attributes = materialIndices = null;
        super.doDisposeData();
    }

    @Override
    public long estimatedNativeBytes() {
        return bytes;
    }

    public KavoraMesh subset(short[] indices) {
        return new IndexSubset(getHandle(), indices);
    }

    private static final class IndexSubset extends KavoraMesh {
        private final long source;
        private final long bytes;
        private short[] indices;

        IndexSubset(long source, short[] indices) {
            super(new KavoraMeshSurface[0]);
            this.source = source;
            this.indices = indices;
            bytes = (long) indices.length * 6 * Short.BYTES;
        }

        @Override
        protected long doCreate(RemixAPI api, long hash) {
            return api.createQuadSubset(hash, source, indices);
        }

        @Override
        protected void doDisposeData() {
            indices = null;
            super.doDisposeData();
        }

        @Override
        public long estimatedNativeBytes() {
            return bytes;
        }
    }
}
