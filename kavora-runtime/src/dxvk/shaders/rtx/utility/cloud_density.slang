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

// Return the mean and central variance of a clamped, uniform-distribution ramp.
// Central moments retain constant fields without subtracting nearly equal squares.
[ForceInline]
public float2 cloudThresholdStatistics(float mean, float variance, float threshold, float rampWidth)
{
  const float value = mean - threshold;
  const float width = sqrt(3.0f * max(variance, 0.0f));
  const float ramp = max(rampWidth, 1e-4f);
  if (width <= 1e-4f)
  {
    return float2(saturate(value / ramp), 0);
  }
  if (value + width <= 0)
  {
    return 0;
  }
  if (value - width >= ramp)
  {
    return float2(1, 0);
  }
  if (value - width >= 0 && value + width <= ramp)
  {
    return float2(value / ramp, variance / (ramp * ramp));
  }
  if (value + width <= ramp)
  {
    const float tail = value + width;
    const float fraction = tail / (2.0f * width);
    const float maximum = tail / ramp;
    return float2(0.5f * fraction * maximum,
      fraction * maximum * maximum * (1.0f / 3.0f - 0.25f * fraction));
  }
  if (value - width >= 0)
  {
    const float tail = ramp - value + width;
    const float fraction = tail / (2.0f * width);
    const float maximum = tail / ramp;
    return float2(1.0f - 0.5f * fraction * maximum,
      fraction * maximum * maximum * (1.0f / 3.0f - 0.25f * fraction));
  }
  const float linearMass = ramp / (2.0f * width);
  const float upperMass = saturate((value + width - ramp) / (2.0f * width));
  const float lowerMass = saturate(1.0f - linearMass - upperMass);
  const float resultMean = upperMass + 0.5f * linearMass;
  const float lowerDelta = resultMean;
  const float upperDelta = 1.0f - resultMean;
  const float linearDelta = 0.5f - resultMean;
  const float resultVariance = lowerMass * lowerDelta * lowerDelta
    + upperMass * upperDelta * upperDelta
    + linearMass * (linearDelta * linearDelta + 1.0f / 12.0f);
  return float2(saturate(resultMean), max(resultVariance, 0.0f));
}

// Raw-moment variance uses two explicitly rounded operations on every target.
[ForceInline]
float cloudRawVariance(float mean, float secondMoment)
{
  precise float square = mean * mean;
  precise float difference = secondMoment - square;
  return max(difference, 0.0f);
}

[ForceInline]
public float2 cloudThresholdMoments(float mean, float secondMoment, float threshold, float rampWidth)
{
  const float2 statistics = cloudThresholdStatistics(mean, cloudRawVariance(mean, secondMoment),
    threshold, rampWidth);
  return float2(statistics.x, statistics.x * statistics.x + statistics.y);
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
  public float3 shapePhase;
  public float2 familyCoverage;
  public float2 familyVariance;
  public float2 familyBase;
  public float2 familyThickness;
}

struct CloudWeatherSample
{
  float4 mean;
  float2 variance;
};

[ForceInline]
CloudWeatherSample cloudWeatherSample(Sampler2D<float4> weatherSampler, float2 uv, float lod)
{
  CloudWeatherSample result = {};
  if (lod <= 0)
  {
    result.mean = weatherSampler.SampleLevel(uv, 0);
    return result;
  }

  // Neighboring children estimate unresolved variation of each family.
  // A constant mask has zero variance at every footprint.
  // Collapse the child footprint continuously onto the resolved center tap.
  const float offset = 0.25f * exp2(lod) * saturate(lod) / float(kCloudWeatherResolution);
  const float childLod = max(0.0f, lod - 1.0f);
  const float4 a = weatherSampler.SampleLevel(uv + float2(-offset, -offset), childLod);
  const float4 b = weatherSampler.SampleLevel(uv + float2(offset, -offset), childLod);
  const float4 c = weatherSampler.SampleLevel(uv + float2(-offset, offset), childLod);
  const float4 d = weatherSampler.SampleLevel(uv + float2(offset, offset), childLod);
  result.mean = 0.5f * (0.5f * (a + b) + 0.5f * (c + d));
  const float2 da = a.rg - result.mean.rg;
  const float2 db = b.rg - result.mean.rg;
  const float2 dc = c.rg - result.mean.rg;
  const float2 dd = d.rg - result.mean.rg;
  result.variance = 0.25f * (da * da + db * db + dc * dc + dd * dd);
  return result;
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
  const CloudWeatherSample weather = cloudWeatherSample(weatherSampler, position / float(kCloudWeatherPeriod), lod);
  const float precipitation = max(args.weather, args.thunder);
  const float bias = (args.coverage - 0.45f) * 0.9f + 0.51f * args.weather
    + 0.15f * args.thunder - 0.17f * args.night * (1.0f - args.weather);
  const float type = saturate(weather.mean.b * (1.0f - 0.4f * args.weather) + 0.85f * args.thunder);
  const float development = smoothstep(0.15f, 0.85f, type);
  const float cumulusMean = weather.mean.r + bias;
  const float deckMean = weather.mean.g + bias;
  const float2 cumulus = cloudThresholdStatistics(cumulusMean, weather.variance.x, 0, 1);
  const float2 deck = cloudThresholdStatistics(deckMean, weather.variance.y, 0, 1);

  CloudColumn column;
  column.coverage = max(cumulus.x, deck.x);
  column.type = type;
  column.familyCoverage = float2(cumulus.x, deck.x);
  column.familyVariance = float2(cumulus.y, deck.y);
  // Convective bodies and spreading decks coexist at distinct condensation
  // levels within the transport shell. Their extents remain independently bounded.
  column.familyBase = args.thickness * float2(0.02f + 0.04f * (1.0f - development),
    lerp(0.42f + 0.10f * development, 0.06f, precipitation));
  column.familyThickness = args.thickness * float2((0.28f + 0.60f * development) * (0.65f + 0.35f * cumulus.x),
    lerp(0.26f - 0.08f * development, 0.38f, precipitation) * (0.75f + 0.25f * deck.x));
  column.thickness = max(cumulus.x > 0 ? column.familyBase.x + column.familyThickness.x : 0,
    deck.x > 0 ? column.familyBase.y + column.familyThickness.y : 0);
  column.shapePhase = column.coverage > 0 ? cloudBillowPhase(position / float(kCloudBasePeriod)) : float3(0);
  return column;
}

