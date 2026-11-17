// SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
// SPDX-License-Identifier: MIT
module cloud_incident;

import "rtx/pass/cloud_parameters.slang";
#include "rtx/utility/cloud_source_lut.h"

// The current two-stream closure is view-independent. Keep the two direct
// beams separate, so any camera, reflection or transmission ray uses its own phase.
public struct CloudIncidentField
{
  public float3 diffuse;
  public float3 direct[2];
};

public float3 evaluateCloudIncidentField(CloudArgs args, CloudIncidentField field, float3 direction)
{
  float3 radiance = field.diffuse;
  [unroll]
  for (uint light = 0; light < 2; ++light)
  {
    radiance += field.direct[light]
      * cloudSourcePhase(dot(direction, args.lights[light].directionToLight), args.anisotropy);
  }
  return radiance;
}
