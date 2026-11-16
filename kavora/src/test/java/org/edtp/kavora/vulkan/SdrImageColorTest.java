/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.vulkan;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SdrImageColorTest {
    @Test
    void fp16ChannelsUseExtendedSrgbInsteadOfLinearScrgb() {
        var data = ByteBuffer.allocate(8).order(ByteOrder.nativeOrder());
        data.putShort(0, (short) 0x3800); // encoded 0.5
        data.putShort(2, (short) 0x3c00); // encoded 1.0
        data.putShort(4, (short) 0x4000); // encoded 2.0
        assertEquals(0.21404114048223255, SdrImageColor.linearHalf(data, 0), 1e-12);
        assertEquals(1, SdrImageColor.linearHalf(data, 2));
        assertEquals(4.953845751592042, SdrImageColor.linearHalf(data, 4), 1e-12);
    }

    @Test
    void sdrFramesRetainEveryEightBitLevelAndAbgrChannelOrder() {
        for (int level = 0; level <= 255; level++) {
            double encoded = Float.float16ToFloat(Float.floatToFloat16(level / 255f));
            double linear = SdrImageColor.srgbToLinear(encoded);
            assertEquals(0xff000000 | level, SdrImageColor.toAbgr(linear, 0, 0, SdrImageColor.SourceFrame.SDR));
            assertEquals(0xff000000 | (level << 8), SdrImageColor.toAbgr(0, linear, 0, SdrImageColor.SourceFrame.SDR));
            assertEquals(0xff000000 | (level << 16), SdrImageColor.toAbgr(0, 0, linear, SdrImageColor.SourceFrame.SDR));
        }
    }

    @Test
    void hdrExportAgreesWithNativeDisplayColorGoldenSamples() {
        var source = SdrImageColor.SourceFrame.parse("42 3 200 1000");
        // Produced by the C++ displaySrgbEncode(displaySdrShoulder(displaySrgbDecode(rgb), 5)) contract.
        assertEquals(0xff1362ff, export(2, .8, .2, source));
        assertEquals(0xfff1f1f1, export(1, 1, 1, source));
        assertEquals(0xff387aff, export(4, 2, 1, source));
        assertEquals(0xffbf800a, export(.04045, .5, .75, source));
    }

    @Test
    void sourceMetadataIsImmutableAndRejectsMalformedLuminance() {
        var hdr = SdrImageColor.SourceFrame.parse("82 3 200 1000");
        var menu = SdrImageColor.SourceFrame.parse("83 1 200 1000");
        assertTrue(hdr.hdrScene());
        assertFalse(menu.hdrScene());
        assertEquals(0xffffffff, export(1, 1, 1, menu));
        assertEquals(0xfff1f1f1, export(1, 1, 1, hdr));
        for (String invalid : new String[] { "", "42 3 200", "42 3 0 1000", "42 3 200 NaN", "42 3 200 100", "42 3 Infinity Infinity" }) {
            assertEquals(SdrImageColor.SourceFrame.SDR, SdrImageColor.SourceFrame.parse(invalid));
        }
    }

    @Test
    void invalidHalfValuesAreSanitizedAndDownsamplingUsesLinearLight() {
        for (double invalid : new double[] { -1, Double.NEGATIVE_INFINITY, Double.POSITIVE_INFINITY, Double.NaN }) {
            assertEquals(0, SdrImageColor.srgbToLinear(invalid));
        }
        double average = (SdrImageColor.srgbToLinear(0) + SdrImageColor.srgbToLinear(1)) * 0.5;
        assertEquals(0xffbcbcbc, SdrImageColor.toAbgr(average, average, average, SdrImageColor.SourceFrame.SDR));
        double bright = SdrImageColor.srgbToLinear(65504);
        assertEquals(0xffffffff, SdrImageColor.toAbgr(bright, bright, bright, SdrImageColor.SourceFrame.parse("1 3 200 1000")));
    }

    private static int export(double r, double g, double b, SdrImageColor.SourceFrame source) {
        return SdrImageColor.toAbgr(SdrImageColor.srgbToLinear(r), SdrImageColor.srgbToLinear(g), SdrImageColor.srgbToLinear(b), source);
    }
}
