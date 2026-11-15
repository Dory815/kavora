// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
#include "dxvk_display_color.h"
#include "rtx/pass/local_tonemap/local_tonemapping.slangh"
import "rtx/pass/srgb_dither/display_color_grade.slang";

StructuredBuffer<float4> Inputs;
RWStructuredBuffer<float4> Results;
uint Count;
uint Operation;

[shader("compute")]
[numthreads(64, 1, 1)]
void colorContracts(uint index : SV_DispatchThreadID)
{
  if (index >= Count)
  {
    return;
  }
  const float4 value = Inputs[index];
  float3 result = 0;
  switch (Operation)
  {
    case 0: result = displaySrgbEncode(value.rgb); break;
    case 1: result = displaySrgbDecode(value.rgb); break;
    case 2: result = displayPqEncodeNits(value.rgb); break;
    case 3: result = displayRec709ToRec2020(value.rgb); break;
    case 4: result = displayHdrShoulder(value.rgb, value.w); break;
    case 5: result = displaySdrShoulder(value.rgb, value.w); break;
    case 6:
    {
      const float encoded = encodeExposureLuminance(value.x, false, true);
      result = float3(encoded, decodeExposureLuminance(encoded, false, true),
        decodeExposureLuminance(value.y, false, true));
      break;
    }
    case 7:
      result = applyDisplayColor<false>(value.rgb, true, true, float3(1), 1, 1, 0, 0, 0, value.w > 0);
      break;
    case 8:
      result = applyDisplayColor<true>(value.rgb, true, false, float3(1), 1, 1, 0, 0, 0, value.w > 0);
      break;
    case 9: result = displaySanitizeColor(value.rgb); break;
  }
  Results[index] = float4(result, 1);
}
