/* SPDX-FileCopyrightText: Copyright (c) 2026 RTX Remix for Minecraft Community Edition contributors
 * SPDX-License-Identifier: Apache-2.0
 */
module cloud_density;

#include "rtx/pass/cloud_noise.h"
#include "rtx/utility/cloud_noise.slangh"

public struct CloudDensityArgs
{
  public float3 groundReference;
  public float3 up;
  public float planetRadius;
  public float3 windOffset;
  public float shapeScale;
  public float baseHeight;
  public float thickness;
  public float coverage;
  public float weather;
  public float thunder;
  public float night;
  public float highBaseHeight;
  public float highThickness;
  public float highCoverage;
}

[ForceInline]
public float cloudAltitude(CloudDensityArgs args, float3 position)
{
  const float3 p = position - args.groundReference;
  const float h = dot(p, args.up);
  const float horizontalSquared = max(0.0f, dot(p, p) - h * h);
  const float radius = args.planetRadius;
  const float radial = sqrt((radius + h) * (radius + h) + horizontalSquared);
  return (h * (2.0f * radius + h) + horizontalSquared) / (radial + radius);
}

[ForceInline]
public float3 cloudCoordinates(CloudDensityArgs args, float3 position)
{
  const float3 drift = position - args.windOffset;
  const float3 local = args.up.z > 0.5f ? drift.xzy : drift;
  return float3(local.x, cloudAltitude(args, position), local.z) / args.shapeScale;
}

[ForceInline]
float cloudNoiseLod(float footprint, float period, float resolution)
{
  return max(0.0f, log2(max(footprint * resolution / period, 1.0f)));
}

// Integrate a clipped ramp and its square over a moment-matched uniform shape distribution.
[ForceInline]
float2 cloudThresholdMoments(float shape, float secondMoment, float threshold, float rampWidth)
{
  const float value = shape - threshold;
  const float width = sqrt(3.0f * max(secondMoment - shape * shape, 0.0f));
  if (width <= 1e-4f)
  {
    const float density = saturate(value / max(rampWidth, 1e-4f));
    return float2(density, density * density);
  }
  const float lower = saturate((value - width) / max(rampWidth, 1e-4f));
  const float upper = saturate((value + width) / max(rampWidth, 1e-4f));
  const float2 rampIntegral = float2(0.5f * (upper * upper - lower * lower),
    (upper * upper * upper - lower * lower * lower) / 3.0f) * rampWidth;
  const float plateau = max(value + width - max(rampWidth, value - width), 0.0f);
  return saturate((rampIntegral + plateau) / (2.0f * width));
}

[ForceInline]
float2 cloudCoverageMoments(float shape, float secondMoment, float coverage)
{
  return coverage > 0 ? cloudThresholdMoments(shape, secondMoment, 1.0f - coverage, coverage) : float2(0);
}

[ForceInline]
float cloudSmoothstepIntegral(float height, float begin, float end)
{
  const float t = saturate((height - begin) / (end - begin));
  return (end - begin) * t * t * t * (1.0f - 0.5f * t) + max(height - end, 0.0f);
}

[ForceInline]
float cloudProfileIntegral(float height, float bottomEnd, float topBegin)
{
  const float h = saturate(height);
  return cloudSmoothstepIntegral(h, 0.0f, bottomEnd) - cloudSmoothstepIntegral(h, topBegin, 1.0f);
}

[ForceInline]
float cloudHeightProfile(float height, float bottomEnd, float topBegin, float footprint)
{
  if (footprint <= 1e-4f)
  {
    return smoothstep(0.0f, bottomEnd, height) * (1.0f - smoothstep(topBegin, 1.0f, height));
  }
  const float lower = cloudProfileIntegral(height - 0.5f * footprint, bottomEnd, topBegin);
  const float upper = cloudProfileIntegral(height + 0.5f * footprint, bottomEnd, topBegin);
  return saturate((upper - lower) / footprint);
}

public struct CloudColumn
{
  public float coverage;
  public float type;
  public float thickness;
  public float coverageVariance;
  public float3 shapePhase;
}

[ForceInline]
float3 cloudBillowPhase(float2 position)
{
  // Four body periods per lattice cell bound the phase derivative to 0.2344.
  // Its lattice wraps with the weather map, including negative coordinates.
  const float2 lattice = position * 0.25f;
  const int2 cell = int2(floor(lattice));
  const float2 t = frac(lattice);
  const float2 blend = t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
  float3 phase = 0;
  [unroll]
  for (uint corner = 0; corner < 4; corner++)
  {
    const uint2 offset = uint2(corner & 1u, corner >> 1);
    const uint3 wrapped = cloudNoiseWrap(int3(cell.x + int(offset.x), 0, cell.y + int(offset.y)),
      kCloudWeatherPeriod / (4u * kCloudBasePeriod));
    const uint hash = cloudNoiseHash(wrapped, kCloudNoiseSeed + 431u);
    const float3 value = float3(hash & 1023u, (hash >> 10) & 1023u, (hash >> 20) & 1023u)
      * (1.0f / 1023.0f) - 0.5f;
    const float2 weight = lerp(1.0f - blend, blend, float2(offset));
    phase += value * (0.5f * weight.x * weight.y);
  }
  return phase;
}

