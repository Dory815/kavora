// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
import "rtx/algorithm/atmosphere.slang";

StructuredBuffer<float4> Inputs;
RWStructuredBuffer<float4> Results;
uint Count;
float MaxDistance;

[shader("compute")]
[numthreads(64, 1, 1)]
void moments(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 cell = Inputs[index];
  const float2 value = cloudCellMoments(cell.x, cell.y, cell.z, MaxDistance);
  Results[index] = float4(value, unpackCloudMoments(packCloudMoments(value)));
}

[shader("compute")]
[numthreads(64, 1, 1)]
void composition(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 cell = Inputs[index];
  const uint count = uint(cell.w);
  const float length = cell.z / float(count);
  AtmosphereSegment result = emptyAtmosphereSegment();
  for (uint step = 0; step < count; step++)
  {
    AtmosphereSegment segment = emptyAtmosphereSegment();
    // Chromatic fog attenuation must not change the cloud-only motion guide.
    segment.transmittance = float3(0.2f, 0.6f, 0.9f);
    segment.cloudMoments = cloudCellMoments(cell.x, cell.y + float(step) * length, length, MaxDistance);
    result = composeAtmosphereSegments(result, segment);
  }
  Results[index] = float4(result.cloudMoments, result.radiance.x, result.transmittance.x);
}
