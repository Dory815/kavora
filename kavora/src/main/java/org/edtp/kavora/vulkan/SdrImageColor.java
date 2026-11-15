/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.vulkan;

import java.nio.ByteBuffer;

/** SDR image export from the presenter's extended-sRGB composition contract. */
final class SdrImageColor {
    private SdrImageColor() {}

    record SourceFrame(long frameIndex, int flags, double paperWhiteNits, double peakNits) {
        static final SourceFrame SDR = new SourceFrame(0, 0, 80, 80);

        static SourceFrame parse(String value) {
            if (value == null || value.isBlank()) return SDR;
            String[] fields = value.strip().split("\\s+");
            if (fields.length != 4) return SDR;
            try {
                long frame = Long.parseUnsignedLong(fields[0]);
                int flags = Integer.parseUnsignedInt(fields[1]);
                double white = Double.parseDouble(fields[2]);
                double peak = Double.parseDouble(fields[3]);
                if (!Double.isFinite(white) || !Double.isFinite(peak) || white <= 0 || peak < white) return SDR;
                return new SourceFrame(frame, flags, white, peak);
            } catch (NumberFormatException invalid) {
                return SDR;
            }
        }

        boolean hdrScene() { return (flags & 3) == 3; }
    }

    static double linearHalf(ByteBuffer bytes, int offset) {
        return srgbToLinear(Float.float16ToFloat(bytes.getShort(offset)));
    }

    static double srgbToLinear(double encoded) {
        // Negative/out-of-gamut values and invalid shader results cannot be represented in an SDR PNG.
        if (!Double.isFinite(encoded) || encoded <= 0) return 0;
        return encoded <= 0.04045 ? encoded / 12.92 : Math.pow((encoded + 0.055) / 1.055, 2.4);
    }

    static int toAbgr(double red, double green, double blue, SourceFrame source) {
        if (source.hdrScene()) {
            // Match displaySdrShoulder in dxvk_display_color.h: one scale preserves RGB ratios.
            double maximum = Math.max(red, Math.max(green, blue));
            if (maximum > 0.75) {
                double peak = Math.max(source.peakNits() / source.paperWhiteNits(), 1);
                double curve = 4 - 1 / (peak - 0.75);
                double mapped = Math.min(0.75 + 1 / (1 / (maximum - 0.75) + curve), 1);
                red = red / maximum * mapped;
                green = green / maximum * mapped;
                blue = blue / maximum * mapped;
            }
        }
        return 0xff000000 | (channel(blue) << 16) | (channel(green) << 8) | channel(red);
    }

    private static int channel(double linear) {
        double encoded = linear <= 0.0031308 ? 12.92 * linear : 1.055 * Math.pow(linear, 1 / 2.4) - 0.055;
        return (int) Math.round(Math.clamp(encoded, 0, 1) * 255);
    }
}
