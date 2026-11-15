/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.vulkan;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Path;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class HdrScreenshotTest {
    @TempDir Path temporary;

    @Test
    void actualNativeImagePngRetainsColorsOrientationAndOpaqueAlpha() throws Exception {
        try (var image = HdrScreenshot.decode(pixels(), 2, 2, 1, SdrImageColor.SourceFrame.SDR)) {
            Path path = temporary.resolve("float-screenshot.png");
            image.writeToFile(path);
            var png = ImageIO.read(path.toFile());
            assertEquals(2, png.getWidth());
            assertEquals(2, png.getHeight());
            assertEquals(0xff0000ff, png.getRGB(0, 0));
            assertEquals(0xffffffff, png.getRGB(1, 0));
            assertEquals(0xffff0000, png.getRGB(0, 1));
            assertEquals(0xff00ff00, png.getRGB(1, 1));
        }
    }

    @Test
    void thumbnailDownscaleAveragesTheFullFloatPixels() {
        try (var image = HdrScreenshot.decode(pixels(), 2, 2, 2, SdrImageColor.SourceFrame.SDR)) {
            assertEquals(1, image.getWidth());
            assertEquals(1, image.getHeight());
            assertArrayEquals(new int[] { 0xffbcbcbc }, image.getPixelsABGR());
        }
    }

    private static ByteBuffer pixels() {
        var bytes = ByteBuffer.allocate(32).order(ByteOrder.nativeOrder());
        for (float[] rgb : new float[][] { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 }, { 1, 1, 1 } }) {
            for (float value : rgb) bytes.putShort(Float.floatToFloat16(value));
            bytes.putShort((short) 0); // Screen capture remains opaque even when the composition alpha is zero.
        }
        return bytes.flip();
    }
}
