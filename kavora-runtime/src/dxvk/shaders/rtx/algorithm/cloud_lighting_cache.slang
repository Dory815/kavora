// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
module cloud_lighting_cache;

import "rtx/pass/cloud_parameters.slang";
import "rtx/utility/cloud_density.slang";
#include "rtx/pass/clouds/cloud_lighting_cache.h"

// One density field and two cumulative integrals serve every viewing ray.
// These tables contain optical depth, not view-dependent cloud radiance.
public struct CloudLightingCache
{
  public Sampler3D<float> sun;
  public Sampler3D<float> moon;
};

[ForceInline]
public uint cloudLightingResolution(CloudArgs args)
{
  return CLOUD_LIGHTING_RESOLUTION_PER_STEP
    * clamp(args.lightSteps, uint(CLOUD_LIGHTING_MIN_QUALITY), uint(CLOUD_LIGHTING_MAX_QUALITY));
}

[ForceInline]
float3 cloudSecondHorizontalAxis(CloudArgs args)
{
  return args.up.z > 0.5f ? float3(0, 1, 0) : float3(0, 0, 1);
}

[ForceInline]
public float cloudLightingRadius(CloudArgs args)
{
  return max(args.maxDistance, 4.0f * args.shapeScale);
}

public struct CloudLightGrid
{
  public float3 origin;
  public float3 horizontal;
  public float3 vertical;
  public float3 direction;
  public float3 extent;

  public float3 cellSize(uint resolution)
  {
    return extent / float3(resolution, resolution / CLOUD_LIGHTING_LIGHT_HEIGHT_DIVISOR, resolution - 1);
  }

  public float3 coordinates(float3 position)
  {
    const float3 offset = position - origin;
    return float3(dot(offset, horizontal), dot(offset, vertical), dot(offset, direction)) / extent;
  }

  public float3 position(float3 coordinate)
  {
    const float3 offset = coordinate * extent;
    return origin + horizontal * offset.x + vertical * offset.y + direction * offset.z;
  }
};

public CloudLightGrid cloudLightGrid(CloudArgs args, uint light)
{
  CloudLightGrid grid = {};
  const float3 direction = args.lights[light].directionToLight;
  grid.direction = dot(direction, direction) > 1e-8f ? normalize(direction) : args.up;
  const float3 perpendicular = cross(args.up, grid.direction);
  grid.horizontal = dot(perpendicular, perpendicular) > 1e-8f
    ? normalize(perpendicular) : float3(1, 0, 0);
  grid.vertical = cross(grid.direction, grid.horizontal);

  const float radius = cloudLightingRadius(args);
  // Include surface shadow rays as well as the visible shell. Curvature is
  // bounded by the corners of the horizontal box, not by a flat cloud plane.
  const float lower = min(0.0f, args.baseHeight) - radius * radius / args.planetRadius;
  const float upper = args.baseHeight + args.thickness;
  const float middle = 0.5f * (lower + upper);
  const float halfHeight = 0.5f * (upper - lower);
  const float3 second = cloudSecondHorizontalAxis(args);
  const float3 center = args.up * middle;
  const float3 halfExtent = float3(
    radius * (abs(grid.horizontal.x) + abs(dot(grid.horizontal, second)))
      + halfHeight * abs(dot(grid.horizontal, args.up)),
    radius * (abs(grid.vertical.x) + abs(dot(grid.vertical, second)))
      + halfHeight * abs(dot(grid.vertical, args.up)),
    radius * (abs(grid.direction.x) + abs(dot(grid.direction, second)))
      + halfHeight * abs(dot(grid.direction, args.up)));
  const float3 projectedCenter = float3(dot(center, grid.horizontal), dot(center, grid.vertical),
    dot(center, grid.direction));
  const float3 corner = projectedCenter - halfExtent;
  grid.origin = args.groundReference + grid.horizontal * corner.x + grid.vertical * corner.y
    + grid.direction * corner.z;
  grid.extent = 2.0f * halfExtent + float3(0, 0, args.lightMaxDistance);
  return grid;
}

