// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
//!variant generate_cloud_light_sun.comp CLOUD_LIGHT_INDEX=0
//!variant generate_cloud_light_moon.comp CLOUD_LIGHT_INDEX=1
//!variant generate_cloud_column.comp CLOUD_LIGHT_COLUMN
//!end-variants

import "rtx/algorithm/clouds.slang";
import "rtx/algorithm/cloud_lighting_cache.slang";
import "rtx/pass/cloud_parameters.slang";
import "rtx/utility/cloud_density.slang";
#include "rtx/pass/common_bindings.slangh"
#include "rtx/pass/clouds/cloud_lighting_binding_indices.h"

#ifdef CLOUD_LIGHT_COLUMN
layout(binding = CLOUD_COLUMN_BINDING_OUTPUT)
RWTexture3D<float2> CloudColumnOutput;
#else
layout(binding = CLOUD_LIGHTING_BINDING_OUTPUT)
RWTexture3D<float> CloudLightingOutput;
#endif

[shader("compute")]
[numthreads(8, 8, 1)]
void main(uint2 column : SV_DispatchThreadID)
{
  const CloudArgs args = cb.volumeArgs.clouds;
  const CloudDensityArgs density = cloudDensityParameters(args);
#ifdef CLOUD_LIGHT_COLUMN
  buildCloudColumnPrefix(args, density, column, CloudWeatherSampler, CloudBaseSampler, CloudDetailSampler, CloudColumnOutput);
#else
  buildCloudLightPrefix(args, density, column, CLOUD_LIGHT_INDEX, CloudWeatherSampler, CloudBaseSampler, CloudDetailSampler,
    CloudLightingOutput);
#endif
}
