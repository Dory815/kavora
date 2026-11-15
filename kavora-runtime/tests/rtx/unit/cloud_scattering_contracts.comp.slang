// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
import "rtx/algorithm/cloud_scattering.slang";
import "rtx/utility/cloud_density.slang";

StructuredBuffer<float4> Inputs;
RWStructuredBuffer<float4> Results;
uint Count;

[shader("compute")]
[numthreads(64, 1, 1)]
void boundaryRadiance(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 sample = Inputs[index];
  const float3 boundary = cloudDiffuseBoundaryRadiance(float3(0.25f, 1.5f, 8.0f), 0,
    sample.xy, sample.z);
  const float furnace = cloudDiffuseBoundaryRadiance(1.56f, 1.56f, sample.xy, sample.z).x;
  Results[index] = float4(boundary, furnace);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void beamRadiance(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 sample = Inputs[index];
  const float2 depth = sample.z >= 0 ? sample.xy : sample.yx;
  Results[index] = float4(cloudDiffuseBeamRadiance(depth, abs(sample.z)), 0, 0, 0);
}

[shader("compute")]
[numthreads(64, 1, 1)]
void columnSupport(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 sample = Inputs[index];
  CloudDensityArgs args = {};
  args.thickness = 1500.0f;
  args.weather = sample.y;
  args.thunder = sample.z;
  const CloudColumn column = { 1.0f, sample.x, sample.w, 0.0f };
  Results[index] = float4(cloudColumnThickness(args, column), 0, 0, 0);
}
