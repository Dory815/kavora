# Cloud redesign: implementation and validation record

Date: 2026-11-16. Branch: `fix/cloud-system-redesign`.

**Status: implementation and CPU diagnostic work are delivered, but native
acceptance is BLOCKED. This branch is not certified merge-ready.** No Slang/SPIR-V
compilation, Vulkan readback, Windows runtime build, Minecraft capture, temporal
reconstruction check or RTX GPU timing completed in this continuation session.

## Revisions and scope

The continuation baseline is `33bbc3ce1c047700285f47f1dfa298054416606e`, not the
older cloud-shape-and-cost branch. Existing changes before this baseline are not
counted as new work in this record.

| Commit | Change |
| --- | --- |
| `9b323b62b1e4198dc1da4c6cbebf6e9ff450d966` | Fixed family periods and world-scale erosion continuity; added density regressions. |
| `894975d2f9b6317cec9794f50ecc977d1203852a` | Independent convective and stratiform occupancy, bases, depths and profiles within the existing transport shell. |
| `e29aec2c8cd8f0dbd28c0877ed4e8b98a953d0e8` | Stable clipped-ramp moments and continuous weather filtering; mathematical and full-range tests. |
| `60a689b8a308cb55d5904da7d87659843b1dc6f1` | Multi-location visual acceptance harness, negative tests, Meson registrations and CI setup fixes. |

Every commit above was pushed immediately before work on the next commit.
Density visuals and final numerical checks use the shader at `e29aec2c`; the
following tooling commit does not alter that shader. Its Git blob is
`a6b40e4abdc199dc1d59d1b52a72c77aaa40cedb`.

The visual/structural reference study remains in [CLOUD_SYSTEM_RESEARCH.md](CLOUD_SYSTEM_RESEARCH.md).
It covers Complementary, Photon, Revelation, Nostalgia and AstraLex. This change
uses independent Kavora calculations, not transplanted shader-pack code.

## Implemented changes

The two low-cloud families no longer interpolate one global noise wavelength.
Their fixed periods divide the weather/wind wrap, and erosion is sampled in
world-scaled coordinates before any family-specific body scaling. This removes
the discontinuous detail-coordinate reset and the nonperiodic intermediate
wavelengths.

Cumulus and spreading decks retain independent coverage, local base, thickness,
height profile and erosion. Their densities can coexist rather than selecting
one profile with a scalar type. Rain lowers and deepens the deck instead of
adding a spatially uniform cloud slab. Existing low/high transport shells,
resource bindings, shared lighting consumers and bounded ray grids remain in
place. High cirrus is unchanged by these commits.

Filtered weather variance is estimated from four child-mip samples for each
family. It is a bounded local estimate, not an exact representation of all
unresolved variation. Constant fields remain constant, and the child footprint
collapses continuously to the center sample at the first filtering boundary.
Clipped-ramp moments use linear/tail/deficit formulas to avoid subtracting nearly
equal polynomial values.

## What actually ran

The available execution environment had a C++ compiler but no usable SlangPy or
Vulkan device/ICD. A diagnostic compatibility layer compiled the fetched source
functions as C++ float32 with syntax-only module/attribute/swizzle adaptations.
Texture sampling and GPU resource plumbing are emulated. The view-range and
opacity checks execute a source excerpt of the production cloudTransmittance
path; they do not execute a separately invented view integrator.

This is useful for detecting field and numerical defects, but it cannot establish
Slang compilation, descriptor correctness, GPU filtering identity or native
performance. The delivered diagnostic archive includes the adapter, source
snapshots, hashes, scripts, raw results and reproduction commands. No adapter
code is part of the game's production rendering pipeline.

| CPU-adapted check | Result |
| --- | --- |
| 48 cloud-type / Y-up or Z-up / wind-wrap cases | Pass; final maximum density difference 0.0004625. |
| 40 cloud-type / coverage / axis seam cases | Pass; maximum density change across 3.125 cm is 0.0041091. |
| Full generated-weather wrap | Pass under the existing absolute/relative tolerance; maximum difference 0.0006968. |
| Independent families | Pass; capped sum and empty-mask behavior, with fixture density centroids 734.97 m and 1237.82 m. |
| 18 constant-mask / footprint cases | Pass; maximum density difference zero. |
| 20 scale/thickness configurations, 81,920 positions | Pass; finite bounded density and enclosing-shell support. |
| 2,160 clipped-ramp moment cases | Pass against independent double-precision integration; maximum absolute error 1.244e-7. |
| 65,536 positions across the first weather mip boundary | Maximum adjacent density change reduced from 0.0154260 to 0.00005731. |
| 62,208 full-range view-ray prefixes | Pass; finite bounded transmission, monotone prefix extension and disabled-field behavior. |
| Six visual-plan unit tests | Pass in ordinary Python, including failed/timeout/stale render rejection. |

Constant-mask fixtures use float32 texture values, matching the RGBA32 test
fixtures. Generated noise/weather use their production storage quantization.
Baseline failures are retained in the archive rather than replaced by candidate
results. Full-range tests cover 12 locations, observers below/inside/above the
clouds, three weather states, four budgets and 1.7/12/24/96 km prefixes. Opaque
rain horizons are allowed; the tests do not require every sky to have blue gaps.

