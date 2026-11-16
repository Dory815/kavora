// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
import "rtx/algorithm/clouds.slang";
import "rtx/pass/cloud_parameters.slang";
import "rtx/pass/clouds/cloud_sky_transport.slang";
import "rtx/utility/cloud_density.slang";

ConstantBuffer<CloudArgs> Clouds;
StructuredBuffer<float4> Inputs;
StructuredBuffer<float4> Directions;
RWStructuredBuffer<float4> Results;
Sampler2D<float4>.Handle Weather;
Sampler3D<float4>.Handle Base;
Sampler3D<float4>.Handle Detail;
uint Count;

[shader("compute")]
[numthreads(64, 1, 1)]
void homogeneous(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 sample = Inputs[index];
  const uint steps = uint(sample.w);
  float3 radiance = 0;
  float transmittance = 1;
  for (uint step = 0; step < steps; step++)
  {
    accumulateCloudSkyStep(sample.x, sample.y / float(steps), sample.z, float3(1, 2, 4),
      radiance, transmittance);
  }
  Results[index] = float4(radiance, transmittance);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void intervals(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float2 interval = cloudInterval(Clouds, Inputs[index].xyz, Directions[index].xyz, Inputs[index].w);
  Results[index] = float4(interval, 0, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void layerIntervals(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 ray = Inputs[index];
  const float4 direction = Directions[index];
  const uint layer = uint(direction.w);
  Results[index] = float4(cloudLayerInterval(Clouds, ray.xyz, direction.xyz, ray.w, layer, 0),
    cloudLayerInterval(Clouds, ray.xyz, direction.xyz, ray.w, layer, 1));
}

[shader("compute")]
[numthreads(64, 1, 1)]
void lightProfiles(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  Results[index] = float4(cloudLightIrradiance(Clouds.lights[0], Inputs[index].x), 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void densities(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 sample = Inputs[index];
  const float density = cloudExtinction(Clouds, sample.xyz, Sampler2D<float4>(Weather),
    Sampler3D<float4>(Base), Sampler3D<float4>(Detail), sample.w)
    / max(max(Clouds.extinction, Clouds.highExtinction), 1e-20f);
  Results[index] = float4(density, 0, 0, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void columnPhases(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  CloudDensityArgs args = {};
  args.shapeScale = Clouds.shapeScale;
  args.thickness = Clouds.thickness;
  args.coverage = Clouds.coverage;
  args.weather = Clouds.weather;
  args.thunder = Clouds.thunder;
  args.night = Clouds.night;
  const float4 input = Inputs[index];
  const CloudColumn column = cloudColumn(args, input.xz / args.shapeScale, Sampler2D<float4>(Weather), input.w);
  Results[index] = float4(column.shapePhase, column.coverage);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void visibility(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 origin = Inputs[index];
  const float transmission = cloudVisibilityTransmittance(Clouds, origin.xyz, Directions[index].xyz, origin.w,
    Sampler2D<float4>(Weather), Sampler3D<float4>(Base), Sampler3D<float4>(Detail));
  Results[index] = float4(transmission, 0, 0, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void lightDepthParts(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 ray = Inputs[index];
  const float4 direction = Directions[index];
  const float2 depth = cloudLightOpticalDepth(Clouds, ray.xyz, direction.xyz, ray.w,
    Sampler2D<float4>(Weather), Sampler3D<float4>(Base), Sampler3D<float4>(Detail), direction.w);
  Results[index] = float4(depth, cloudLowLightSupportLength(Clouds), 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void viewTransmission(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 origin = Inputs[index];
  const float3 direction = Directions[index].xyz;
  const float transmission = cloudTransmittance(Clouds, origin.xyz, direction, origin.w,
    Sampler2D<float4>(Weather), Sampler3D<float4>(Base), Sampler3D<float4>(Detail));
  Results[index] = float4(transmission, cloudSampleSpacing(Clouds, direction, 1), 0, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void emptyLightSupports(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 ray = Inputs[index];
  const float3 direction = Directions[index].xyz;
  CloudDensityArgs densityArgs = {};
  densityArgs.groundReference = Clouds.groundReference;
  densityArgs.up = Clouds.up;
  densityArgs.planetRadius = Clouds.planetRadius;
  const float span = cloudLowLightSupportLength(Clouds);
  const uint2 empty = cloudLowLightEmptySupports(Clouds, ray.xyz, direction, ray.w, span);
  float maximumProfileHeight = -1e30f;
  uint count = 0;
  for (uint tap = empty.x; tap < empty.y; tap++)
  {
    const float offset = (tap & 1u) == 0 ? 0.21132486541f : 0.78867513459f;
    const float distance = (float(tap >> 1) + offset) * (2.0f * span);
    const float3 position = ray.xyz + direction * distance;
    // This is the production density's first exact zero condition.
    const float upper = cloudAltitude(densityArgs, position)
      + 0.5f * cloudHeightFootprint(Clouds, position, direction, span) - Clouds.baseHeight;
    maximumProfileHeight = max(maximumProfileHeight, upper);
    count++;
  }
  Results[index] = float4(count, maximumProfileHeight, empty.x, empty.y);
}
