/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors.
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.mixin;

import com.mojang.blaze3d.systems.RenderSystem;
import com.mojang.renderpearl.api.pipeline.CompiledRenderPipeline;
import com.mojang.renderpearl.api.pipeline.RenderPipeline;
import com.mojang.renderpearl.frontend.FrontendRenderPipeline;
import org.edtp.kavora.vulkan.FloatCompositionPipeline;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;

@Mixin(value = FrontendRenderPipeline.class, remap = false)
abstract class FrontendRenderPipelineMixin implements FloatCompositionPipeline.Access {
    @Unique private RenderPipeline kavora$compositionSource;
    @Unique private FloatCompositionPipeline kavora$variantDescriptor;
    @Unique private CompiledRenderPipeline kavora$variant;

    @Override
    public void kavora$setCompositionSource(RenderPipeline source) {
        kavora$compositionSource = source;
    }

    @Override
    public CompiledRenderPipeline kavora$floatCompositionVariant() {
        if (kavora$variant == null || kavora$variant.isClosed()) {
            if (kavora$variantDescriptor == null) {
                kavora$variantDescriptor = new FloatCompositionPipeline(kavora$compositionSource);
            }
            kavora$variant = RenderSystem.getCompiledPipeline(kavora$variantDescriptor);
        }
        return kavora$variant;
    }
}
