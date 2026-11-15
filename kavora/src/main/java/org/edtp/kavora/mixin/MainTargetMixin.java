/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.mixin;

import com.mojang.blaze3d.pipeline.MainTarget;
import com.mojang.renderpearl.api.GpuFormat;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/** Keep composition precision independent of the window's current output mode. */
@Mixin(value = MainTarget.class, remap = false)
abstract class MainTargetMixin {
    @ModifyArg(method = "<init>", at = @At(value = "INVOKE", target =
            "Lcom/mojang/blaze3d/pipeline/RenderTarget;<init>(Ljava/lang/String;Lcom/mojang/renderpearl/api/GpuFormat;Lcom/mojang/renderpearl/api/GpuFormat;)V"), index = 1)
    private static GpuFormat kavora$compositionFormat(GpuFormat format) {
        return GpuFormat.RGBA16_FLOAT;
    }
}