[ForceInline]
float3 cloudLightTextureCoordinate(CloudArgs args, float3 coordinate)
{
  const float resolution = float(cloudLightingResolution(args));
  // U/V samples are cell centers. Depth stores cumulative values at nodes,
  // including both endpoints, so its normalized coordinate needs a half texel.
  return float3(coordinate.xy, (saturate(coordinate.z) * (resolution - 1.0f) + 0.5f) / resolution);
}

public bool cloudCachedLightDepth(CloudArgs args, CloudLightingCache cache, uint light,
  float3 begin, float3 end, out float depth)
{
  depth = 0;
  if (all(begin == end))
  {
    return true;
  }
  const CloudLightGrid grid = cloudLightGrid(args, light);
  const float3 from = grid.coordinates(begin);
  const float3 to = grid.coordinates(end);
  if (any(from.xy < 0) || any(from.xy > 1) || any(to.xy < 0) || any(to.xy > 1)
    || min(from.z, to.z) < 0)
  {
    return false;
  }
  const uint resolution = cloudLightingResolution(args);
  const float2 size = float2(resolution, resolution / CLOUD_LIGHTING_LIGHT_HEIGHT_DIVISOR);
  const float2 pixel = from.xy * size - 0.5f;
  const int2 lower = int2(floor(pixel));
  const float2 fraction = frac(pixel);
  const float fromDepth = cloudLightTextureCoordinate(args, from).z;
  const float toDepth = cloudLightTextureCoordinate(args, to).z;
  float4 opticalDepth = 0;
  const float4 weights = float4((1.0f - fraction.x) * (1.0f - fraction.y),
    fraction.x * (1.0f - fraction.y), (1.0f - fraction.x) * fraction.y, fraction.x * fraction.y);
  float minimum = 3.402823466e+38f;
  [unroll]
  for (uint tap = 0; tap < 4; tap++)
  {
    const int2 offset = int2(tap & 1u, tap >> 1u);
    const float2 uv = (float2(clamp(lower + offset, int2(0), int2(size) - 1)) + 0.5f) / size;
    float a;
    float b;
    if (light == 0)
    {
      a = from.z >= 1 ? 0 : cache.sun.SampleLevel(float3(uv, fromDepth), 0);
      b = to.z >= 1 ? 0 : cache.sun.SampleLevel(float3(uv, toDepth), 0);
    }
    else
    {
      a = from.z >= 1 ? 0 : cache.moon.SampleLevel(float3(uv, fromDepth), 0);
      b = to.z >= 1 ? 0 : cache.moon.SampleLevel(float3(uv, toDepth), 0);
    }
    opticalDepth[tap] = max(0.0f, from.z < to.z ? a - b : b - a);
    if (weights[tap] > 0)
    {
      minimum = min(minimum, opticalDepth[tap]);
    }
  }
  // Interpolate transmitted energy. Exponentiating a filtered optical depth
  // would darken unresolved clear paths (Jensen's inequality). The shift keeps
  // this finite even when every complete prefix is deeply opaque.
  const float transmission = dot(weights, exp(minimum - opticalDepth));
  depth = max(0.0f, minimum - log(max(transmission, 1e-30f)));
  return true;
}

bool cloudLightHasEnergy(CloudLight light)
{
  if (any(light.irradiance > 0))
  {
    return true;
  }
  if (light.hasRadianceProfile != 0)
  {
    [unroll]
    for (uint sample = 0; sample < 4; sample++)
    {
      if (any(light.radianceProfile[sample].rgb > 0))
      {
        return true;
      }
    }
  }
  return false;
}

