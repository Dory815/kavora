/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: MIT
 */
module cloud_shape;

#include "rtx/utility/cloud_noise.slangh"
#include "rtx/pass/cloud_noise.h"
#include "rtx/utility/cirrus_shapes.slangh"

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
      const uint group = uint(x + y) % kCirrusGroupCount;
      const uint count = kCirrusGroupSizes[group];
      const uint first = hash % count;
      const uint stride = (hash & 0x100u) != 0 ? 1u : count - 1u;
      // The three-colour region lattice wraps without sharing a variant across an edge.
      // Each region visits its own shapes once, in a deterministic permutation.
      for (uint packet = 0; packet < count; packet++)
      {
        const uint seed = cloudNoiseHash(uint3(hash, packet, 0), kCloudNoiseSeed + 443);
        const uint tile = kCirrusGroups[group][(first + packet * stride) % count];
        const float aspect = kCirrusGeometry[tile].x;
        const float orientation = kCirrusGeometry[tile].y;
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
        const float length = 1.5f * (0.25f + 0.35f * cirrusRandom(seed, 5));
        // Size the longest crop axis; a long fallstreak must not become wider
        // than its weather region simply because its photograph is panoramic.
        const float2 extent = float2(aspect, 1.0f) * (length / max(aspect, 1.0f));
        const float2 local = float2(dot(offset, direction), dot(offset, perpendicular))
          / extent + 0.5f;
        if (any(local < 0) || any(local > 1))
        {
          continue;
        }
        const float2 atlasGrid = float2(kCirrusAtlasGrid);
        const float2 tileUv = (local + float2(tile % kCirrusAtlasGrid.x, tile / kCirrusAtlasGrid.x)) / atlasGrid;
        const float pixelWidth = float(period) / float(kCloudWeatherResolution);
        const float2 dx = (wind * wind.x + across * across.x * reflection) * pixelWidth;
        const float2 dy = (wind * wind.y + across * across.y * reflection) * pixelWidth;
        const float2 atlasDx = float2(dot(dx, direction), dot(dx, perpendicular)) / extent / atlasGrid;
        const float2 atlasDy = float2(dot(dy, direction), dot(dy, perpendicular)) / extent / atlasGrid;
        const float amount = region * (0.45f + 0.55f * cirrusRandom(seed, 6));
        density += atlas.SampleGrad(tileUv, atlasDx, atlasDy).r * amount;
      }
    }
  }
  return saturate(density);
}
