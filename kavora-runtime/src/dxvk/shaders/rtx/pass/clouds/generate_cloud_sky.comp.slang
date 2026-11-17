/* SPDX-License-Identifier: MIT */
import "cloud_sky_transport.slang";
import "rtx/utility/cloud_density.slang";
#include "rtx/pass/common_bindings.slangh"
#include "rtx/algorithm/scene_cloud_lighting.slangh"
#include "rtx/pass/clouds/cloud_sky_binding_indices.h"
#include "rtx/utility/math.slangh"
import "rtx/concept/camera/camera.slang";
import "rtx/algorithm/clouds.slang";
import "rtx/pass/cloud_parameters.slang";
import "rtx/algorithm/cloud_sky.slang";
#include "rtx/algorithm/environment_radiance.slangh"

layout(binding = CLOUD_SKY_BINDING_OUTPUT)
RWTexture2D<float4> CloudSky;
layout(binding = CLOUD_SKY_BINDING_DISTANCE_MOMENT_OUTPUT)
RWTexture2D<float> CloudSkyDistanceMoment;

[shader("compute")]
[numthreads(8, 8, 1)]
void main(uint2 pixel : SV_DispatchThreadID)
{
  const CloudArgs args = cb.volumeArgs.clouds;
  const uint2 extent = uint2(args.skyResolution * 2, args.skyResolution);
  if (any(pixel >= extent))
  {
    return;
  }
  const float3 direction = cloudSkyDirection((float2(pixel) + 0.5f) / float2(extent), args.up);
  const float3 origin = cameraGetWorldPosition(cb.camera);
  float2 intervals[4];
  bool hasCloud = false;
  [unroll]
  for (uint i = 0; i < 4; i++)
  {
    intervals[i] = cloudLayerInterval(args, origin, direction, cloudLayerMaxDistance(args, i / 2), i / 2, i % 2);
    hasCloud = hasCloud || intervals[i].y > intervals[i].x;
  }
  if (!hasCloud)
  {
    CloudSky[pixel] = float4(0, 0, 0, 1);
    CloudSkyDistanceMoment[pixel] = 0;
    return;
  }
  const float3 ambient = sampleCloudAmbientRadiance(args);
  const CloudRayPhase cloudPhase = createCloudRayPhase(args, direction);
  float3 radiance = 0;
  float transmittance = 1;
  float distanceMoment = 0;
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
    const CloudRayGrid grid = createCloudRayGrid(intervals[nearest], cloudSampleSpacing(args, direction, nearest / 2),
      3.14159265359f / float(args.skyResolution), args.steps);
    intervals[nearest].x = 3.402823466e+38f;
    float previous = grid.interval.x;
    for (uint cell = 0; previous < grid.interval.y; cell++)
    {
      const float next = grid.boundary(cell + 1);
      const float distance = grid.sampleAt(cell);
      const float3 position = origin + direction * distance;
      const float pixelFootprint = distance * 3.14159265359f / float(args.skyResolution);
      const float footprint = cloudDensityFootprint(args, direction, grid.spanAt(cell), pixelFootprint, nearest / 2);
      const float extinction = cloudViewExtinction(args, position, distance, CloudWeatherSampler, CloudBaseSampler,
        CloudDetailSampler, footprint, cloudHeightFootprint(args, position, direction, grid.spanAt(cell), pixelFootprint, nearest / 2));
      if (extinction > 0)
      {
        const float opacity = accumulateCloudSkyStep(extinction, next - previous, args.albedo,
          cloudIncidentRadiance(args, position, direction, ambient, CloudWeatherSampler, CloudBaseSampler,
            CloudDetailSampler, sceneCloudLightingCache(), cloudPhase), radiance, transmittance);
        distanceMoment += opacity * distance;
      }
      if (transmittance < kOpaqueCloudTransmittance)
      {
        break;
      }
      previous = next;
    }
    if (transmittance < kOpaqueCloudTransmittance)
    {
      break;
    }
  }
  CloudSky[pixel] = float4(radiance, transmittance);
  CloudSkyDistanceMoment[pixel] = distanceMoment / cloudMaxViewDistance(args);
}
