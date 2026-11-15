/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
 * SPDX-License-Identifier: MIT
 */
//!variant filter_cloud_noise_3d.comp CLOUD_NOISE_VOLUME
//!variant filter_cloud_noise_3d_float.comp CLOUD_NOISE_VOLUME CLOUD_NOISE_FLOAT
//!variant filter_cloud_noise_2d.comp
//!end-variants

#ifdef CLOUD_NOISE_VOLUME
layout(binding = 0)
Sampler3D<float4> Source;
#ifdef CLOUD_NOISE_FLOAT
layout(rgba16f, binding = 1)
#else
layout(rgba8, binding = 1)
#endif
RWTexture3D<float4> Destination;
#else
layout(binding = 0)
Sampler2D<float4> Source;
layout(rgba16f, binding = 1)
RWTexture2D<float4> Destination;
#endif

[shader("compute")]
#ifdef CLOUD_NOISE_VOLUME
[numthreads(4, 4, 4)]
#else
[numthreads(4, 4, 1)]
#endif
void main(uint3 id : SV_DispatchThreadID)
{
#ifdef CLOUD_NOISE_VOLUME
  uint3 extent;
  Destination.GetDimensions(extent.x, extent.y, extent.z);
  if (any(id >= extent))
  {
    return;
  }
  Destination[id] = Source.SampleLevel((float3(id) + 0.5f) / float3(extent), 0);
#else
  uint2 extent;
  Destination.GetDimensions(extent.x, extent.y);
  if (any(id.xy >= extent))
  {
    return;
  }
  Destination[id.xy] = Source.SampleLevel((float2(id.xy) + 0.5f) / float2(extent), 0);
#endif
}
