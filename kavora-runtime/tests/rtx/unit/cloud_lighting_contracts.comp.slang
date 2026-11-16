// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
import "rtx/algorithm/clouds.slang";
import "rtx/algorithm/cloud_lighting_cache.slang";
import "rtx/pass/cloud_parameters.slang";
ConstantBuffer<CloudArgs> Clouds;
Sampler3D<float>.Handle Sun;
Sampler3D<float2>.Handle Column;
StructuredBuffer<float4> Origins;
StructuredBuffer<float4> Directions;
RWStructuredBuffer<float4> Results;
uint Count;

[shader("compute")]
[numthreads(64, 1, 1)]
void depths(uint index : SV_DispatchThreadID)
{
  if (index >= Count) return;
  CloudLightingCache cache = { Sampler3D<float>(Sun), Sampler3D<float>(Sun), Sampler3D<float2>(Column) };
  const float3 origin = Origins[index].xyz;
  const float3 endpoint = origin + Directions[index].xyz * Origins[index].w;
  float depth;
  const bool found = cloudCachedLightDepth(Clouds, cache, 0, origin, endpoint, depth);
  float2 horizontal;
  const bool columnFound = cloudCachedColumnCoordinate(Clouds, origin, horizontal);
  Results[index] = float4(depth, found ? 1.0f : 0.0f, columnFound ? 1.0f : 0.0f, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void columns(uint index : SV_DispatchThreadID)
{
  if (index >= Count) return;
  CloudLightingCache cache = { Sampler3D<float>(Sun), Sampler3D<float>(Sun), Sampler3D<float2>(Column) };
  const float height = Origins[index].x;
  const float cosine = Origins[index].y;
  const float distance = Origins[index].z;
  const float2 sample = cloudCachedColumn(Clouds, cache, float2(0.5f), height);
  const float projection = cloudCachedColumnProjection(Clouds, cache, float2(0.5f), height, cosine, distance);
  Results[index] = float4(sample, projection, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void grids(uint index : SV_DispatchThreadID)
{
  if (index >= Count) return;
  const float4 input = Origins[index];
  const CloudRayGrid grid = createCloudRayGrid(float2(input.x, input.y), input.z, input.w, uint(Directions[index].x));
  float maximumError = 0;
  float previous = grid.interval.x;
  for (uint cell = 0; cell < grid.cells; cell++)
  {
    const float middle = grid.sampleAt(cell);
    maximumError = max(maximumError, abs(float(grid.cellAt(middle)) - float(cell)));
    const float boundary = grid.boundary(cell + 1);
    if (boundary <= previous) maximumError = 100000;
    previous = boundary;
  }
  Results[index] = float4(grid.cells, previous, maximumError, grid.boundary(1) - input.x);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void lightIndices(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  Results[index] = float4(cloudCachedLightIndex(Clouds, Origins[index].xyz), 0, 0, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void energyParts(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  CloudLightingCache cache = { Sampler3D<float>(Sun), Sampler3D<float>(Sun), Sampler3D<float2>(Column) };
  const float3 origin = Origins[index].xyz;
  const float3 middle = origin + Directions[index].xyz * (Origins[index].w * Directions[index].w);
  const float3 endpoint = origin + Directions[index].xyz * Origins[index].w;
  float local;
  float external;
  float total;
  const bool a = cloudCachedLightDepth(Clouds, cache, 0, origin, middle, local);
  const bool b = cloudCachedLightDepth(Clouds, cache, 0, middle, endpoint, external);
  const bool c = cloudCachedLightDepth(Clouds, cache, 0, origin, endpoint, total);
  Results[index] = float4(local, external, total, (a && b && c) ? 1.0f : 0.0f);
}
