/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.sdk;

/**
 * Finite clear-air transport paired with an atmospheric dome and its transmission.
 * Lengths are kilometres and extinction is inverse kilometres. Sea level is in world metres.
 * Arrays are copied into the light's temporary FFM arena before its foreign call.
 */
public final class LightInfoAtmosphereEXT {
    public long transmittanceLut;
    public long scatteringLut;
    /** Two world-space directions toward the lights, followed by their angular radii in radians. */
    public final float[] lightDirections = new float[8];
    /** Two RGB irradiances with zero fourth components. */
    public final float[] lightIrradiances = new float[8];
    public float seaLevelMeters;
    public float innerRadius;
    public float lowerDepth;
    public float atmosphereHeight;
    public Float3D rayleighExtinction = new Float3D();
    public float rayleighHeight;
    public float mieExtinction;
    public float mieHeight;
    public float mieAlbedo;
    public float mieAnisotropy;
}
