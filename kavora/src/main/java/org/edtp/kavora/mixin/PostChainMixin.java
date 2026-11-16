/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.mixin;

import com.mojang.renderpearl.api.GpuFormat;
import net.minecraft.client.renderer.PostChain;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/** The same descriptor supplies both transient and persistent post-processing targets. */
@Mixin(value = PostChain.class, remap = false)
abstract class PostChainMixin {
    @ModifyArg(method = "addToFrame", at = @At(value = "INVOKE", target =
            "Lcom/mojang/blaze3d/resource/RenderTargetDescriptor$TextureProperties;<init>(Lorg/joml/Vector4fc;Lcom/mojang/renderpearl/api/GpuFormat;)V"), index = 1)
    private static GpuFormat kavora$compositionFormat(GpuFormat format) {
        return GpuFormat.RGBA16_FLOAT;
    }
}
