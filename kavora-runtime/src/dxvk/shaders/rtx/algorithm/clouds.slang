/* SPDX-License-Identifier: MIT */
module clouds;

import "rtx/pass/cloud_parameters.slang";
import "rtx/utility/cloud_density.slang";

static const float kFloatMax = 3.402823466e+38f;

[ForceInline]
CloudDensityArgs cloudDensityParameters(CloudArgs args)
{
  CloudDensityArgs density;
  density.groundReference = args.groundReference;
  density.up = args.up;
  density.planetRadius = args.planetRadius;
  density.windOffset = args.windOffset;
  density.shapeScale = args.shapeScale;
  density.baseHeight = args.baseHeight;
  density.thickness = args.thickness;
  density.coverage = args.coverage;
  density.weather = args.weather;
  density.thunder = args.thunder;
  density.night = args.night;
  density.highBaseHeight = args.highBaseHeight;
  density.highThickness = args.highThickness;
  density.highCoverage = args.highCoverage;
  return density;
}

float2 cloudSphereRoots(CloudArgs args, float3 origin, float3 direction, float altitude)
{
  const float3 p = origin - args.groundReference;
  const float h = dot(p, args.up);
  const float3 horizontal = p - h * args.up;
  const float b = dot(horizontal, direction) + (args.planetRadius + h) * dot(direction, args.up);
  const float c = dot(horizontal, horizontal) + (h - altitude) * (2.0f * args.planetRadius + h + altitude);
  const float discriminant = b * b - c;
  if (discriminant < 0)
  {
    return -1;
  }
  const float root = sqrt(discriminant);
  const float q = -b - (b >= 0 ? root : -root);
  if (abs(q) < 1e-6f)
  {
    return -b;
  }
  const float other = c / q;
  return float2(min(q, other), max(q, other));
}

[ForceInline]
bool cloudLayerEnabled(CloudArgs args, uint layer)
{
  return args.enable && (layer == 0 ? args.extinction > 0 && args.thickness > 0
    : args.highExtinction > 0 && args.highThickness > 0 && args.highCoverage > 0);
}

[ForceInline]
public float cloudLayerBase(CloudArgs args, uint layer)
{
  return layer == 0 ? args.baseHeight : args.highBaseHeight;
}

[ForceInline]
public float cloudLayerTop(CloudArgs args, uint layer)
{
  return cloudLayerBase(args, layer) + (layer == 0 ? args.thickness : args.highThickness);
}

[ForceInline]
public float cloudLayerMaxDistance(CloudArgs args, uint layer)
{
  return layer == 0 ? args.maxDistance : args.highMaxDistance;
}

[ForceInline]
public float cloudMaxViewDistance(CloudArgs args)
{
  return max(args.maxDistance, args.highMaxDistance);
}

// A grazing ray can cross a shell twice with clear air between the two intervals.
public float2 cloudLayerInterval(CloudArgs args, float3 origin, float3 direction, float distance,
  uint layer, uint segment = 0)
{
  if (!cloudLayerEnabled(args, layer))
  {
    return 0;
  }
  const float2 outer = cloudSphereRoots(args, origin, direction, cloudLayerTop(args, layer));
  const float begin = max(0.0f, outer.x);
  const float end = min(distance, outer.y);
  if (end <= begin)
  {
    return 0;
  }
  const float2 inner = cloudSphereRoots(args, origin, direction, cloudLayerBase(args, layer));
  if (inner.y <= begin || inner.x >= end)
  {
    return segment == 0 ? float2(begin, end) : float2(0);
  }
  if (inner.x <= begin)
  {
    const float entry = max(begin, inner.y);
    return segment == 0 && end > entry ? float2(entry, end) : float2(0);
  }
  const float2 interval = segment == 0 ? float2(begin, inner.x) : float2(inner.y, end);
  return interval.y > interval.x ? interval : float2(0);
}

[ForceInline]
public float2 cloudInterval(CloudArgs args, float3 origin, float3 direction, float distance)
{
  return cloudLayerInterval(args, origin, direction, min(distance, args.maxDistance), 0);
}

[ForceInline]
uint cloudLayerAt(CloudArgs args, float3 position)
{
  return args.highExtinction > 0 && args.highThickness > 0
    && cloudAltitude(cloudDensityParameters(args), position) >= args.highBaseHeight ? 1u : 0u;
}

