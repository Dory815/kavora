/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0 */
package org.edtp.kavora.sdk;

import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import static java.lang.foreign.ValueLayout.*;

/** Exercises profile ownership and pNext marshalling without loading a renderer. */
public final class CloudRadianceProfileContractTest {
    public static void main(String[] args) {
        float[] samples = {1, 2, 3, 400, 4, 5, 6, 1900, 7, 8, 9, 6000, 10, 11, 12, 6800};
        float[] expected = samples.clone();
        long extension = RemixBridge.allocDistantLightChain(0, -1, 0, .5f, 1, 0,
                new Float3D(7, 8, 9), samples);
        try (Arena scope = Arena.ofConfined()) {
            MemorySegment distant = MemorySegment.ofAddress(extension).reinterpret(40, scope, null);
            require(distant.get(JAVA_INT, 0) == StructType.LIGHT_INFO_DISTANT_EXT, "Distant extension type");
            MemorySegment constant = distant.get(ADDRESS, 8).reinterpret(32, scope, null);
            require(constant.get(JAVA_INT, 0) == StructType.LIGHT_INFO_CLOUD_RADIANCE_EXT, "Constant extension type");
            MemorySegment profile = constant.get(ADDRESS, 8).reinterpret(80, scope, null);
            require(profile.get(JAVA_INT, 0) == StructType.LIGHT_INFO_CLOUD_RADIANCE_PROFILE_EXT, "Profile extension type");
            require(profile.get(ADDRESS, 8).address() == 0, "Profile terminates chain");
            samples[0] = 99;
            for (int index = 0; index < expected.length; index++) {
                require(profile.get(JAVA_FLOAT, 16 + 4L * index) == expected[index], "Copied profile component " + index);
            }
        } finally {
            RemixBridge.freeExt(extension);
        }

        long constant = RemixBridge.allocDistantLightChain(0, -1, 0, .5f, 1, 0, null);
        try (Arena scope = Arena.ofConfined()) {
            MemorySegment distant = MemorySegment.ofAddress(constant).reinterpret(40, scope, null);
            require(distant.get(ADDRESS, 8).address() == 0, "Absent profile preserves old distant-light layout");
        } finally {
            RemixBridge.freeExt(constant);
        }

        reject(new float[15]);
        float[] invalid = expected.clone();
        invalid[4] = -1;
        reject(invalid);
        invalid = expected.clone();
        invalid[3] = Float.NaN;
        reject(invalid);
        invalid = expected.clone();
        invalid[8] = Float.POSITIVE_INFINITY;
        reject(invalid);
        invalid = expected.clone();
        invalid[7] = invalid[3];
        reject(invalid);
        invalid = expected.clone();
        invalid[11] = invalid[7] - 1;
        reject(invalid);
        System.out.println("Verified cloud profile layout, copied ownership, optional chain, and invalid-input rejection");
    }

    private static void reject(float[] samples) {
        try {
            long extension = RemixBridge.allocDistantLightChain(0, -1, 0, .5f, 1, 0, null, samples);
            RemixBridge.freeExt(extension);
            throw new AssertionError("Invalid cloud profile was accepted");
        } catch (IllegalArgumentException expected) {
            // Malformed input must be rejected before allocating a published extension.
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
