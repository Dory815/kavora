// SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
// SPDX-License-Identifier: MIT
import "rtx/pass/cloud_parameters.slang";
import "rtx/algorithm/clouds.slang";
import "rtx/algorithm/cloud_lighting_cache.slang";

ConstantBuffer<CloudArgs> Clouds;
Sampler2D<float4>.Handle Weather;
Sampler3D<float4>.Handle Base;
Sampler3D<float4>.Handle Detail;
RWTexture3D<float> LightOutput;
RWTexture3D<float2> ColumnOutput;
uint LightIndex;

[shader("compute")]
[numthreads(8, 8, 1)]
void buildLight(uint2 column : SV_DispatchThreadID)
{
  buildCloudLightPrefix(Clouds, cloudDensityParameters(Clouds), column, LightIndex,
    Sampler2D<float4>(Weather), Sampler3D<float4>(Base), Sampler3D<float4>(Detail), LightOutput);
}

[shader("compute")]
[numthreads(8, 8, 1)]
void buildColumn(uint2 column : SV_DispatchThreadID)
{
  buildCloudColumnPrefix(Clouds, cloudDensityParameters(Clouds), column,
    Sampler2D<float4>(Weather), Sampler3D<float4>(Base), Sampler3D<float4>(Detail), ColumnOutput);
}
