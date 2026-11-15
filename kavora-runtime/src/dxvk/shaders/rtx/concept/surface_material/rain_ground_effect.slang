// SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
// SPDX-License-Identifier: MIT
module rain_ground_effect;

#include "rtx/utility/procedural_noise.h"

import "rtx/concept/surface_material/material_effects.slang";
import "rtx/utility/value_noise_sampling.slang";

public struct RainGroundSettings {
  public int2 sceneOrigin;
  public int2 gridOrigin;
  public int gridSize;
  public float rain;
  public float rippleStrength;
  public float ringTile;
};

public interface IRainGroundResources {
  static RainGroundSettings settings();
  static float3 cameraPosition();
  static StructuredBuffer<int> columns();
  static Sampler3D<float4> patchNoise();
  static Texture2D<float2> rings();
  static SamplerState ringSampler();
};

public struct RainGroundMaterial {
  public float3 albedo;
  public float3 normal;
  public float roughness;
};

public struct RainGroundInputs {
  public float rain;
  public float metallic;
  public float puddleCoverage;
  public float3 puddleNormal;
};

public struct RainGroundEffect : IMaterialEffect<RainGroundInputs, RainGroundMaterial> {
  [ForceInline]
  public static void apply(RainGroundInputs input, inout RainGroundMaterial material)
  {
    const float dielectric = 1.0f - input.metallic;
    const float wet = input.rain * dielectric;
    const float puddle = wet * input.puddleCoverage;
    material.albedo *= 1.0f - 0.22f * wet;
    const float filmRoughness = min(material.roughness, lerp(0.29f, 0.62f, material.roughness));
    material.roughness = lerp(material.roughness, filmRoughness, wet);
    material.roughness = lerp(material.roughness, min(material.roughness, 0.16f), puddle);
    if (puddle > 0.0f)
    {
      material.normal = normalize(lerp(material.normal, input.puddleNormal, puddle));
    }
  }
};

[ForceInline]
public float exposedGroundRain<Resources : IRainGroundResources>(float3 position, RainGroundSettings settings)
{
  const int2 column = int2(floor(position.xz)) + settings.sceneOrigin;
  const int2 cell = column - settings.gridOrigin;
  if (any(cell < 0) || any(cell >= settings.gridSize))
  {
    return 0.0f;
  }
  const int2 wrapped = column & (settings.gridSize - 1);
  const int exposedY = Resources.columns()[wrapped.y * settings.gridSize + wrapped.x];
  const float2 fromCamera = position.xz - Resources.cameraPosition().xz;
  const float rangeWeight = 1.0f - smoothstep(88.0f * 88.0f, 112.0f * 112.0f, dot(fromCamera, fromCamera));
  return position.y >= float(exposedY - 1) ? rangeWeight * settings.rain : 0.0f;
}

public static const float kMaxGroundPuddleRelief = 0.12f;

[ForceInline]
public RainGroundInputs groundPuddleInputs<Resources : IRainGroundResources>(RainGroundInputs input,
  float3 position, RainGroundSettings settings, float relief, float cavity)
{
  // The noise lattice and the ring texture both repeat over the same world interval.
  const int patchScale = 3;
  const int patternPeriod = patchScale * VALUE_NOISE_RESOLUTION;
  const int2 patternOrigin = (settings.sceneOrigin % patternPeriod + patternPeriod) % patternPeriod;
  const float2 tilePosition = position.xz + float2(patternOrigin);
  const float patch = sampleLinearValueNoise(Resources.patchNoise(), float3(tilePosition / float(patchScale), 11.5f)).x;
  const float slopeWeight = smoothstep(0.7f, 0.98f, input.puddleNormal.y);
  const float reliefWeight = 1.0f - smoothstep(0.025f, kMaxGroundPuddleRelief, relief);
  input.puddleCoverage = slopeWeight * reliefWeight * smoothstep(-0.06f, 0.34f, patch + cavity);
  const float3 cameraOffset = position - Resources.cameraPosition();
  const float ripple = settings.rippleStrength * (1.0f - smoothstep(144.0f, 1024.0f, dot(cameraOffset, cameraOffset)));
  if (input.puddleCoverage > 0.0f && ripple > 0.0f)
  {
    const float2 slope = Resources.rings().SampleLevel(Resources.ringSampler(), tilePosition / settings.ringTile, 0.0f);
    input.puddleNormal = normalize(input.puddleNormal - float3(slope.x, 0.0f, slope.y) * ripple);
  }
  return input;
}
