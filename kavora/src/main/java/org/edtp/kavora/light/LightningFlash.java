/* SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors.
 * SPDX-License-Identifier: Apache-2.0 */
package org.edtp.kavora.light;

import net.minecraft.util.Mth;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.LightningBolt;
import org.edtp.kavora.render.RenderOrigin;
import org.edtp.kavora.sdk.LightInfo;
import org.edtp.kavora.sdk.LightInfoCylinderEXT;

/** Approximates the lower part of the visible bolt with one finite, world-space emitter. */
final class LightningFlash {
    private static final int TRUNK_SEGMENTS = 8;
    private static final float SEGMENT_HEIGHT = 16.0f;
    private static final float GROUND_CLEARANCE = 0.25f;
    private static final float RADIUS = 0.25f;
    private static final float PEAK_RADIANCE = 150.0f;

    private LightningFlash() {}

    static LightInfo light(LightningBolt bolt, float partialTick, RenderOrigin origin) {
        // Vanilla raises its sky flash while life is non-negative, including on restrikes.
        float pulse = Mth.clamp((bolt.life + 1.0f - partialTick) * 0.5f, 0.0f, 1.0f);
        if (pulse <= 0.0f) return null;

        // Vanilla draws its trunk from the top down and anchors the last point at the strike.
        // Its last two random draws give the offset back from the base to the first joint.
        RandomSource random = RandomSource.createThreadLocalInstance(bolt.seed);
        for (int i = 1; i < TRUNK_SEGMENTS; i++) {
            random.nextInt(11);
            random.nextInt(11);
        }
        float dx = 5 - random.nextInt(11);
        float dz = 5 - random.nextInt(11);
        float length = Mth.sqrt(dx * dx + SEGMENT_HEIGHT * SEGMENT_HEIGHT + dz * dz);
        float start = GROUND_CLEARANCE / SEGMENT_HEIGHT;
        float radiance = PEAK_RADIANCE * pulse;
        return LightInfo.builder()
                .radiance(radiance * 0.82f, radiance * 0.90f, radiance)
                .cylinderExt(LightInfoCylinderEXT.builder()
                        .position(origin.localX(bolt.getX() + start * dx),
                                (float) (bolt.getY() + GROUND_CLEARANCE), origin.localZ(bolt.getZ() + start * dz))
                        .radius(RADIUS)
                        .axis(dx / length, SEGMENT_HEIGHT / length, dz / length)
                        .axisLength(length * (1.0f - start))
                        .volumetricRadianceScale(0.35f)
                        .build())
                .build();
    }
}
