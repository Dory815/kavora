/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.vulkan;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.platform.NativeImage;
import com.mojang.blaze3d.systems.RenderSystem;
import com.mojang.renderpearl.api.buffers.GpuBuffer;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.function.Consumer;
import org.edtp.kavora.NativeRuntime;

/** Float readback only; Minecraft retains screenshot filenames, notifications and asynchronous PNG saving. */
public final class HdrScreenshot {
    private HdrScreenshot() {}

    public static void capture(RenderTarget target, int downscale, Consumer<NativeImage> consumer) {
        var texture = target.getColorTexture();
        int width = target.width;
        int height = target.height;
        if (downscale <= 0 || width % downscale != 0 || height % downscale != 0) {
            throw new IllegalArgumentException("Image size is not divisible by downscale factor");
        }
        // Capture the source frame, not the current window mode; the readback can complete after a display change.
        var source = sourceFrame();
        var gpu = RenderSystem.getDevice();
        var buffer = gpu.createBuffer(() -> "Kavora float screenshot", GpuBuffer.USAGE_MAP_READ | GpuBuffer.USAGE_COPY_DST,
                (long) width * height * texture.getFormat().blockSize());
        try {
            gpu.createCommandEncoder().copyTextureToBuffer(texture, buffer, 0,
                    () -> finish(buffer, width, height, downscale, source, consumer), 0);
        } catch (RuntimeException | Error failure) {
            buffer.close();
            throw failure;
        }
    }

    private static SdrImageColor.SourceFrame sourceFrame() {
        if (!NativeRuntime.isStarted()) return SdrImageColor.SourceFrame.SDR;
        try {
            return SdrImageColor.SourceFrame.parse(NativeRuntime.api().getConfigVariableResolved("rtx.display.status.sourceFrame"));
        } catch (RuntimeException unavailable) {
            return SdrImageColor.SourceFrame.SDR;
        }
    }

    private static void finish(GpuBuffer buffer, int width, int height, int downscale,
                               SdrImageColor.SourceFrame source, Consumer<NativeImage> consumer) {
        NativeImage image = null;
        try (buffer; var mapped = buffer.map(true, false)) {
            image = decode(mapped.data().order(ByteOrder.nativeOrder()), width, height, downscale, source);
        } catch (RuntimeException | Error failure) {
            if (image != null) image.close();
            throw failure;
        }
        try {
            consumer.accept(image);
        } catch (RuntimeException | Error failure) {
            image.close();
            throw failure;
        }
    }

    static NativeImage decode(ByteBuffer bytes, int width, int height, int downscale, SdrImageColor.SourceFrame source) {
        NativeImage image = null;
        try {
            int outputWidth = width / downscale;
            int outputHeight = height / downscale;
            image = new NativeImage(outputWidth, outputHeight, false);
            double weight = 1.0 / ((double) downscale * downscale);
            for (int y = 0; y < outputHeight; y++) {
                for (int x = 0; x < outputWidth; x++) {
                    double red = 0, green = 0, blue = 0;
                    for (int dy = 0; dy < downscale; dy++) {
                        for (int dx = 0; dx < downscale; dx++) {
                            int offset = ((y * downscale + dy) * width + x * downscale + dx) * 8;
                            red += SdrImageColor.linearHalf(bytes, offset);
                            green += SdrImageColor.linearHalf(bytes, offset + 2);
                            blue += SdrImageColor.linearHalf(bytes, offset + 4);
                        }
                    }
                    image.setPixelABGR(x, outputHeight - y - 1,
                            SdrImageColor.toAbgr(red * weight, green * weight, blue * weight, source));
                }
            }
            return image;
        } catch (RuntimeException | Error failure) {
            if (image != null) image.close();
            throw failure;
        }
    }
}