[ForceInline]
public float cloudColumnThickness(CloudDensityArgs args, CloudColumn column)
{
  // Empty columns still need nonzero support for the lighting quadrature.
  return column.thickness > 0 ? column.thickness : args.thickness;
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
float cloudFamilyDensity(float4 body, float profile, float coverage, float variance,
  float erosion, float rampWidth)
{
  // Stretch the body spectrum before thresholding so humid parent groups still
  // contain individual billows instead of saturating into a featureless slab.
  const float mean = (body.r - 0.40f) / 0.60f;
  const float bodyVariance = cloudRawVariance(body.r, body.g) / 0.36f;
  return cloudThresholdStatistics(mean * profile, bodyVariance * profile * profile + variance,
    1.0f - coverage + erosion, rampWidth).x;
}

[ForceInline]
public float cloudDensityInColumn(CloudDensityArgs args, float3 coordinates, CloudColumn column,
  Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler, float footprint, float heightFootprint)
{
  const float heightAboveBase = coordinates.y * args.shapeScale - args.baseHeight;
  if (args.thickness <= 0 || column.coverage <= 0 || heightAboveBase + 0.5f * heightFootprint <= 0
    || heightAboveBase - 0.5f * heightFootprint >= args.thickness)
  {
    return 0;
  }
  const float2 height = (heightAboveBase - column.familyBase) / column.familyThickness;
  const float2 profileFootprint = heightFootprint / column.familyThickness;
  // Give both cloud families a more gradual condensation edge. The wider
  // lower fade softens dense cloud bases without flattening their upper billows.
  const float cumulusProfile = column.familyCoverage.x > 0
    ? cloudHeightProfile(height.x, 0.25f, lerp(0.30f, 0.70f, column.type), profileFootprint.x) : 0;
  const float deckProfile = column.familyCoverage.y > 0
    ? cloudHeightProfile(height.y, 0.28f, 0.70f, profileFootprint.y) : 0;
  if (cumulusProfile <= 0 && deckProfile <= 0)
  {
    return 0;
  }

  const float3 shapePosition = float3(coordinates.x, heightAboveBase / args.shapeScale, coordinates.z)
    + column.shapePhase * float(kCloudBasePeriod);
  const float detailPeriod = float(kCloudBasePeriod) * 0.0625f;
  const float detailLod = cloudNoiseLod(footprint, args.shapeScale * detailPeriod, float(kCloudDetailResolution));
  const float3 detail = detailSampler.SampleLevel(shapePosition / detailPeriod, detailLod).rgb;
  const float3 warpedPosition = shapePosition + (detail - 0.5f) * (0.04f * float(kCloudBasePeriod));
  const float billows = dot(detail, float3(0.625f, 0.25f, 0.125f));
  float density = 0;
  if (cumulusProfile > 0)
  {
    const float bodyPeriod = float(kCloudBasePeriod);
    const float3 bodyPosition = warpedPosition - float3(0, column.familyBase.x / args.shapeScale, 0);
    const float lod = cloudNoiseLod(footprint, args.shapeScale * bodyPeriod, float(kCloudBaseResolution));
    const float4 body = baseSampler.SampleLevel(bodyPosition / bodyPeriod, lod);
    const float erosion = lerp(billows, 1.0f - billows, saturate(height.x * 4.0f)) * 0.10f;
    density = cloudFamilyDensity(body, cumulusProfile, column.familyCoverage.x,
      column.familyVariance.x, erosion, 0.10f);
  }
  if (deckProfile > 0)
  {
    // Decks have broad horizontal cells and shallower vertical billows.
    const float3 bodyPeriod = float(kCloudBasePeriod) * float3(4, 1, 4);
    const float3 bodyPosition = warpedPosition - float3(0, column.familyBase.y / args.shapeScale, 0);
    const float lod = cloudNoiseLod(footprint, args.shapeScale * float(kCloudBasePeriod), float(kCloudBaseResolution));
    const float4 body = baseSampler.SampleLevel(bodyPosition / bodyPeriod, lod);
    const float erosion = lerp(billows, 1.0f - billows, saturate(height.y * 4.0f)) * 0.055f;
    density += cloudFamilyDensity(body, deckProfile, column.familyCoverage.y,
      column.familyVariance.y, erosion, 0.12f);
  }
  return saturate(density);
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