public float cloudExtinction(CloudArgs args, float3 position, Sampler2D<float4> weatherSampler,
  Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler, float footprint = 0, float heightFootprint = 0)
{
  const uint layer = cloudLayerAt(args, position);
  const float extinction = layer == 0 ? args.extinction : args.highExtinction;
  return extinction * cloudDensity(cloudDensityParameters(args), position, weatherSampler,
    baseSampler, detailSampler, footprint, layer, heightFootprint);
}

[ForceInline]
public float cloudHeightFootprint(CloudArgs args, float3 position, float3 direction, float span,
  float pixelFootprint = 0)
{
  const float3 radial = position - args.groundReference + args.planetRadius * args.up;
  const float radialLength = length(radial);
  const float cosine = dot(direction, radial) / radialLength;
  const float sineSquared = saturate(1.0f - cosine * cosine);
  const float rayFootprint = abs(cosine) * span + sineSquared * span * span / (4.0f * radialLength);
  return max(rayFootprint, pixelFootprint * sqrt(sineSquared));
}

[ForceInline]
public float cloudViewExtinction(CloudArgs args, float3 position, float distance,
  Sampler2D<float4> weatherSampler, Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler, float footprint = 0,
  float heightFootprint = 0)
{
  const float maxDistance = cloudLayerMaxDistance(args, cloudLayerAt(args, position));
  const float visibility = 1.0f - smoothstep(0.5f, 1.0f, distance / maxDistance);
  return visibility * cloudExtinction(args, position, weatherSampler, baseSampler, detailSampler, footprint, heightFootprint);
}

public float cloudSampleSpacing(CloudArgs args, float3 direction, uint layer = 0)
{
  const float horizontalSpacing = args.shapeScale * (layer == 0 ? 2.5f : 8.0f) / float(args.steps);
  const float thickness = layer == 0 ? args.thickness : args.highThickness;
  const float verticalSpacing = thickness * 0.125f / max(abs(dot(direction, args.up)), 1e-4f);
  return min(horizontalSpacing, verticalSpacing);
}

public static const float kOpaqueCloudTransmittance = 1e-8f;

public struct VolumeCloud
{
  [ForceInline]
  public static float2 interval(CloudArgs args, float3 origin, float3 direction, uint layer = 0, uint segment = 0)
  {
    return args.transportMode == 0
      ? cloudLayerInterval(args, origin, direction, cloudLayerMaxDistance(args, layer), layer, segment) : float2(0);
  }

  [ForceInline]
  public static float transmittance(CloudArgs args, float3 origin, float3 direction, float distance,
    Sampler2D<float4> weather, Sampler3D<float4> base, Sampler3D<float4> detail)
  {
    return args.transportMode == 0 ? cloudTransmittance(args, origin, direction, distance, weather, base, detail) : 1.0f;
  }
};

// Clipped prefixes share the full ray's cells and density samples.
public struct CloudRayGrid
{
  public float2 interval;
  public float spacing;

  public uint cellAt(float distance)
  {
    return uint(floor(max(0.0f, distance - interval.x) / spacing));
  }

  public float boundary(uint index)
  {
    return min(interval.y, interval.x + float(index) * spacing);
  }

  public float sampleAt(uint index)
  {
    return 0.5f * (boundary(index) + boundary(index + 1));
  }

  public float spanAt(uint index)
  {
    return boundary(index + 1) - boundary(index);
  }
};

public float cloudTransmittance(CloudArgs args, float3 origin, float3 direction, float distance,
  Sampler2D<float4> weatherSampler, Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler)
{
  float transmittance = 1;
  for (uint layer = 0; layer < 2; layer++)
  {
    if (!cloudLayerEnabled(args, layer))
    {
      continue;
    }
    for (uint segment = 0; segment < 2; segment++)
    {
      const CloudRayGrid grid = {
        cloudLayerInterval(args, origin, direction, cloudLayerMaxDistance(args, layer), layer, segment),
        cloudSampleSpacing(args, direction, layer)
      };
      const float end = min(grid.interval.y, distance);
      float previous = grid.interval.x;
      for (uint cell = 0; previous < end; cell++)
      {
        const float next = min(end, grid.boundary(cell + 1));
        const float sampleDistance = grid.sampleAt(cell);
        const float3 position = origin + direction * sampleDistance;
        const float footprint = max(grid.spacing, args.viewAngularFootprint * sampleDistance);
        const float heightFootprint = cloudHeightFootprint(args, position, direction, grid.spanAt(cell),
          args.viewAngularFootprint * sampleDistance);
        const float extinction = cloudViewExtinction(args, position, sampleDistance,
          weatherSampler, baseSampler, detailSampler, footprint, heightFootprint);
        transmittance *= exp(-extinction * (next - previous));
        if (transmittance < kOpaqueCloudTransmittance)
        {
          return transmittance;
        }
        previous = next;
      }
    }
  }
  return transmittance;
}

