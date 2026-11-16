/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.mixin;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.renderpearl.api.GpuFormat;
import java.util.function.Consumer;
import net.minecraft.client.Screenshot;
import org.edtp.kavora.vulkan.HdrScreenshot;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(value = Screenshot.class, remap = false)
abstract class ScreenshotMixin {
    @Inject(method = "takeScreenshot(Lcom/mojang/blaze3d/pipeline/RenderTarget;ILjava/util/function/Consumer;)V",
            at = @At("HEAD"), cancellable = true)
    private static void kavora$readFloatColor(RenderTarget target, int downscale, Consumer<NativeImage> consumer,
                                             CallbackInfo ci) {
        if (target.getColorTexture() != null && target.getColorTexture().getFormat() == GpuFormat.RGBA16_FLOAT) {
            HdrScreenshot.capture(target, downscale, consumer);
            ci.cancel();
        }
    }
}
