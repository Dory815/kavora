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
#define LUT_UINT unsigned
#define LUT_MUTATING
#else
#define LUT_EXP exp
#define LUT_LOG log
#define LUT_MIN min
#define LUT_MAX max
#define LUT_UINT uint
#define LUT_MUTATING [mutating]
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

struct VolumeLutIntervals {
  float starts[7];
  float ends[7];
};

// Knots are budgeted inside each medium, including exact entry and exit planes.
// Capacity must be at least 32. Slots match AtmosphereIntervals.
struct VolumeLutGrid {
  float end;
  float scale;
  LUT_UINT nextNode[7];

  LUT_MUTATING
  float next(VolumeLutIntervals intervals, float previous, LUT_UINT capacity) {
    const LUT_UINT budget = capacity - 8u;
    const LUT_UINT small = budget / 10u;
    const LUT_UINT low = budget / 2u;
    const LUT_UINT air = budget - low - 3u * small;
    const LUT_UINT lowCount = LUT_UINT(intervals.ends[1] > intervals.starts[1])
      + LUT_UINT(intervals.ends[2] > intervals.starts[2]);
    const LUT_UINT highCount = LUT_UINT(intervals.ends[3] > intervals.starts[3])
      + LUT_UINT(intervals.ends[4] > intervals.starts[4]);
    float nextDistance = end;
    for (LUT_UINT interval = 0; interval < 7; ++interval) {
      const float begin = intervals.starts[interval];
      const float finish = intervals.ends[interval];
      if (finish <= begin || finish <= previous) {
        continue;
      }
      const LUT_UINT cells = interval == 6 ? air
        : (interval == 1 || interval == 2 ? low / LUT_MAX(lowCount, 1u)
        : (interval == 3 || interval == 4 ? small / LUT_MAX(highCount, 1u) : small));
      for (; nextNode[interval] <= cells; ++nextNode[interval]) {
        const LUT_UINT index = nextNode[interval];
        const float fraction = float(index) / float(cells);
        const float span = finish - begin;
        const float offset = interval == 0 || interval == 5
          ? volumeLutDistance(fraction, span, scale)
          : span * (interval == 3 || interval == 4 ? fraction : fraction * fraction);
        const float distance = index == cells ? finish : begin + offset;
        if (distance > previous) {
          nextDistance = LUT_MIN(nextDistance, distance);
          break;
        }
      }
    }
    return LUT_MAX(previous, nextDistance);
  }
};

inline VolumeLutGrid createVolumeLutGrid(VolumeLutIntervals intervals, float scale) {
  VolumeLutGrid grid = {};
  for (LUT_UINT interval = 0; interval < 7; ++interval) {
    grid.end = LUT_MAX(grid.end, intervals.ends[interval]);
  }
  grid.scale = LUT_MAX(scale, 1e-4f);
  return grid;
}

#undef LUT_EXP
#undef LUT_LOG
#undef LUT_MIN
#undef LUT_MAX
#undef LUT_UINT
#undef LUT_MUTATING
#ifdef __cplusplus
}
#endif
