// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
#include "rtx/utility/cloud_noise.slangh"

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
void noiseGradient(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 sample = Inputs[index];
  const uint period = uint(sample.z);
  const float slice = period == 2 ? 0.37f : 0.71f;
  const uint seed = kCloudNoiseSeed + (period == 2 ? 401u : 419u);
  const float2 derivative = cloudPerlinGradient2D(sample.xy, period, slice, seed);
  const float dx = cloudPerlin(float3((sample.xy + float2(sample.w, 0)) * float(period), slice), period, seed)
    - cloudPerlin(float3((sample.xy - float2(sample.w, 0)) * float(period), slice), period, seed);
  const float dy = cloudPerlin(float3((sample.xy + float2(0, sample.w)) * float(period), slice), period, seed)
    - cloudPerlin(float3((sample.xy - float2(0, sample.w)) * float(period), slice), period, seed);
  Results[index] = float4(derivative, float2(dx, dy) / (2.0f * sample.w));
}

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
