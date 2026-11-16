/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: MIT
 */
module cloud_shape;

#include "rtx/utility/cloud_noise.slangh"
#include "rtx/pass/cloud_noise.h"

float cirrusRandom(uint hash, uint stream)
{
  return cloudNoiseUnit(cloudNoiseHash(uint3(hash, stream, 0), kCloudNoiseSeed));
}

public float cloudCirrusHorizontalDensity(float2 uv, Sampler2D<float4> atlas)
{
  const int period = 3;
  const float2 position = uv * float(period);
  float density = 0;
  for (int y = 0; y < period; y++)
  {
    for (int x = 0; x < period; x++)
    {
      const uint hash = cloudNoiseHash(uint3(x, y, 0), kCloudNoiseSeed + 421);
      const float2 jitter = float2(cirrusRandom(hash, 0), cirrusRandom(hash, 1));
      const float2 regionCenter = float2(x, y) + 0.5f + (jitter - 0.5f) * 0.7f;
      const float humidity = cloudPerlin(float3(regionCenter * (2.0f / float(period)), 0.41f), 2, kCloudNoiseSeed + 461);
      const float region = smoothstep(-0.22f, 0.20f, humidity);
      if (region <= 0)
      {
        continue;
      }
      const float bearing = 0.4f + 0.65f * cloudPerlin(float3(regionCenter * (2.0f / float(period)), 0.71f), 2, kCloudNoiseSeed + 419);
      const float2 wind = float2(cos(bearing), sin(bearing));
      const float2 across = float2(-wind.y, wind.x);
      for (uint packet = 0; packet < 4; packet++)
      {
        const uint seed = cloudNoiseHash(uint3(hash, packet, 0), kCloudNoiseSeed + 443);
        const uint tile = min(uint(cirrusRandom(seed, 0) * 4.0f), 3u);
        // Crop geometry and flow axes match packaging/runtime-textures/cirrus_sources.json.
        const float aspect = float4(0.8636364f, 2.2222222f, 0.4256757f, 0.7875000f)[tile];
        const float orientation = float4(1.21f, 0.11f, -1.42f, 1.40f)[tile];
        const float2 center = regionCenter + wind * ((cirrusRandom(seed, 1) - 0.5f) * 0.8f)
          + across * ((cirrusRandom(seed, 2) - 0.5f) * 0.45f);
        const float angle = bearing + orientation + (cirrusRandom(seed, 3) - 0.5f) * 0.5f;
        const float2 direction = float2(cos(angle), sin(angle));
        const float2 perpendicular = float2(-direction.y, direction.x);
        // Each finite cloud uses its nearest periodic image across region boundaries.
        const float2 rawDelta = position - center;
        const float2 delta = rawDelta - float(period) * round(rawDelta / float(period));
        const float reflection = cirrusRandom(seed, 4) > 0.5f ? 1.0f : -1.0f;
        const float2 offset = wind * dot(delta, wind) + across * dot(delta, across)
          * reflection;
        const float height = 0.25f + 0.35f * cirrusRandom(seed, 5);
        const float2 local = float2(dot(offset, direction), dot(offset, perpendicular))
          / (float2(aspect, 1.0f) * height) + 0.5f;
        if (any(local < 0) || any(local > 1))
        {
          continue;
        }
        const float2 tileUv = (local + float2(tile % 2u, tile / 2u)) * 0.5f;
        const float pixelWidth = float(period) / float(kCloudWeatherResolution);
        const float2 dx = (wind * wind.x + across * across.x * reflection) * pixelWidth;
        const float2 dy = (wind * wind.y + across * across.y * reflection) * pixelWidth;
        const float2 atlasDx = float2(dot(dx, direction), dot(dx, perpendicular)) / (float2(aspect, 1.0f) * height) * 0.5f;
        const float2 atlasDy = float2(dot(dy, direction), dot(dy, perpendicular)) / (float2(aspect, 1.0f) * height) * 0.5f;
        const float amount = region * (0.45f + 0.55f * cirrusRandom(seed, 6));
        density += atlas.SampleGrad(tileUv, atlasDx, atlasDy).r * amount;
      }
    }
  }
  return saturate(density);
}
