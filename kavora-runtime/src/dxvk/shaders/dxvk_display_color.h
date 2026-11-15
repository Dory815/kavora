// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
#ifndef DXVK_DISPLAY_COLOR_H
#define DXVK_DISPLAY_COLOR_H

// Shared display math for native contracts, Slang post-processing and the GLSL presenter.
#ifdef __cplusplus
#include <algorithm>
#include <cmath>
namespace dxvk::display_color {
struct Rgb {
  float x;
  float y;
  float z;

  constexpr Rgb(float r, float g, float b) : x(r), y(g), z(b) { }
};
#define DISPLAY_COLOR_RGB Rgb
#define DISPLAY_COLOR_INLINE inline
#define DISPLAY_COLOR_ABS std::abs
#define DISPLAY_COLOR_POW std::pow
#define DISPLAY_COLOR_MIN std::min
#define DISPLAY_COLOR_MAX std::max
#elif defined(__SLANG__)
#define DISPLAY_COLOR_RGB float3
#define DISPLAY_COLOR_INLINE [ForceInline]
#define DISPLAY_COLOR_ABS abs
#define DISPLAY_COLOR_POW pow
#define DISPLAY_COLOR_MIN min
#define DISPLAY_COLOR_MAX max
#else
#define DISPLAY_COLOR_RGB vec3
#define DISPLAY_COLOR_INLINE
#define DISPLAY_COLOR_ABS abs
#define DISPLAY_COLOR_POW pow
#define DISPLAY_COLOR_MIN min
#define DISPLAY_COLOR_MAX max
#endif

DISPLAY_COLOR_INLINE
float displaySanitizeValue(float value)
{
  return value >= 0.0f && value <= 3.402823466e+38f ? value : 0.0f;
}

DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displaySanitizeColor(DISPLAY_COLOR_RGB color)
{
  return DISPLAY_COLOR_RGB(displaySanitizeValue(color.x), displaySanitizeValue(color.y), displaySanitizeValue(color.z));
}

// IEC sRGB transfer, with the sign extension specified by Khronos Data Format 13.3.4.
DISPLAY_COLOR_INLINE
float displaySrgbEncode(float linear)
{
  const float magnitude = DISPLAY_COLOR_ABS(linear);
  const float encoded = magnitude <= 0.0031308f ? 12.92f * magnitude
    : 1.055f * DISPLAY_COLOR_POW(magnitude, 1.0f / 2.4f) - 0.055f;
  return linear < 0.0f ? -encoded : encoded;
}

DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displaySrgbEncode(DISPLAY_COLOR_RGB linear)
{
  return DISPLAY_COLOR_RGB(displaySrgbEncode(linear.x), displaySrgbEncode(linear.y), displaySrgbEncode(linear.z));
}

DISPLAY_COLOR_INLINE
float displaySrgbDecode(float encoded)
{
  const float magnitude = DISPLAY_COLOR_ABS(encoded);
  const float linear = magnitude <= 0.04045f ? magnitude / 12.92f
    : DISPLAY_COLOR_POW((magnitude + 0.055f) / 1.055f, 2.4f);
  return encoded < 0.0f ? -linear : linear;
}

DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displaySrgbDecode(DISPLAY_COLOR_RGB encoded)
{
  return DISPLAY_COLOR_RGB(displaySrgbDecode(encoded.x), displaySrgbDecode(encoded.y), displaySrgbDecode(encoded.z));
}

// ITU-R BT.2087-0 Annex 1, M2. Both spaces use the D65 white point.
DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displayRec709ToRec2020(DISPLAY_COLOR_RGB color)
{
  return DISPLAY_COLOR_RGB(
    0.6274f * color.x + 0.3293f * color.y + 0.0433f * color.z,
    0.0691f * color.x + 0.9195f * color.y + 0.0114f * color.z,
    0.0164f * color.x + 0.0880f * color.y + 0.8956f * color.z);
}

// ITU-R BT.2100-3 Table 4 inverse EOTF. Input is display luminance in cd/m^2.
DISPLAY_COLOR_INLINE
float displayPqEncodeNits(float nits)
{
  const float m1 = 2610.0f / 16384.0f;
  const float m2 = 2523.0f / 32.0f;
  const float c1 = 3424.0f / 4096.0f;
  const float c2 = 2413.0f / 128.0f;
  const float c3 = 2392.0f / 128.0f;
  const float luminance = DISPLAY_COLOR_MIN(displaySanitizeValue(nits), 10000.0f) / 10000.0f;
  const float powered = DISPLAY_COLOR_POW(luminance, m1);
  return DISPLAY_COLOR_POW((c1 + c2 * powered) / (1.0f + c3 * powered), m2);
}

DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displayPqEncodeNits(DISPLAY_COLOR_RGB nits)
{
  return DISPLAY_COLOR_RGB(displayPqEncodeNits(nits.x), displayPqEncodeNits(nits.y), displayPqEncodeNits(nits.z));
}

DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displayScaleColor(DISPLAY_COLOR_RGB color, float scale)
{
  return DISPLAY_COLOR_RGB(color.x * scale, color.y * scale, color.z * scale);
}

// Scene RGB is exposed into paper-white units. A common scale preserves its color ratios.
DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displayHdrShoulder(DISPLAY_COLOR_RGB sceneColor, float peakToWhite)
{
  const DISPLAY_COLOR_RGB color = displaySanitizeColor(sceneColor);
  const float maximum = DISPLAY_COLOR_MAX(color.x, DISPLAY_COLOR_MAX(color.y, color.z));
  if (maximum <= 1.0f)
  {
    return color;
  }
  const float headroom = DISPLAY_COLOR_MAX(displaySanitizeValue(peakToWhite), 1.0f) - 1.0f;
  const float mapped = 1.0f + headroom / (1.0f + headroom / (maximum - 1.0f));
  return DISPLAY_COLOR_RGB((color.x / maximum) * mapped, (color.y / maximum) * mapped,
    (color.z / maximum) * mapped);
}

// An HDR frame presented on SDR reserves its upper quarter for highlights above paper white.
DISPLAY_COLOR_INLINE
DISPLAY_COLOR_RGB displaySdrShoulder(DISPLAY_COLOR_RGB displayColor, float sourcePeakToWhite)
{
  const DISPLAY_COLOR_RGB color = displaySanitizeColor(displayColor);
  const float maximum = DISPLAY_COLOR_MAX(color.x, DISPLAY_COLOR_MAX(color.y, color.z));
  const float knee = 0.75f;
  if (maximum <= knee)
  {
    return color;
  }
  const float peak = DISPLAY_COLOR_MAX(displaySanitizeValue(sourcePeakToWhite), 1.0f);
  const float compression = 1.0f / (1.0f - knee) - 1.0f / (peak - knee);
  const float mapped = DISPLAY_COLOR_MIN(knee + 1.0f / (1.0f / (maximum - knee) + compression), 1.0f);
  return DISPLAY_COLOR_RGB((color.x / maximum) * mapped, (color.y / maximum) * mapped,
    (color.z / maximum) * mapped);
}

#ifdef __cplusplus
}
#endif
#undef DISPLAY_COLOR_RGB
#undef DISPLAY_COLOR_INLINE
#undef DISPLAY_COLOR_ABS
#undef DISPLAY_COLOR_POW
#undef DISPLAY_COLOR_MIN
#undef DISPLAY_COLOR_MAX
#endif
