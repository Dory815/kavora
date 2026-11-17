# Path-traced cloud and atmosphere performance work

Branch: `perf/cloud-atmosphere-pathtracing`

This change set keeps the existing Vulkan/RTX path-tracing transport. It does
not replace the G-buffer atmosphere, cloud volume integration, PSR, or
path-traced material transport with screen-space shader-pack rendering.

## Changes

### Air-light disk quadrature

For small celestial disks wholly above the local horizon and with
`dot(localUp, lightDirection) >= 0.3`, evaluate the transmittance LUT once at
the central light direction. Retain the original four-node disk quadrature
for grazing rays, partially occulted disks, and larger emitters.

For each eligible active light sample this reduces transmittance LUT reads in
the finite-disk integral from four to one, and avoids the associated disk
quadrature setup. It does not change the view-ray integration step count.

### Air scattering phase terms

Rayleigh and Mie phase terms depend on the fixed view-ray direction and light
directions, not on the position of an air sample along that ray. Compute these
terms once in `createAirRayPhase` and reuse them for the air cells in one
`integrateAtmosphereRange` invocation. Inactive lights are skipped. The
four-argument `sampleAirMedium` entry point remains available as a wrapper.

This is an exact algebraic hoist; it does not change the phase functions,
extinction profile, LUTs, or quadrature.

The same invariant applies to cloud scattering. The mixed Henyey-Greenstein
phase used by `cloudIncidentRadiance` depends on the view-ray direction and
light direction, not the cloud-cell position. It is now computed once per
atmosphere ray, and once per sky-map pixel ray in cloud-sky generation, rather
than once for every cloud cell. The existing single-sample entry point remains
as a compatibility wrapper. Lights with no irradiance and no radiance-profile
energy are skipped during phase setup. A shader contract compares the hoisted
phase against the original expression for 128 deterministic ray directions,
including inactive-light handling.

### Cloud directional-cache grid reuse

The cloud directional optical-depth query already constructs a light-space
grid to determine the local cache-cell footprint. The same grid is now passed
to the optical-depth prefix lookups rather than reconstructing the light basis
for each interval. The near grid is also shared with the near-cascade
containment test, and near/far grids are each constructed once when both
cascades are blended.

Depending on whether the local interval is split and whether near/far cascades
are blended, the previous code could reconstruct the same cascade grid about
3–9 times during one low-light optical-depth query. The new path constructs
each required grid once (one for near-only, or one each for near and far).
All cache sampling, interpolation, prefix subtraction, local correction,
fallback behavior, and optical-depth arithmetic are unchanged.

## Validation

- `tests/rtx/unit/test_air_disk_approximation.py`: CPU regression against
  four-point disk quadrature over 972 spherical-atmosphere cases, plus horizon,
  partial-disk, large-emitter, and per-ray phase-invariance checks.
- Current CPU result: maximum absolute transmittance difference
  `4.400922e-05`; maximum relative difference `6.982272e-05`.
- `tests/rtx/unit/cloud_lighting_contracts.comp.slang` adds a `reusedGrid`
  entry point. `test_cloud_lighting.py` compares the reused-grid lookup and
  containment results against the existing wrappers.
- A CPU-rendered A/B image compares the spherical-atmosphere transmittance
  reference and central-ray approximation over altitude and light angle. It is
  a component diagnostic, not a Minecraft screenshot.
- The container does not have SlangPy, a Vulkan Python binding, a Vulkan ICD,
  or a reachable GitHub host for a local clone. Therefore Slang/SPIR-V
  compilation, Vulkan readback of the cloud contract, Windows runtime build,
  RTX GPU timing, and full Minecraft visual acceptance have not been run.

## Interpretation

These are targeted reductions in redundant shader work, not a demonstrated
frame-time percentage. The Nsight report's `Dense Endpoint` and PSR command
stream spans remain the primary unresolved performance targets. They are
command-stream spans across multiple submissions, not per-shader GPU timings.
No claim is made that these changes alone solve the reported multi-hundred
millisecond workload.

The next high-value investigation is the per-cloud-cell `cloudIncidentRadiance`
work: `cloudLocalOpticalDepth` samples the 3D cloud field vertically, while
`cloudLightOpticalDepth` evaluates directional shadow transport. Any
replacement must preserve near-cloud correction, external blockers, finite
light-source behavior, and the path-tracing radiance/transmittance contract.
