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
  float coverage = 0;
  float amplitude = 1;
  for (uint octave = 0; octave < 4; octave++)
  {
    const uint period = 12u << octave;
    coverage += amplitude * cloudPerlin(float3(uv * float(period), 0.37f), period, kCloudNoiseSeed + 211 + octave);
    amplitude *= 0.5f;
  }
  coverage = saturate(coverage * (0.8f / 1.875f) + 0.5f);
  const float clumps = cloudWorley(float3(uv, 0.5f), 32, kCloudNoiseSeed + 223, true);
  coverage = saturate((0.55f * coverage + 0.45f * clumps) * 1.4f - 0.28f);
  const float type = 0.6f * cloudPerlin(float3(uv * 2.0f, 0.71f), 2, kCloudNoiseSeed + 241)
    + 0.4f * cloudPerlin(float3(uv * 4.0f, 0.13f), 4, kCloudNoiseSeed + 251);
  const float highDensity = cloudCirrusHorizontalDensity(uv, CloudCirrusAtlas);
  CloudWeather[id] = float4(coverage, coverage * coverage,
    saturate(type * 0.9f + 0.5f), highDensity);
}
