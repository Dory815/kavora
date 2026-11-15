/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: MIT
 */
module cloud_shape;

#include "rtx/utility/cloud_noise.slangh"

float2 cirrusFlow(float2 uv)
{
  const float2 potentialGradient =
    0.045f * cloudPerlinGradient2D(uv, 2, 0.37f, kCloudNoiseSeed + 401)
    + 0.012f * cloudPerlinGradient2D(uv, 4, 0.71f, kCloudNoiseSeed + 419);
  // Mean drift carries material through local strain without parallel density ridges.
  return float2(0.34f, 0.035f) + float2(potentialGradient.y, -potentialGradient.x);
}

public float cloudCirrusHorizontalDensity(float2 uv)
{
  // Bounded backward midpoint integration runs only while baking Weather.A.
  // The finite-step map approximates advection, not exact discrete volume preservation.
  float2 materialPosition = uv;
  const float dt = 0.8f / 12.0f;
  for (uint step = 0; step < 12; step++)
  {
    const float2 first = cirrusFlow(materialPosition);
    materialPosition -= dt * cirrusFlow(materialPosition - 0.5f * dt * first);
  }

  const float condensate =
    0.58f * cloudPerlin(float3(materialPosition * float2(9, 17), 0.31f), uint3(9, 17, 8), kCloudNoiseSeed + 431)
    + 0.28f * cloudPerlin(float3(materialPosition * float2(19, 37), 0.67f), uint3(19, 37, 8), kCloudNoiseSeed + 439)
    + 0.14f * cloudPerlin(float3(materialPosition * float2(31, 59), 0.49f), uint3(31, 59, 8), kCloudNoiseSeed + 443);
  const float meso =
    0.6f * cloudPerlin(float3(materialPosition * float2(7, 9), 0.59f), uint3(7, 9, 8), kCloudNoiseSeed + 449)
    + 0.4f * cloudPerlin(float3(materialPosition * float2(13, 15), 0.23f), uint3(13, 15, 8), kCloudNoiseSeed + 457);
  const float regional =
    0.7f * cloudPerlin(float3(uv * 3.0f, 0.41f), 3, kCloudNoiseSeed + 461)
    + 0.3f * cloudPerlin(float3(uv * 5.0f, 0.79f), 5, kCloudNoiseSeed + 463);
  // All material and coverage shaping happens before generating density mipmaps.
  return smoothstep(-0.10f, 0.24f, condensate)
    * smoothstep(-0.20f, 0.15f, meso) * smoothstep(-0.25f, 0.20f, regional);
}
