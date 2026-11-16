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

  // Broad moisture regions provide a shared weather context for each family.
  const float regional = 0.65f * cloudPerlin(float3(uv * 2.0f, 0.37f), 2, kCloudNoiseSeed + 211)
    + 0.35f * cloudPerlin(float3(uv * 4.0f, 0.17f), 4, kCloudNoiseSeed + 212);
  const float region = smoothstep(-0.55f, 0.05f, regional);
  const float regionalAmount = lerp(0.35f, 1.0f, region);

  // Broken cumulus groups form at kilometre scales before individual billows.
  const float groups = 0.50f * cloudPerlin(float3(uv * 8.0f, 0.37f), 8, kCloudNoiseSeed + 223)
    + 0.32f * cloudPerlin(float3(uv * 16.0f, 0.51f), 16, kCloudNoiseSeed + 227)
    + 0.18f * cloudPerlin(float3(uv * 32.0f, 0.19f), 32, kCloudNoiseSeed + 229);
  const float cumulusCoverage = saturate(0.42f + 1.85f * groups);

  // Stratiform decks occupy broader, connected regions with irregular openings.
  // Their mask shares the moisture field but has a distinct spatial spectrum.
  // A weak cellular term breaks smooth blobs into open/closed cloud cells.
  const float deckCells = cloudWorley(float3(uv, 0.0f), 8, kCloudNoiseSeed + 237, true);
  const float deckNoise = 0.55f * regional
    + 0.20f * cloudPerlin(float3(uv * 8.0f, 0.83f), 8, kCloudNoiseSeed + 233)
    + 0.12f * cloudPerlin(float3(uv * 16.0f, 0.23f), 16, kCloudNoiseSeed + 239)
    + 0.08f * cloudPerlin(float3(uv * 32.0f, 0.61f), 32, kCloudNoiseSeed + 243)
    + 0.05f * (deckCells - 0.5f);
  const float deckCoverage = smoothstep(-0.40f, 0.10f, deckNoise);

  // Cloud family varies over broad weather regions, not independently per cell.
  // Humid regions modestly favor deeper development; the density evaluator
  // supplies the corresponding vertical profile and 3D body morphology.
  const float typeNoise = 0.65f * cloudPerlin(float3(uv * 4.0f, 0.71f), 4, kCloudNoiseSeed + 241)
    + 0.35f * cloudPerlin(float3(uv * 8.0f, 0.13f), 8, kCloudNoiseSeed + 251);
  const float type = saturate(0.5f + 0.9f * typeNoise + 0.18f * regional);
  // Preserve both family masks through the weather-map mip chain. The density
  // evaluator blends them after filtering, using the local cloud-family type.
  const float highDensity = cloudCirrusHorizontalDensity(uv, CloudCirrusAtlas);
  CloudWeather[id] = float4(regionalAmount * cumulusCoverage,
    regionalAmount * deckCoverage, type, highDensity);
}