[ForceInline]
public CloudColumn cloudColumn(CloudDensityArgs args, float2 position, Sampler2D<float4> weatherSampler,
  float footprint = 0)
{
  const float lod = cloudNoiseLod(footprint, args.shapeScale * float(kCloudWeatherPeriod), float(kCloudWeatherResolution));
  const float4 weather = weatherSampler.SampleLevel(position / float(kCloudWeatherPeriod), lod);
  const float bias = (args.coverage - 0.45f) * 0.9f + 0.51f * args.weather
    + 0.15f * args.thunder - 0.17f * args.night * (1.0f - args.weather);
  const float type = saturate(weather.b * (1.0f - 0.4f * args.weather) + 0.85f * args.thunder);
  const float stratiformBlend = 1.0f - smoothstep(0.20f, 0.62f, type);
  const float cumulusMean = saturate(weather.r + bias);
  const float deckMean = saturate(weather.g + bias);
  // Family masks retain their own mip-filtered means. Reconstruct a bounded
  // unresolved-coverage variance so grazing rays do not turn their average
  // into a uniform, opaque horizontal deck.
  const float mipVarianceScale = 0.25f * saturate(lod * 0.25f);
  const float cumulusVariance = cumulusMean * (1.0f - cumulusMean) * mipVarianceScale;
  const float deckVariance = deckMean * (1.0f - deckMean) * mipVarianceScale;
  const float2 cumulusCoverage = cloudCoverageMoments(cumulusMean,
    cumulusMean * cumulusMean + cumulusVariance, 1.0f);
  const float2 deckCoverage = cloudCoverageMoments(deckMean,
    deckMean * deckMean + deckVariance, 1.0f);
  const float2 coverage = lerp(cumulusCoverage, deckCoverage, stratiformBlend);
  // Cloud type varies across groups. Local condensation controls development
  // above a shared base, rather than assigning independent heights to columns.
  const float thickness = args.thickness * (0.22f + 0.78f * smoothstep(0.1f, 0.9f, type))
    * (0.4f + 0.6f * coverage.x);
  const float3 shapePhase = coverage.x > 0 ? cloudBillowPhase(position / float(kCloudBasePeriod)) : float3(0);
  return { coverage.x, type, thickness, max(coverage.y - coverage.x * coverage.x, 0.0f),
    shapePhase };
}

[ForceInline]
float cloudOvercastThickness(CloudDensityArgs args, float cloudType)
{
  return args.thickness * lerp(0.20f, 0.35f, args.thunder) * lerp(1.0f, 1.35f, cloudType);
}

[ForceInline]
public float cloudColumnThickness(CloudDensityArgs args, CloudColumn column)
{
  const float overcastThickness = max(args.weather, args.thunder) > 0
    ? cloudOvercastThickness(args, column.type) : 0.0f;
  return max(column.thickness, overcastThickness);
}

[ForceInline]
float overcastDensity(CloudDensityArgs args, float heightAboveBase,
  float cloudType, float coverage, float heightFootprint)
{
  const float precipitation = max(args.weather, args.thunder);
  if (precipitation <= 0)
  {
    return 0;
  }

  // A shallow stratiform contribution develops beneath taller cells as rain sets in.
  const float layerThickness = cloudOvercastThickness(args, cloudType);
  const float height = heightAboveBase / layerThickness;
  const float profile = cloudHeightProfile(height, 0.16f, 0.65f, heightFootprint / layerThickness);
  // Rain deepens existing stratiform regions instead of painting a uniform
  // shell across every dry opening in the weather field.
  return precipitation * lerp(0.36f, 0.47f, args.thunder) * coverage * profile;
}

[ForceInline]
float cirrusDensity(CloudDensityArgs args, float3 p, Sampler2D<float4> weatherSampler,
  float footprint, float heightFootprint)
{
  if (args.highThickness <= 0)
  {
    return 0;
  }
  const float height = (p.y * args.shapeScale - args.highBaseHeight) / args.highThickness;
  const float profileFootprint = heightFootprint / args.highThickness;
  if (args.highCoverage <= 0 || height + 0.5f * profileFootprint <= 0 || height - 0.5f * profileFootprint >= 1)
  {
    return 0;
  }
  const float weatherLod = cloudNoiseLod(footprint, args.shapeScale * float(kCloudHighWeatherPeriod), float(kCloudWeatherResolution));
  const float4 weather = weatherSampler.SampleLevel(p.xz / float(kCloudHighWeatherPeriod), weatherLod);
  const float coverage = saturate(args.highCoverage);
  const float amount = coverage * (2.0f - coverage);
  const float profile = cloudHeightProfile(height, 0.15f, 0.65f, profileFootprint);
  // Finished fibres fade without applying another threshold to their mip chain.
  return weather.a * amount * profile;
}

