// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT

StructuredBuffer<float4> Inputs;
RWStructuredBuffer<float4> Results;
uint Count;
uint display_transfer;
uint display_frame_index;
float source_paper_white_nits;
float source_peak_nits;
float target_paper_white_nits;
float target_peak_nits;

// Execute the exact GLSL present helper with Slang's equivalent vector types.
#define vec3 float3
#define uvec2 uint2
#include "dxvk_present_color.glsl"
#undef uvec2
#undef vec3

[shader("compute")]
[numthreads(64, 1, 1)]
void presentContracts(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  Results[index] = float4(presentDisplayColor(Inputs[index].rgb, uint2(index, 0)), 1);
}