public int cloudCachedLightIndex(CloudArgs args, float3 direction)
{
  [unroll]
  for (uint light = 0; light < 2; light++)
  {
    // The small celestial disk shares a prefiltered central-axis far shadow.
    // Its actual sampled direction is retained by the local correction. Large
    // area lights use the bounded uncached quadrature throughout their cone.
    const float radius = args.lights[light].angularRadius;
    if (radius <= 0.02f && cloudLightHasEnergy(args.lights[light])
      && dot(direction, args.lights[light].directionToLight) >= cos(radius + 1e-5f) - 2e-7f)
    {
      return int(light);
    }
  }
  return -1;
}

float cloudCacheExtinction(CloudArgs args, CloudDensityArgs density, float3 position,
  float footprint, float heightFootprint, Sampler2D<float4> weather, Sampler3D<float4> base,
  Sampler3D<float4> detail)
{
  return args.extinction * cloudDensity(density, position, weather, base, detail, footprint, 0, heightFootprint);
}

public void buildCloudLightPrefix(CloudArgs args, CloudDensityArgs density, uint2 column, uint light,
  Sampler2D<float4> weather, Sampler3D<float4> base, Sampler3D<float4> detail, RWTexture3D<float> output)
{
  const uint resolution = cloudLightingResolution(args);
  const uint2 extent = uint2(resolution, resolution / CLOUD_LIGHTING_LIGHT_HEIGHT_DIVISOR);
  if (any(column >= extent))
  {
    return;
  }
  const CloudLightGrid grid = cloudLightGrid(args, light);
  const float2 horizontal = (float2(column) + 0.5f) / float2(extent);
  const float span = grid.extent.z / float(resolution - 1);
  // The prefix grid controls storage, not the shadow quadrature spacing.
  // Resolve density along the light ray without an isotropic cell-sized mip,
  // which would pull neighbouring off-ray clouds into otherwise clear gaps.
  const float nominalSupport = 0.5f * args.shapeScale / float(max(args.lightSteps, 1u));
  const uint subcells = min(max(1u, args.lightSteps / 2), max(1u, uint(ceil(span / (2.0f * nominalSupport)))));
  const float subspan = span / float(subcells);
  const float support = 0.5f * subspan;
  const float footprint = min(support, args.shapeScale / 128.0f);
  float depth = 0;
  output[uint3(column, resolution - 1)] = 0;
  for (uint node = resolution - 1; node > 0; node--)
  {
    const float lower = float(node - 1);
    const float3 middle = grid.position(float3(horizontal, (lower + 0.5f) / float(resolution - 1)));
    const float3 radialMiddle = normalize(middle - args.groundReference + args.up * args.planetRadius);
    const float altitude = cloudAltitude(density, middle);
    const float heightExtent = 0.6f * span * abs(dot(grid.direction, radialMiddle))
      + span * span / args.planetRadius;
    // All Gaussian supports in this cache cell fit within this radial bound.
    if (altitude + heightExtent >= args.baseHeight && altitude - heightExtent <= args.baseHeight + args.thickness)
    {
      for (uint subcell = 0; subcell < subcells; subcell++)
      {
        const float aNode = lower + (float(subcell) + 0.21132486541f) / float(subcells);
        const float bNode = lower + (float(subcell) + 0.78867513459f) / float(subcells);
        const float3 a = grid.position(float3(horizontal, aNode / float(resolution - 1)));
        const float3 b = grid.position(float3(horizontal, bNode / float(resolution - 1)));
        const float3 radialA = normalize(a - args.groundReference + args.up * args.planetRadius);
        const float3 radialB = normalize(b - args.groundReference + args.up * args.planetRadius);
        const float extinctionA = cloudCacheExtinction(args, density, a, footprint,
          abs(dot(grid.direction, radialA)) * support + support * support / args.planetRadius,
          weather, base, detail);
        const float extinctionB = cloudCacheExtinction(args, density, b, footprint,
          abs(dot(grid.direction, radialB)) * support + support * support / args.planetRadius,
          weather, base, detail);
        depth += support * (extinctionA + extinctionB);
      }
    }
    output[uint3(column, node - 1)] = depth;
  }
}
