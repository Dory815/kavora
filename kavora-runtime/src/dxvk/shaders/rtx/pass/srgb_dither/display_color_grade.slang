// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION. All rights reserved.
// SPDX-License-Identifier: MIT
module display_color_grade;

import "rtx/utility/color_transfer.slang";
#include "dxvk_display_color.h"

// Receives linear post-tonemap RGB and returns linear graded RGB.
// The pass owns transfer encoding, dithering and the output alpha.
[ForceInline]
float3 gradeDisplayColor(float3 color, float3 balance, float contrast, float saturation, bool extendedSrgb)
{
  color *= balance;
  color = contrast * (color - 0.18f) + 0.18f;
  color = extendedSrgb ? max(color, 0.0f) : saturate(color);
  return lerp(calcBt709Luminance(color).xxx, color, saturation);
}

// The inversion works in display values even when the caller exports a linear image.
[ForceInline]
float3 invertDisplayColor(float3 linearColor, float amount, uint mode, float threshold, bool extendedSrgb)
{
  const float3 display = extendedSrgb ? displaySrgbEncode(displaySanitizeColor(linearColor))
    : linearToGamma(saturate(linearColor));
  const float3 negative = extendedSrgb ? max(1.0f - display, 0.0f) : 1.0f - display;
  const bool showNegative = mode == 0 || dot(display, float3(1.0f / 3.0f)) < threshold;
  return lerp(display, showNegative ? negative : float3(0.0f), amount);
}

[ForceInline]
public float3 applyDisplayColor<let Inversion : bool>(float3 linearColor, bool convertToSrgb,
  bool gradingEnabled, float3 balance, float contrast, float saturation,
  float inversionAmount, uint inversionMode, float inversionThreshold, bool extendedSrgb = false)
{
  if (gradingEnabled)
  {
    linearColor = gradeDisplayColor(linearColor, balance, contrast, saturation, extendedSrgb);
  }

  if (Inversion)
  {
    const float3 inverted = invertDisplayColor(linearColor, inversionAmount, inversionMode, inversionThreshold, extendedSrgb);
    return convertToSrgb ? inverted : (extendedSrgb ? displaySrgbDecode(inverted) : gammaToLinear(inverted));
  }
  return convertToSrgb ? (extendedSrgb ? displaySrgbEncode(linearColor) : linearToGamma(linearColor)) : linearColor;
}
