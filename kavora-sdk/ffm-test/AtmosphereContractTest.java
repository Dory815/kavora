/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.sdk;

import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.util.function.Consumer;
import static java.lang.foreign.ValueLayout.*;

/** Exercises optional atmosphere ownership and the fixed C layout without loading a renderer. */
public final class AtmosphereContractTest {
    public static void main(String[] args) {
        require(RemixLayouts.size("LightInfoAtmosphereEXT") == 144, "Atmosphere extension size");
        require(RemixLayouts.size("LightInfoDomeEXT") == 80, "Existing dome layout remains compatible");
        LightInfoAtmosphereEXT air = validAtmosphere();
        long extension = allocate(air);
        try (Arena scope = Arena.ofConfined()) {
            MemorySegment dome = MemorySegment.ofAddress(extension).reinterpret(80, scope, null);
            MemorySegment transmission = dome.get(ADDRESS, 8).reinterpret(24, scope, null);
            require(transmission.get(JAVA_INT, 0) == StructType.LIGHT_INFO_DOME_TRANSMITTANCE_EXT, "Dome transmission type");
            MemorySegment atmosphere = transmission.get(ADDRESS, 8).reinterpret(144, scope, null);
            require(atmosphere.get(JAVA_INT, 0) == StructType.LIGHT_INFO_ATMOSPHERE_EXT, "Atmosphere extension type");
            require(atmosphere.get(ADDRESS, 8).address() == 0, "Atmosphere terminates chain");
            require(atmosphere.get(ADDRESS, 16).address() == 11, "Transmission texture handle");
            require(atmosphere.get(ADDRESS, 24).address() == 12, "Scattering texture handle");
            air.lightDirections[1] = 99;
            air.lightIrradiances[0] = 99;
            air.rayleighExtinction.x = 99;
            require(atmosphere.get(JAVA_FLOAT, 36) == 1, "Direction storage is copied");
            require(atmosphere.get(JAVA_FLOAT, 64) == 10, "Irradiance storage is copied");
            require(atmosphere.get(JAVA_FLOAT, 96) == 64, "Sea-level offset");
            require(atmosphere.get(JAVA_FLOAT, 112) == .0055f, "Optical coefficients are copied");
            require(atmosphere.get(JAVA_FLOAT, 140) == .9f, "Anisotropy offset");
        } finally {
            RemixBridge.freeExt(extension);
        }
        long legacy = allocate(null);
        try (Arena scope = Arena.ofConfined()) {
            MemorySegment dome = MemorySegment.ofAddress(legacy).reinterpret(80, scope, null);
            MemorySegment transmission = dome.get(ADDRESS, 8).reinterpret(24, scope, null);
            require(transmission.get(ADDRESS, 8).address() == 0, "Absent atmosphere preserves optional chain");
        } finally {
            RemixBridge.freeExt(legacy);
        }
        reject(value -> value.transmittanceLut = 0);
        reject(value -> value.scatteringLut = 0);
        reject(value -> value.innerRadius = Float.POSITIVE_INFINITY);
        reject(value -> value.lowerDepth = Float.NaN);
        reject(value -> value.atmosphereHeight = value.lowerDepth);
        reject(value -> value.rayleighExtinction.z = -1);
        reject(value -> value.mieHeight = 0);
        reject(value -> value.mieAlbedo = 1.1f);
        reject(value -> value.mieAnisotropy = 1);
        reject(value -> value.lightDirections[1] = 2);
        reject(value -> value.lightDirections[7] = Float.NaN);
        reject(value -> value.lightIrradiances[0] = -1);
        reject(value -> value.lightIrradiances[7] = 1);
        System.out.println("Verified atmosphere ABI, copied ownership, optional chain, and invalid-input rejection");
    }

    private static long allocate(LightInfoAtmosphereEXT air) {
        LightInfoDomeEXT dome = new LightInfoDomeEXT();
        return RemixBridge.allocDomeLightChain(dome.transform, 1, 2, 1, 0, 0, false, 0, air);
    }

    private static LightInfoAtmosphereEXT validAtmosphere() {
        LightInfoAtmosphereEXT air = new LightInfoAtmosphereEXT();
        air.transmittanceLut = 11;
        air.scatteringLut = 12;
        air.lightDirections[1] = 1;
        air.lightDirections[3] = .004f;
        air.lightDirections[5] = -1;
        air.lightDirections[7] = .004f;
        air.lightIrradiances[0] = 10;
        air.lightIrradiances[1] = 20;
        air.lightIrradiances[2] = 30;
        air.seaLevelMeters = 64;
        air.innerRadius = 6359;
        air.lowerDepth = 12;
        air.atmosphereHeight = 112;
        air.rayleighExtinction = new Float3D(.0055f, .013f, .0224f);
        air.rayleighHeight = 8;
        air.mieExtinction = .021f;
        air.mieHeight = 1.2f;
        air.mieAlbedo = .9f;
        air.mieAnisotropy = .9f;
        return air;
    }

    private static void reject(Consumer<LightInfoAtmosphereEXT> mutation) {
        LightInfoAtmosphereEXT air = validAtmosphere();
        mutation.accept(air);
        try {
            long extension = allocate(air);
            RemixBridge.freeExt(extension);
            throw new AssertionError("Malformed atmosphere was accepted");
        } catch (IllegalArgumentException expected) {
            // No native extension may outlive a failed validation.
        }
    }

    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
}
