// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
//!variant generate_cloud_light_sun.comp CLOUD_LIGHT_INDEX=0
//!variant generate_cloud_light_moon.comp CLOUD_LIGHT_INDEX=1
//!end-variants

import "rtx/algorithm/clouds.slang";
import "rtx/algorithm/cloud_lighting_cache.slang";
import "rtx/pass/cloud_parameters.slang";
import "rtx/utility/cloud_density.slang";
#include "rtx/pass/common_bindings.slangh"
#include "rtx/pass/clouds/cloud_lighting_binding_indices.h"

layout(binding = CLOUD_LIGHTING_BINDING_OUTPUT)
RWTexture3D<float> CloudLightingOutput;

[shader("compute")]
[numthreads(8, 8, 1)]
void main(uint2 column : SV_DispatchThreadID)
{
  const CloudArgs args = cb.volumeArgs.clouds;
  const CloudDensityArgs density = cloudDensityParameters(args);
  buildCloudLightPrefix(args, density, column, CLOUD_LIGHT_INDEX, CloudWeatherSampler, CloudBaseSampler, CloudDetailSampler,
    CloudLightingOutput);
}
