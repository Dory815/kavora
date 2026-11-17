/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.sky;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SkyAtmosphereTest {
    private static final float SUN_RADIUS = (float) Math.toRadians(.265);

    @Test void diskTransmissionMatchesIndependentAdaptiveQuadrature() {
        // Adaptive path quadrature and 128-point disk integration, without a lookup table.
        assertTransmission(2, 60, .9207109610, .8570936435, .7156180758);
        assertTransmission(2, .0283, .02193846213, .002611557152, .00001282401320);
        assertTransmission(2, -.2, .01060610963, .001049436764, .000003261511108);
        assertTransmission(10000, -2, .2691253128, .04941269280, .0007506036597);
    }

    @Test void overheadTransmissionMatchesAnalyticExponentialDensity() {
        float[] transmission = SkyAtmosphere.transmittanceToLight(2, 1, SUN_RADIUS);
        double rayleighColumn = 8 * (Math.exp(-.002 / 8) - Math.exp(-100.0 / 8));
        double mieColumn = 1.2 * (Math.exp(-.002 / 1.2) - Math.exp(-100.0 / 1.2));
        double[] coefficients = {.005802, .013558, .0331};
        for (int channel = 0; channel < 3; channel++) {
            assertEquals(Math.exp(-coefficients[channel] * rayleighColumn - .021 * mieColumn),
                    transmission[channel], .0001);
        }
    }

    @Test void airAttenuationVariesContinuouslyAcrossSeaLevelTangent() {
        float below = (float) Math.sin(Math.toRadians(-1));
        float[] fromSeaLevel = SkyAtmosphere.transmittanceToLight(2, below, SUN_RADIUS);
        float[] fromMountain = SkyAtmosphere.transmittanceToLight(2000, below, SUN_RADIUS);
        assertTrue(fromMountain[0] > fromSeaLevel[0] && fromSeaLevel[0] > 0);
        float tangent = (float) -Math.sqrt(.002 * (2 * 6371 + .002)) / 6371.002f;
        float[] above = SkyAtmosphere.transmittanceToLight(2, tangent + 1e-7f, 0);
        float[] under = SkyAtmosphere.transmittanceToLight(2, tangent - 1e-7f, 0);
        for (int channel = 0; channel < 3; channel++) {
            assertTrue(under[channel] > 0);
            assertEquals(above[channel], under[channel], above[channel] * .0001);
        }
        float[] centred = SkyAtmosphere.transmittanceToLight(0, 0, SUN_RADIUS);
        assertTrue(centred[0] > centred[1] && centred[1] > centred[2] && centred[2] > 0);
    }

    @Test void sunsetProfileKeepsIlluminatedHighCloudsAboveTheDarkLowLayer() {
        float[] profile = new float[16];
        float[] altitudes = {400, 1900, 6000, 6800};
        float[] source = {30, 30, 30};
        float cosine = (float) Math.sin(Math.toRadians(-2));
        SkyAtmosphere.radianceProfile(profile, altitudes, 63, source, cosine, SUN_RADIUS);
        assertTrue(profile[0] < 1e-6f, "The low cloud base is in atmospheric shadow");
        assertTrue(profile[8] > 1f, "High cloud illumination survives surface-light extinction");
        assertTrue(profile[12] > profile[8] && profile[8] > profile[4]);
        for (int sample = 0; sample < 4; sample++) {
            float[] transmission = SkyAtmosphere.transmittanceToLight(altitudes[sample] - 63, cosine, SUN_RADIUS);
            assertEquals(altitudes[sample], profile[sample * 4 + 3]);
            for (int channel = 0; channel < 3; channel++) {
                assertEquals(transmission[channel] * source[channel], profile[sample * 4 + channel]);
            }
        }
        assertTrue(profile[12] > profile[13] && profile[13] > profile[14]);
    }

    @Test void cloudProfileUsesSeaLevelAsDensityReferenceAndReusesItsOutput() {
        float[] output = new float[16];
        float[] heights = {400, 1900, 6000, 6800};
        SkyAtmosphere.radianceProfile(output, heights, 0, new float[]{2, 3, 4}, 1, SUN_RADIUS);
        float[] original = output.clone();
        SkyAtmosphere.radianceProfile(output, new float[]{500, 2000, 6100, 6900}, 100,
                new float[]{2, 3, 4}, 1, SUN_RADIUS);
        for (int sample = 0; sample < 4; sample++) {
            for (int channel = 0; channel < 3; channel++) {
                assertEquals(original[sample * 4 + channel], output[sample * 4 + channel]);
            }
        }
        SkyAtmosphere.radianceProfile(output, heights, 0, new float[]{2, 3, 4}, -1, SUN_RADIUS);
        for (int sample = 0; sample < 4; sample++) {
            for (int channel = 0; channel < 3; channel++) assertEquals(0, output[sample * 4 + channel]);
        }
    }

    private static void assertTransmission(float height, double elevation, double... expected) {
        float[] actual = SkyAtmosphere.transmittanceToLight(height,
                (float) Math.sin(Math.toRadians(elevation)), SUN_RADIUS);
        for (int channel = 0; channel < 3; channel++) {
            assertEquals(expected[channel], actual[channel], expected[channel] * .005,
                    "height=" + height + ", elevation=" + elevation + ", channel=" + channel);
        }
    }
}
