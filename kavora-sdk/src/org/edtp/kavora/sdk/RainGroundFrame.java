/* SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors.
 * SPDX-License-Identifier: Apache-2.0 */
package org.edtp.kavora.sdk;

import java.nio.ByteBuffer;

/** World columns exposed to rain. A supplied direct buffer is borrowed for the duration of Submit. */
public final class RainGroundFrame {
    public static final int GRID_SIZE = 256;
    public static final int GRID_BYTES = GRID_SIZE * GRID_SIZE * Integer.BYTES;

    public ByteBuffer columns;
    public int originX;
    public int originZ;
    public float rain;
}
