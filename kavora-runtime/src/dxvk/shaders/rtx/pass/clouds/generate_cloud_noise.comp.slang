/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 RTX Remix for Minecraft Community Edition contributors
 * SPDX-License-Identifier: Apache-2.0
 */
//!variant generate_cloud_noise.comp CLOUD_NOISE_BASE
//!variant generate_cloud_detail.comp
//!end-variants

#include "rtx/pass/cloud_noise.h"
#include "rtx/utility/cloud_noise.slangh"

#ifdef CLOUD_NOISE_BASE
layout(rg16f, binding = 0)
#else
layout(rgba8, binding = 0)
#endif
RWTexture3D<float4> CloudNoise;
layout(push_constant)
ConstantBuffer<CloudNoiseGenerationArgs> cb;

[shader("compute")]
[numthreads(4, 4, 4)]
void main(uint3 id : SV_DispatchThreadID)
{
  const uint resolution = cb.detail ? kCloudDetailResolution : kCloudBaseResolution;
  const float3 uv = (float3(id) + 0.5f) / float(resolution);
  if (cb.detail)
  {
    CloudNoise[id] = float4(cloudWorleyFbm(uv, 2, kCloudNoiseSeed + 101),
      cloudWorleyFbm(uv, 4, kCloudNoiseSeed + 113),
      cloudWorleyFbm(uv, 8, kCloudNoiseSeed + 127), 1);
    return;
  }
  float perlin = 0;
  float amplitude = 1;
  for (uint octave = 0; octave < 3; octave++)
  {
    const uint period = 2u << octave;
    perlin += amplitude * cloudPerlin(uv * float(period), period, kCloudNoiseSeed + octave);
    amplitude *= 0.5f;
  }
  perlin = saturate(perlin * (0.75f / 1.75f) + 0.5f);
  const float worley4 = cloudWorleyFbm(uv, 4, kCloudNoiseSeed + 11);
  const float lowFrequency = 0.625f * worley4 + 0.25f * cloudWorleyFbm(uv, 8, kCloudNoiseSeed + 23)
    + 0.125f * cloudWorleyFbm(uv, 16, kCloudNoiseSeed + 37);
  // cloudWorleyFbm is one minus distance: its feature centres dilate the
  // coherent Perlin mass into convex billows, rather than hollowing it out.
  const float cumulus = saturate(0.65f + 0.30f * (perlin - 0.5f) + 1.75f * (lowFrequency - 0.47f));
  // Filtering both moments retains the variation needed by the coverage threshold.
  CloudNoise[id] = float4(cumulus, cumulus * cumulus, 0, 0);
}
