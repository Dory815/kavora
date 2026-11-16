/* SPDX-License-Identifier: MIT */
#pragma once

#include "rtx/utility/shader_types.h"

// World periods are expressed in units of CloudArgs.shapeScale.
static const uint kCloudBasePeriod = 2;
static const uint kCloudBaseResolution = 128;
static const uint kCloudDetailResolution = 32;
static const uint kCloudWeatherResolution = 1024;
static const uint kCloudWeatherPeriod = 64;
static const uint kCloudHighWeatherPeriod = 32;

struct CloudNoiseGenerationArgs {
  uint detail;
  uint padding0;
  uint padding1;
  uint padding2;
};
