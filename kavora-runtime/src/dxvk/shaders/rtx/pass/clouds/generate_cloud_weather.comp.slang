/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 RTX Remix for Minecraft Community Edition contributors
 * SPDX-License-Identifier: Apache-2.0
 */
#include "rtx/pass/cloud_noise.h"
#include "rtx/utility/cloud_noise.slangh"

import rtx.utility.cloud_shape;

layout(rgba16f, binding = 0)
RWTexture2D<float4> CloudWeather;

layout(binding = 1)
Sampler2D<float4> CloudCirrusAtlas;

[shader("compute")]
[numthreads(8, 8, 1)]
void main(uint2 id : SV_DispatchThreadID)
{
  const float2 uv = (float2(id) + 0.5f) / float(kCloudWeatherResolution);
  // Mesoscale moisture controls whether a region can support condensation.
  // Separate kilometre-scale updraft groups from the broad dry intervals.
  const float regional = 0.65f * cloudPerlin(float3(uv * 2.0f, 0.37f), 2, kCloudNoiseSeed + 211)
    + 0.35f * cloudPerlin(float3(uv * 4.0f, 0.17f), 4, kCloudNoiseSeed + 212);
  const float region = smoothstep(-0.28f, 0.16f, regional);
  // Connected updrafts contain a range of kilometre-scale footprints. Their
  // fine octaves remain resolved in the 64 m weather texels at the default scale.
  const float groups = 0.55f * cloudPerlin(float3(uv * 32.0f, 0.37f), 32, kCloudNoiseSeed + 223)
    + 0.30f * cloudPerlin(float3(uv * 64.0f, 0.51f), 64, kCloudNoiseSeed + 227)
    + 0.15f * cloudPerlin(float3(uv * 128.0f, 0.19f), 128, kCloudNoiseSeed + 229);
  const float coverage = region * saturate(0.32f + 2.20f * groups);
  // Use a continuous development field; clipping whole regions to one cloud
  // type makes every cloud equally flat or equally tall.
  const float typeNoise = 0.65f * cloudPerlin(float3(uv * 16.0f, 0.71f), 16, kCloudNoiseSeed + 241)
    + 0.35f * cloudPerlin(float3(uv * 32.0f, 0.13f), 32, kCloudNoiseSeed + 251);
  const float type = saturate(0.5f + 0.9f * typeNoise);
  const float highDensity = cloudCirrusHorizontalDensity(uv, CloudCirrusAtlas);
  CloudWeather[id] = float4(coverage, coverage * coverage,
    type, highDensity);
}