[ForceInline]
float cloudLightSampleDepth(CloudArgs args, uint layer, float3 position, float3 direction, float span,
  Sampler2D<float4> weatherSampler, Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler)
{
  const float heightFootprint = cloudHeightFootprint(args, position, direction, span);
  const float extinction = layer == 0 ? args.extinction : args.highExtinction;
  return extinction * cloudDensity(cloudDensityParameters(args), position, weatherSampler, baseSampler, detailSampler,
    span, layer, heightFootprint) * span;
}

float cloudLightOpticalDepth(CloudArgs args, float3 origin, float3 direction, float distance,
  Sampler2D<float4> weatherSampler, Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler)
{
  float opticalDepth = 0;
  const float altitude = cloudAltitude(cloudDensityParameters(args), origin);
  for (uint layer = 0; layer < 2; layer++)
  {
    if (!cloudLayerEnabled(args, layer))
    {
      continue;
    }
    const float top = cloudLayerTop(args, layer);
    const float2 outer = cloudSphereRoots(args, origin, direction, top);
    float begin = max(0.0f, outer.x);
    if (altitude < cloudLayerBase(args, layer))
    {
      begin = max(begin, cloudSphereRoots(args, origin, direction, cloudLayerBase(args, layer)).y);
    }
    // Sunlit high-cloud rays remain above the dense lower atmosphere.
    const float lightRange = layer == 0 ? args.lightMaxDistance
      : 2.0f * sqrt(top * (2.0f * args.planetRadius + top));
    const float limit = layer == 0 ? min(distance, args.lightMaxDistance) : min(distance, begin + lightRange);
    const float end = min(limit, outer.y);
    if (end <= begin)
    {
      continue;
    }
    const float spacing = cloudSampleSpacing(args, direction, layer);
    const float stretch = log(1.0f + lightRange / spacing);
    const uint steps = layer == 0 ? args.lightSteps : max(4u, (args.lightSteps + 1) / 2);
    // Keep one grid through the inner clear-air gap as a ray crosses the shell's tangent.
    float previous = begin;
    for (uint i = 0; i < steps; i++)
    {
      const float boundary = begin + spacing * (exp(stretch * float(i + 1) / float(steps)) - 1.0f);
      const float next = min(end, boundary);
      const float t = (previous + next) * 0.5f;
      const float span = next - previous;
      // Use the unclipped width so moving the shell exit cannot switch quadrature rules.
      if (boundary - previous > args.shapeScale * 0.25f)
      {
        const float offset = span * 0.28867513459f;
        opticalDepth += cloudLightSampleDepth(args, layer, origin + direction * (t - offset), direction, 0.5f * span,
          weatherSampler, baseSampler, detailSampler);
        opticalDepth += cloudLightSampleDepth(args, layer, origin + direction * (t + offset), direction, 0.5f * span,
          weatherSampler, baseSampler, detailSampler);
      }
      else
      {
        opticalDepth += cloudLightSampleDepth(args, layer, origin + direction * t, direction, span,
          weatherSampler, baseSampler, detailSampler);
      }
      previous = next;
      if (previous >= end)
      {
        break;
      }
    }
  }
  return opticalDepth;
}

public float cloudVisibilityTransmittance(CloudArgs args, float3 origin, float3 direction, float distance,
  Sampler2D<float4> weatherSampler, Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler)
{
  return exp(-cloudLightOpticalDepth(args, origin, direction, distance, weatherSampler, baseSampler, detailSampler));
}

