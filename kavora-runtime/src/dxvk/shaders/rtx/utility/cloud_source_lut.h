// SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
// SPDX-License-Identifier: MIT
#pragma once

#define CLOUD_SOURCE_CASCADES 3u
#define CLOUD_SOURCE_LOW_NODES 16u
#define CLOUD_SOURCE_HIGH_NODES 2u
#define CLOUD_SOURCE_COMPONENTS 3u
#define CLOUD_SOURCE_VERTICAL_NODES (CLOUD_SOURCE_LOW_NODES + CLOUD_SOURCE_HIGH_NODES)

#ifdef __cplusplus
#include <algorithm>
#include <cmath>
namespace dxvk {
#define CLOUD_SOURCE_UINT unsigned
#define CLOUD_SOURCE_SQRT std::sqrt
#define CLOUD_SOURCE_MIN std::min
#define CLOUD_SOURCE_MAX std::max
#else
#define CLOUD_SOURCE_UINT uint
#define CLOUD_SOURCE_SQRT sqrt
#define CLOUD_SOURCE_MIN min
#define CLOUD_SOURCE_MAX max
#endif

inline CLOUD_SOURCE_UINT cloudSourceResolution(CLOUD_SOURCE_UINT lightSteps) {
  return 4u * CLOUD_SOURCE_MIN(CLOUD_SOURCE_MAX(lightSteps, 4u), 16u);
}

inline CLOUD_SOURCE_UINT cloudSourceAtlasWidth(CLOUD_SOURCE_UINT resolution) {
  return CLOUD_SOURCE_MAX(1u, resolution * CLOUD_SOURCE_VERTICAL_NODES);
}

inline CLOUD_SOURCE_UINT cloudSourceAtlasHeight(CLOUD_SOURCE_UINT resolution) {
  return 1u + resolution * CLOUD_SOURCE_CASCADES * CLOUD_SOURCE_COMPONENTS;
}

inline CLOUD_SOURCE_UINT cloudSourceAtlasX(CLOUD_SOURCE_UINT x, CLOUD_SOURCE_UINT z, CLOUD_SOURCE_UINT resolution) {
  return x + resolution * z;
}

inline CLOUD_SOURCE_UINT cloudSourceAtlasY(CLOUD_SOURCE_UINT y, CLOUD_SOURCE_UINT cascade,
  CLOUD_SOURCE_UINT component, CLOUD_SOURCE_UINT resolution) {
  return 1u + y + resolution * (component + CLOUD_SOURCE_COMPONENTS * cascade);
}

inline float cloudSourceHenyeyGreenstein(float cosine, float anisotropy) {
  const float g = anisotropy;
  const float denominator = CLOUD_SOURCE_MAX(1.0f + g * g - 2.0f * g * cosine, 0.001f);
  return (1.0f - g * g) / (4.0f * 3.14159265359f * denominator * CLOUD_SOURCE_SQRT(denominator));
}

inline float cloudSourcePhase(float cosine, float anisotropy) {
  return 0.85f * cloudSourceHenyeyGreenstein(cosine, anisotropy)
    + 0.15f * cloudSourceHenyeyGreenstein(cosine, -0.25f);
}

inline float cloudSourceRadius(float shapeScale, float viewRange, CLOUD_SOURCE_UINT cascade) {
  const float range = CLOUD_SOURCE_MAX(viewRange, 4.0f * shapeScale);
  const float nearRadius = CLOUD_SOURCE_MIN(range, 4.0f * shapeScale);
  return cascade == 0 ? nearRadius
    : (cascade == 1 ? CLOUD_SOURCE_MIN(range, 4.0f * nearRadius) : range);
}

// Solves |horizontal + (R + height) up| = R + altitude without subtracting R twice.
inline float cloudSourcePlaneHeight(float radius, float horizontalSquared, float altitude) {
  const float radial = radius + altitude;
  return altitude - horizontalSquared
    / (CLOUD_SOURCE_SQRT(CLOUD_SOURCE_MAX(radial * radial - horizontalSquared, 0.0f)) + radial);
}

#undef CLOUD_SOURCE_UINT
#undef CLOUD_SOURCE_SQRT
#undef CLOUD_SOURCE_MIN
#undef CLOUD_SOURCE_MAX
#ifdef __cplusplus
}
#endif
