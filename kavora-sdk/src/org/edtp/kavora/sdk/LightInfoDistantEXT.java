/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package org.edtp.kavora.sdk;

/**
 * Distant (directional) light extension.
 */
public class LightInfoDistantEXT {
    public Float3D direction = new Float3D(0, -1, 0);
    public float angularDiameterDegrees = 0.5f;
    public float volumetricRadianceScale = 1.0f;
    /** Clear-air incident radiance for clouds. Null uses the light's ordinary radiance. */
    public Float3D cloudIncidentRadiance;
    /** Four RGB/altitude samples (16 floats), copied during create/update. Null uses constant cloud radiance. */
    public float[] cloudRadianceProfile;

    public LightInfoDistantEXT() {}

    public static class Builder {
        private Float3D direction = new Float3D(0, -1, 0);
        private float angularDiameterDegrees = 0.5f;
        private float volumetricRadianceScale = 1.0f;
        private Float3D cloudIncidentRadiance;
        private float[] cloudRadianceProfile;

        public Builder direction(float x, float y, float z) {
            this.direction = new Float3D(x, y, z);
            return this;
        }

        public Builder angularDiameterDegrees(float degrees) {
            this.angularDiameterDegrees = degrees;
            return this;
        }

        public Builder volumetricRadianceScale(float scale) {
            this.volumetricRadianceScale = scale;
            return this;
        }

        public Builder cloudIncidentRadiance(float red, float green, float blue) {
            this.cloudIncidentRadiance = new Float3D(red, green, blue);
            return this;
        }

        /** RGB uses light radiance units; the fourth component is increasing world-space altitude. */
        public Builder cloudRadianceProfile(float[] samples) {
            if (samples != null && samples.length != 16) {
                throw new IllegalArgumentException("Cloud radiance profile requires four RGB/altitude samples");
            }
            this.cloudRadianceProfile = samples;
            return this;
        }

        public LightInfoDistantEXT build() {
            LightInfoDistantEXT ext = new LightInfoDistantEXT();
            ext.direction = this.direction;
            ext.angularDiameterDegrees = this.angularDiameterDegrees;
            ext.volumetricRadianceScale = this.volumetricRadianceScale;
            ext.cloudIncidentRadiance = this.cloudIncidentRadiance;
            ext.cloudRadianceProfile = this.cloudRadianceProfile;
            return ext;
        }
    }

    public static Builder builder() {
        return new Builder();
    }
}
