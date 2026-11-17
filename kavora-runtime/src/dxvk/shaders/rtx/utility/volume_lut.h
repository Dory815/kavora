/* SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
 * SPDX-License-Identifier: MIT
 */
#pragma once

#ifdef __cplusplus
#include <algorithm>
#include <cmath>
namespace dxvk {
#define LUT_EXP std::exp
#define LUT_LOG std::log
#define LUT_MIN std::min
#define LUT_MAX std::max
#else
#define LUT_EXP exp
#define LUT_LOG log
#define LUT_MIN min
#define LUT_MAX max
#endif

// Returns 1 - exp(-depth) without cancellation near zero.
inline float volumeLutOpacity(float depth) {
  depth = LUT_MAX(depth, 0.0f);
  return depth < 0.01f
    ? depth * (1.0f - depth * (0.5f - depth * (1.0f / 6.0f - depth / 24.0f)))
    : 1.0f - LUT_EXP(-depth);
}

// Interpolates a homogeneous cell in optical depth, not in display color.
inline float volumeLutWeight(float depth, float fraction) {
  fraction = LUT_MIN(LUT_MAX(fraction, 0.0f), 1.0f);
  if (fraction == 0.0f || fraction == 1.0f) {
    return fraction;
  }
  depth = LUT_MAX(depth, 0.0f);
  return depth < 1e-5f ? fraction
    : volumeLutOpacity(depth * fraction) / volumeLutOpacity(depth);
}

inline float volumeLutLog1p(float value) {
  return value < 0.01f
    ? value * (1.0f - value * (0.5f - value * (1.0f / 3.0f - value * 0.25f)))
    : LUT_LOG(1.0f + value);
}

inline float volumeLutExpm1(float value) {
  return value < 0.01f
    ? value * (1.0f + value * (0.5f + value * (1.0f / 6.0f + value / 24.0f)))
    : LUT_EXP(value) - 1.0f;
}

// Maps finite distances to a logarithmic grid without a zero-distance singularity.
inline float volumeLutCoordinate(float distance, float end, float scale) {
  scale = LUT_MAX(scale, 1e-4f);
  end = LUT_MAX(end, 0.0f);
  if (end == 0.0f) {
    return 0.0f;
  }
  distance = LUT_MIN(LUT_MAX(distance, 0.0f), end);
  return volumeLutLog1p(distance / scale) / volumeLutLog1p(end / scale);
}

inline float volumeLutDistance(float fraction, float end, float scale) {
  if (fraction <= 0.0f || end <= 0.0f) {
    return 0.0f;
  }
  if (fraction >= 1.0f) {
    return end;
  }
  scale = LUT_MAX(scale, 1e-4f);
  return LUT_MIN(end, scale * volumeLutExpm1(fraction * volumeLutLog1p(end / scale)));
}

// Stored prefixes may be opaque. Never divide by their transmittance.
inline float volumeLutRadiance(float from, float to, float fromDepth, float toDepth, float fraction) {
  return from + (to - from) * volumeLutWeight(LUT_MAX(toDepth - fromDepth, 0.0f), fraction);
}

#undef LUT_EXP
#undef LUT_LOG
#undef LUT_MIN
#undef LUT_MAX
#ifdef __cplusplus
}
#endif
