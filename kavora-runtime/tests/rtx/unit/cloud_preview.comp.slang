// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
import "rtx/algorithm/clouds.slang";
import "rtx/pass/cloud_parameters.slang";
import "rtx/pass/clouds/cloud_sky_transport.slang";

ConstantBuffer<CloudArgs> Clouds;
Sampler2D<float4>.Handle Weather;
Sampler3D<float4>.Handle Base;
Sampler3D<float4>.Handle Detail;
RWStructuredBuffer<float4> Results;
uint2 Size;
float3 Origin;
float3 Forward;
float3 Right;
float3 CameraUp;
float TanHalfFov;
float TopSpan;
float3 Ambient;
uint Projection;
uint Radiance;

[shader("compute")]
[numthreads(8, 8, 1)]
void main(uint2 pixel : SV_DispatchThreadID)
{
  if (any(pixel >= Size))
  {
    return;
  }
  const float2 uv = (float2(pixel) + 0.5f) / float2(Size) * 2.0f - 1.0f;
  const float aspect = float(Size.x) / float(Size.y);
  const float3 origin = Projection == 1
    ? Origin + Right * (uv.x * TopSpan * 0.5f) - CameraUp * (uv.y * TopSpan * 0.5f / aspect)
    : Origin;
  const float3 direction = Projection == 1 ? Forward
    : normalize(Forward + Right * (uv.x * aspect * TanHalfFov) - CameraUp * (uv.y * TanHalfFov));
  const Sampler2D<float4> weather = Sampler2D<float4>(Weather);
  const Sampler3D<float4> base = Sampler3D<float4>(Base);
  const Sampler3D<float4> detail = Sampler3D<float4>(Detail);

  if (Projection == 0 && Radiance == 0)
  {
    const float transmission = cloudTransmittance(Clouds, origin, direction, 3.402823466e+38f,
      weather, base, detail);
    Results[pixel.y * Size.x + pixel.x] = float4(0, 0, 0, transmission);
    return;
  }

  float2 intervals[4];
  [unroll]
  for (uint i = 0; i < 4; i++)
  {
    intervals[i] = cloudLayerInterval(Clouds, origin, direction,
      Projection == 1 ? 1000000.0f : cloudLayerMaxDistance(Clouds, i / 2), i / 2, i % 2);
  }
  float3 radiance = 0;
  float transmission = 1;
  float opticalDepth = 0;
  for (uint intervalIndex = 0; intervalIndex < 4; intervalIndex++)
  {
    uint nearest = 0;
    [unroll]
    for (uint i = 1; i < 4; i++)
    {
      if (intervals[i].x < intervals[nearest].x)
      {
        nearest = i;
      }
    }
    const CloudRayGrid grid = { intervals[nearest], cloudSampleSpacing(Clouds, direction, nearest / 2) };
    intervals[nearest].x = 3.402823466e+38f;
    float previous = grid.interval.x;
    for (uint cell = 0; previous < grid.interval.y; cell++)
    {
      const float next = grid.boundary(cell + 1);
      const float distance = grid.sampleAt(cell);
      const float3 position = origin + direction * distance;
      const float pixelFootprint = Projection == 1 ? TopSpan / float(Size.x) : Clouds.viewAngularFootprint * distance;
#if defined(CLOUD_PREVIEW_HAS_DENSITY_FOOTPRINT)
      const float footprint = cloudDensityFootprint(Clouds, direction, grid.spacing, pixelFootprint, nearest / 2);
#else
      const float footprint = max(grid.spacing, pixelFootprint);
#endif
#if defined(CLOUD_PREVIEW_HAS_CELL_SPAN)
      const float cellSpan = grid.spanAt(cell);
#else
      const float cellSpan = grid.spacing;
#endif
#if defined(CLOUD_PREVIEW_HAS_LAYER_HEIGHT_FOOTPRINT)
      const float heightFootprint = cloudHeightFootprint(Clouds, position, direction, cellSpan, pixelFootprint, nearest / 2);
#else
      const float heightFootprint = cloudHeightFootprint(Clouds, position, direction, cellSpan, pixelFootprint);
#endif
      const float extinction = Projection == 1
        ? cloudExtinction(Clouds, position, weather, base, detail, footprint, heightFootprint)
        : cloudViewExtinction(Clouds, position, distance, weather, base, detail, footprint, heightFootprint);
      opticalDepth += extinction * (next - previous);
      if (Radiance != 0 && extinction > 0)
      {
        accumulateCloudSkyStep(extinction, next - previous, Clouds.albedo,
          cloudIncidentRadiance(Clouds, position, direction, Ambient, weather, base, detail), radiance, transmission);
      }
      previous = next;
    }
  }
  Results[pixel.y * Size.x + pixel.x] = Radiance != 0
    ? float4(radiance, transmission) : float4(opticalDepth, 0, 0, exp(-opticalDepth));
}