[ForceInline]
public float cloudDensityInColumn(CloudDensityArgs args, float3 coordinates, CloudColumn column,
  Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler, float footprint, float heightFootprint)
{
  // A prepared column fixes local weather while retaining the shared three-dimensional shape.
  const float3 p = coordinates;
  const float heightAboveBase = p.y * args.shapeScale - args.baseHeight;
  if (heightAboveBase + 0.5f * heightFootprint <= 0 || heightAboveBase - 0.5f * heightFootprint >= args.thickness)
  {
    return 0;
  }
  const float overcast = overcastDensity(args, heightAboveBase, column.type,
    column.coverage, heightFootprint);
  const float columnHeight = heightAboveBase / column.thickness;
  const float profileFootprint = heightFootprint / column.thickness;
  if (column.coverage <= 0 || columnHeight - 0.5f * profileFootprint >= 1)
  {
    return overcast;
  }
  const float height = saturate(columnHeight);
  const float profile = cloudHeightProfile(columnHeight, 0.1f, lerp(0.3f, 0.75f, column.type), profileFootprint);
  const float anvil = smoothstep(0.75f, 1.0f, column.type) * smoothstep(0.8f, 0.9f, height)
    * (1.0f - smoothstep(0.95f, 1.0f, height));
  const float coverageScale = 1.0f - 0.35f * height * (1.0f - column.type) + 0.5f * anvil;
  const float coverage = saturate(column.coverage * coverageScale);
  if (profile <= 0)
  {
    return overcast;
  }
  const float stratiform = 1.0f - smoothstep(0.20f, 0.62f, column.type);
  // Each family has a fixed period that divides the host's weather wrap.
  // Interpolate density, not a world-coordinate wavelength.
  const float3 shapePosition = float3(p.x, heightAboveBase / args.shapeScale, p.z)
    + column.shapePhase * float(kCloudBasePeriod);
  const float detailPeriod = float(kCloudBasePeriod) * 0.0625f;
  const float detailLod = cloudNoiseLod(footprint, args.shapeScale * detailPeriod, 32.0f);
  const float3 detail = detailSampler.SampleLevel(shapePosition / detailPeriod, detailLod).rgb;
  const float3 warpedPosition = shapePosition + (detail - 0.5f) * (0.04f * float(kCloudBasePeriod));
  const float coverageVariance = column.coverageVariance * coverageScale * coverageScale;
  const float billows = dot(detail, float3(0.625f, 0.25f, 0.125f));
  const float erosion = lerp(billows, 1.0f - billows, saturate(height * 4.0f)) * 0.10f;

  float density = 0;
  if (stratiform < 1.0f)
  {
    const float bodyPeriod = float(kCloudBasePeriod);
    const float lod = cloudNoiseLod(footprint, args.shapeScale * bodyPeriod, 128.0f);
    const float4 body = baseSampler.SampleLevel(warpedPosition / bodyPeriod, lod);
    density += (1.0f - stratiform) * cloudThresholdMoments(body.r * profile,
      body.g * profile * profile + coverageVariance, 1.0f - coverage + erosion, 0.08f).x;
  }
  if (stratiform > 0.0f)
  {
    const float bodyPeriod = 4.0f * float(kCloudBasePeriod);
    const float lod = cloudNoiseLod(footprint, args.shapeScale * bodyPeriod, 128.0f);
    const float4 body = baseSampler.SampleLevel(warpedPosition / bodyPeriod, lod);
    density += stratiform * cloudThresholdMoments(body.r * profile,
      body.g * profile * profile + coverageVariance, 1.0f - coverage + erosion, 0.08f).x;
  }
  return max(overcast, density);
}

[ForceInline]
public float cloudDensity(CloudDensityArgs args, float3 position, Sampler2D<float4> weatherSampler,
  Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler, float footprint = 0, uint layer = 0,
  float heightFootprint = 0)
{
  const float3 p = cloudCoordinates(args, position);
  if (layer == 1)
  {
    return cirrusDensity(args, p, weatherSampler, footprint, heightFootprint);
  }
  const float heightAboveBase = p.y * args.shapeScale - args.baseHeight;
  if (heightAboveBase + 0.5f * heightFootprint <= 0 || heightAboveBase - 0.5f * heightFootprint >= args.thickness)
  {
    return 0;
  }
  const CloudColumn column = cloudColumn(args, p.xz, weatherSampler, footprint);
  return cloudDensityInColumn(args, p, column, baseSampler, detailSampler, footprint, heightFootprint);
}