float cloudPhase(float cosine, float g)
{
  const float denominator = max(1.0f + g * g - 2.0f * g * cosine, 0.001f);
  return (1.0f - g * g) / (4.0f * 3.14159265359f * denominator * sqrt(denominator));
}

[ForceInline]
public float3 cloudLightIrradiance(CloudLight light, float altitude)
{
  if (!light.hasRadianceProfile)
  {
    return light.irradiance;
  }
  float4 lower = light.radianceProfile[0];
  [unroll]
  for (uint i = 1; i < 4; i++)
  {
    const float4 upper = light.radianceProfile[i];
    if (altitude <= upper.w)
    {
      const float fraction = saturate((altitude - lower.w) / max(upper.w - lower.w, 1e-4f));
      return lerp(lower.rgb, upper.rgb, fraction);
    }
    lower = upper;
  }
  return lower.rgb;
}

public float3 cloudIncidentRadiance(CloudArgs args, float3 position, float3 direction, float3 ambientRadiance,
  Sampler2D<float4> weatherSampler, Sampler3D<float4> baseSampler, Sampler3D<float4> detailSampler)
{
  float3 source = 0.0f;
  float skyTransmissionSum = 0;
  float skyPower = 0;
  const float precipitation = max(args.weather, args.thunder);
  const float altitude = cloudAltitude(cloudDensityParameters(args), position);
  for (uint lightIndex = 0; lightIndex < 2; lightIndex++)
  {
    const CloudLight light = args.lights[lightIndex];
    const float3 irradiance = cloudLightIrradiance(light, altitude);
    if (!any(irradiance > 0))
    {
      continue;
    }
    const float opticalDepth = cloudLightOpticalDepth(args, position, light.directionToLight, kFloatMax,
      weatherSampler, baseSampler, detailSampler);
    const float cosine = dot(direction, light.directionToLight);
    const float phase = 0.85f * cloudPhase(cosine, args.anisotropy) + 0.15f * cloudPhase(cosine, -0.25f);
    // The effective optical depths of successive orders differ by powers of two.
    const float transmission5 = exp(-opticalDepth * (1.0f / 16.0f));
    const float transmission4 = transmission5 * transmission5;
    const float transmission3 = transmission4 * transmission4;
    const float transmission2 = transmission3 * transmission3;
    const float transmission = transmission2 * transmission2;
    const float singleScattering = phase * transmission;
    const float scatteringProbability = 1.0f - transmission;
    float multipleScattering = 0;
    // Higher orders require another collision and vanish in the optically thin limit.
    float orderWeight = args.multipleScattering * scatteringProbability;
    const float meanCosine = 0.85f * args.anisotropy - 0.15f * 0.25f;
    float orderG = meanCosine;
    // Approximate diffuse incident light while preserving physical view extinction.
    // Successive phases retain the first moment of the full dual-lobe distribution.
    const float4 orderTransmission = float4(transmission2, transmission3, transmission4, transmission5);
    [unroll]
    for (uint order = 0; order < 4; order++)
    {
      orderG *= meanCosine;
      multipleScattering += orderWeight * cloudPhase(cosine, orderG) * orderTransmission[order];
      orderWeight *= args.multipleScattering * args.albedo * scatteringProbability;
    }
    // Eddington's conservative two-stream limit approximates the diffuse flux
    // through a thick droplet layer. Use it as the asymptote of the higher orders.
    const float lightCosine = saturate(dot(light.directionToLight, args.up));
    const float transportDepth = (1.0f - meanCosine) * opticalDepth * lightCosine;
    const float unscatteredTransmission = exp(-transportDepth);
    // Weight diffuse-sky attenuation by the light actually reaching this altitude.
    const float power = irradiance.x + irradiance.y + irradiance.z;
    skyTransmissionSum += power * unscatteredTransmission;
    skyPower += power;
    const float diffuseTransmission = rcp(1.0f + 0.75f * transportDepth);
    const float diffuseScattering = args.multipleScattering * lightCosine * (1.0f - unscatteredTransmission)
      * diffuseTransmission * (1.0f / 3.14159265359f);
    source += irradiance * (singleScattering + max(multipleScattering, diffuseScattering));
  }
  const float skyTransmission = skyPower > 0
    ? lerp(1.0f, skyTransmissionSum / skyPower, precipitation) : 1.0f;
  return source + ambientRadiance * skyTransmission;
}
