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
  const float region = smoothstep(-0.55f, 0.05f, regional);
  // Form mesoscale cloud streets and groups before adding individual billows.
  // The octaves span roughly 8, 4 and 2 km at the default 1 km shape scale;
  // they no longer make 0.5 km cells the dominant visible cloud footprint.
  const float groups = 0.50f * cloudPerlin(float3(uv * 8.0f, 0.37f), 8, kCloudNoiseSeed + 223)
    + 0.32f * cloudPerlin(float3(uv * 16.0f, 0.51f), 16, kCloudNoiseSeed + 227)
    + 0.18f * cloudPerlin(float3(uv * 32.0f, 0.19f), 32, kCloudNoiseSeed + 229);
  // Dry regions reduce cloud amount but do not become a hard cloud-free mask.
  // This allows cloud-rich skies to remain structured instead of switching
  // between isolated islands and a single continuous overcast sheet.
  const float regionalAmount = lerp(0.35f, 1.0f, region);
  const float coverage = regionalAmount * saturate(0.42f + 1.85f * groups);
  // Cloud development changes over broad weather regions, not independently
  // for every small cell. The density evaluator maps this continuous field to
  // shallow sheets, ordinary cumulus and stronger vertical development.
  const float typeNoise = 0.65f * cloudPerlin(float3(uv * 4.0f, 0.71f), 4, kCloudNoiseSeed + 241)
    + 0.35f * cloudPerlin(float3(uv * 8.0f, 0.13f), 8, kCloudNoiseSeed + 251);
  const float type = saturate(0.5f + 0.9f * typeNoise);
  const float highDensity = cloudCirrusHorizontalDensity(uv, CloudCirrusAtlas);
  CloudWeather[id] = float4(coverage, coverage * coverage,
    type, highDensity);
}
