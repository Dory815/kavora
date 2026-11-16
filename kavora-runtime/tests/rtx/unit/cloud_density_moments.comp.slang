// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
import "rtx/utility/cloud_density.slang";

StructuredBuffer<float4> Inputs;
RWStructuredBuffer<float2> Results;
uint Count;

[shader("compute")]
[numthreads(64, 1, 1)]
void main(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 sample = Inputs[index];
  Results[index] = cloudThresholdMoments(sample.x, sample.y, sample.z, sample.w);
}
