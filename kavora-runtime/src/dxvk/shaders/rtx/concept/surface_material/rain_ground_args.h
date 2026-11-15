// SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
// SPDX-License-Identifier: MIT
#pragma once

#include "rtx/utility/shader_types.h"

#ifdef __cplusplus
constexpr int kRainGroundGridSize = 256;
#else
static const int kRainGroundGridSize = 256;
#endif

struct RainGroundArgs {
  ivec2 origin;
  float rain;
  float rippleStrength;
};
