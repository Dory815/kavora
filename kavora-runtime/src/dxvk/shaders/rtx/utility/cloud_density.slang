/* SPDX-FileCopyrightText: Copyright (c) 2026 RTX Remix for Minecraft Community Edition contributors
 * SPDX-License-Identifier: Apache-2.0
 */
module cloud_density;

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
float2 cloudCoverageMoments(float shape, float secondMoment, float coverage)
{
  if (coverage <= 0)
  {
    return 0;
  }
  const float value = shape - 1.0f + coverage;
  const float width = sqrt(3.0f * max(secondMoment - shape * shape, 0.0f));
  if (width <= 1e-4f)
  {
    const float density = saturate(value / max(coverage, 1e-4f));
    return float2(density, density * density);
  }
  const float lower = saturate((value - width) / max(coverage, 1e-4f));
  const float upper = saturate((value + width) / max(coverage, 1e-4f));
  const float2 rampIntegral = float2(0.5f * (upper * upper - lower * lower),
    (upper * upper * upper - lower * lower * lower) / 3.0f) * coverage;
  const float plateau = max(value + width - max(coverage, value - width), 0.0f);
  return saturate((rampIntegral + plateau) / (2.0f * width));
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
}

[ForceInline]
public CloudColumn cloudColumn(CloudDensityArgs args, float2 position, Sampler2D<float4> weatherSampler,
  float footprint = 0)
{
  const float lod = cloudNoiseLod(footprint, args.shapeScale * 16.0f, 512.0f);
  const float4 weather = weatherSampler.SampleLevel(position / 16.0f, lod);
  const float bias = (args.coverage - 0.45f) * 0.9f - 0.18f + 0.51f * args.weather
    + 0.15f * args.thunder - 0.17f * args.night * (1.0f - args.weather);
  const float variance = max(weather.g - weather.r * weather.r, 0.0f);
  const float mean = weather.r + bias;
  const float2 coverage = cloudCoverageMoments(mean, mean * mean + variance, 1.0f);
  const float type = saturate(weather.b * (1.0f - 0.4f * args.weather) + 0.85f * args.thunder);
  const float thickness = args.thickness * ((140.0f + 460.0f * smoothstep(0.1f, 0.6f, type)
    + 900.0f * smoothstep(0.72f, 1.0f, type)) / 1500.0f);
  return { coverage.x, type, thickness, max(coverage.y - coverage.x * coverage.x, 0.0f) };
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
float overcastDensity(CloudDensityArgs args, float heightAboveBase, float cloudType, float heightFootprint)
{
  const float precipitation = max(args.weather, args.thunder);
  if (precipitation <= 0)
  {
    return 0;
  }

  // A continuous, stratiform layer forms beneath the taller cloud cells as rain sets in.
  const float layerThickness = cloudOvercastThickness(args, cloudType);
  const float height = heightAboveBase / layerThickness;
  const float profile = cloudHeightProfile(height, 0.16f, 0.65f, heightFootprint / layerThickness);
  return precipitation * lerp(0.36f, 0.47f, args.thunder) * profile;
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
  const float weatherLod = cloudNoiseLod(footprint, args.shapeScale * 16.0f, 512.0f);
  const float4 weather = weatherSampler.SampleLevel(p.xz / 16.0f, weatherLod);
  const float coverage = saturate(args.highCoverage);
  const float amount = coverage * (2.0f - coverage);
  const float regionalAmount = lerp(amount * amount, amount * (2.0f - amount), weather.b);
  const float profile = cloudHeightProfile(height, 0.15f, 0.65f, profileFootprint);
  // Regional amount is monotone in coverage and linear in filtered weather.
  // Finished fibres fade without applying another threshold to their mip chain.
  return weather.a * regionalAmount * profile;
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
  const float overcast = overcastDensity(args, heightAboveBase, column.type, heightFootprint);
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
  const float baseLod = cloudNoiseLod(footprint, args.shapeScale, 128.0f);
  const float4 base = baseSampler.SampleLevel(p, baseLod);
  const float coverageVariance = column.coverageVariance * coverageScale * coverageScale;
  const float2 density = cloudCoverageMoments(base.r, base.g + coverageVariance, coverage);
  if (density.x * profile <= overcast)
  {
    return overcast;
  }
  const float detailLod = cloudNoiseLod(footprint, args.shapeScale * 0.25f, 32.0f);
  const float3 detail = detailSampler.SampleLevel(p * 4.0f, detailLod).rgb;
  const float billows = dot(detail, float3(0.625f, 0.25f, 0.125f));
  const float erosion = lerp(billows, 1.0f - billows, saturate(height * 4.0f)) * 0.18f;
  // The polynomial erosion integrates directly from the two coverage moments.
  const float eroded = (1.0f - erosion) * density.x + erosion * density.y;
  return max(overcast, eroded * profile);
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