## Visual inspection

Forty-eight low-cloud opacity images were rendered from the source view path:
reference/candidate, four world locations, two coverage settings (0.45 and 0.85)
and three pitches (10, 45 and 90 degrees). Inputs include 256x144 pixels, 75-degree
vertical FOV, 384 view cells, a 24 km low-cloud range, and a camera-centered ground
reference matching the runtime convention. White means cloud opacity and black
means clear sky. These images do not claim to show lighting or cloud color.

Inspection shows more varied silhouettes and openings at the origin/north/far
locations without forcing all regions to become clear. The user and far
cloud-rich overhead views remain essentially opaque. That is a valid coverage
outcome, not evidence that the lighting of their interiors is natural.

An earlier 20-image RGB diagnostic uses simplified lighting and the pre-filter-fix
family density. It is labelled separately and is not evidence for final native
color, scattering, sunset quality or temporal stability. Some views show broad
gray ceilings; that limitation is retained rather than hidden by selecting only
favorable viewpoints. The final aesthetic acceptance gate remains open.

## Sampling and cost limits

No new full raymarch layer or persistent GPU texture was added. The low-density
query requires at most four logical texture samples while weather is resolved,
and seven when the four-child weather estimate is active. Sampling each active
body is conditional on its height profile. Logical calls are not equivalent to
texel traffic, register pressure or GPU time.

Equal-query CPU measurements with four workers and three repetitions showed
approximately 1.01x to 1.91x baseline query time across two runs over the tested weather and
footprint cases. The filtered cases are more expensive. These timings are noisy
CPU diagnostics and must not be presented as game FPS or as a successful GPU
performance budget. The archive retains individual cases and sampler counts.

A separate 72-ray, 96 km grazing-view diagnostic compared view budgets against a
2048-cell reference with a fixed pixel cone:

| View budget | Mean absolute transmission error | Maximum error |
| --- | ---: | ---: |
| 64 | 0.104561 | 0.956450 |
| 128 | 0.043501 | 0.691557 |
| 256 | 0.010760 | 0.215212 |
| 384 | 0.000458 | 0.008404 |
| 512 | 0.000330 | 0.008870 |

This subset is not a universal convergence guarantee. Low budgets clearly lose
important features and are not approved by this record. No quality default was
silently increased as part of the density change.

## Native validation entry points

The following require NumPy and SlangPy with a hardware or software Vulkan ICD:

```sh
python kavora-runtime/tests/rtx/unit/test_cloud_transport.py --dump scratch/cloud-transport
python kavora-runtime/tests/rtx/unit/test_cloud_morphology.py --dump scratch/cloud-morphology
python kavora-runtime/tests/rtx/unit/test_cloud_density_math.py --dump scratch/cloud-math
python kavora-runtime/tests/rtx/unit/test_cloud_filtering.py --dump scratch/cloud-filtering
python kavora-runtime/tests/rtx/unit/test_cloud_view_ranges.py --dump scratch/cloud-ranges
python kavora-runtime/tests/rtx/unit/test_cloud_lighting.py
python kavora-runtime/tests/rtx/unit/test_cloud_scattering.py --device vulkan
```

The numerical moment reference uses precise floating-point compiler mode to
match its documented operation rounding. Other density/transport tests retain
the normal compiler mode.

The visual matrix supports four locations, five weather states, both layers,
three pitches and four light angles. Reference and candidate use identical
controls and the matching revision's test support. Without a production
atmosphere fixture, the sunset case tests a low solar angle under a constant
environment, not physically correct sunset color.

```sh
python kavora-runtime/tests/rtx/unit/render_cloud_morphology_matrix.py \
  --output scratch/cloud-plan --dry-run

python kavora-runtime/tests/rtx/unit/render_cloud_morphology_matrix.py \
  --output scratch/cloud-matrix \
  --reference-repo ../kavora-reference \
  --reference-shader-root ../kavora-reference/kavora-runtime/src/dxvk/shaders
```

A plan is not a completed render. Failure manifests and per-case logs remain on
disk, and missing fresh completion markers, images or raw outputs reject a case.

## Blocking acceptance gates

GitHub Actions run `43899579691`, for tooling commit `60a689b8`, created five jobs
but all failed before executing a step. The API reports empty step lists,
`runner_id=0` and empty runner names. A previous run retry behaved the same way.
The available API output does not establish the underlying account/service
reason, so this record does not attribute it to billing or a shader failure.

Still required: actual Slang/SPIR-V compilation and the complete Vulkan suite;
Windows native build; the full atmosphere/cloud/terrain presentation path;
motion, camera cuts, wind wrapping, sunset and weather transitions; and target
RTX GPU timings including lighting-cache construction. Native screenshots must
include the opaque cloud-rich views, not just the newly opened regions.

Until those gates run and are reviewed, do not describe this redesign as fully
validated, performance-approved or ready to merge.
