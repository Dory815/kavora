/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors.
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.vulkan;

import com.mojang.renderpearl.api.GpuFormat;
import com.mojang.renderpearl.api.pipeline.ColorTargetState;
import com.mojang.renderpearl.api.pipeline.CompiledRenderPipeline;
import com.mojang.renderpearl.api.pipeline.RenderPipeline;
import com.mojang.renderpearl.api.vertex.VertexFormat;

/** Retargets a single-color host pipeline to the renderer's FP16 composition format. */
public final class FloatCompositionPipeline extends RenderPipeline {
    public interface Access {
        void kavora$setCompositionSource(RenderPipeline source);
        CompiledRenderPipeline kavora$floatCompositionVariant();
    }

    public FloatCompositionPipeline(RenderPipeline source) {
        super(source.getLocation(), source.getShaders(), source.getShaderDefines(), source.getBindGroupLayouts(),
                colorTarget(source.getColorTargetStates().getFirst()), source.getDepthStencilState(),
                source.getPolygonMode(), source.isCull(), source.getVertexFormatBindings().toArray(VertexFormat[]::new),
                source.getPrimitiveTopology(), source.pushConstantSize(), source.getSortKey());
    }

    private static ColorTargetState[] colorTarget(ColorTargetState original) {
        return new ColorTargetState[] {
                new ColorTargetState(original.blendFunction(), GpuFormat.RGBA16_FLOAT, original.writeMask())
        };
    }
}
