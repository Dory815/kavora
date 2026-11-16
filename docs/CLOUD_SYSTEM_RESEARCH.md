# Cloud-system redesign: reference study and design baseline

Date: 2026-11-16
Target branch: fix/cloud-system-redesign

## Goal

A natural sky must work for sparse, broken, cloud-rich, overcast, sunset,
horizon and zenith views. A clean blue sky is one valid weather state, not the
quality target for every state. Cloud amount, scale, type, vertical development
and regional organization must be independently expressive.

## Mature Minecraft shader references

### Complementary Reimagined / Unbound

Sources:
- https://www.complementary.dev/reimagined/
- https://github.com/ComplementaryDevelopment/ComplementaryReimagined/blob/main/shaders/lang/en_US.lang
- https://github.com/ComplementaryDevelopment/ComplementaryReimagined/blob/main/shaders/lib/atmospherics/clouds/unboundClouds.glsl

Complementary deliberately offers two visual defaults: Reimagined preserves
Minecraft's visual identity; Unbound aims at a more realistic presentation.
Its controls separate cloud amount, cloud size and rain-driven addition, and
Reimagined can enable a second layer at a distinct altitude. Unbound uses
multi-octave noise and altitude-dependent thresholding.

Takeaway: amount and scale are separate artistic dimensions. Increasing amount
should create more cloud-bearing regions and/or enlarge groups, not simply make
every existing cloud thicker. A second layer is useful when it adds a different
visual scale or type, not when it duplicates the same morphology.

### Photon

Sources:
- https://github.com/sixthsurge/photon/blob/main/shaders/include/sky/clouds.glsl
- https://github.com/sixthsurge/photon/blob/main/shaders/include/sky/clouds/cumulus.glsl
- https://github.com/sixthsurge/photon/blob/main/shaders/include/sky/clouds/cirrus.glsl
- https://github.com/sixthsurge/photon/blob/main/shaders/include/weather/clouds.glsl
- https://modrinth.com/shader/photon-shader

Photon explicitly composes cumulus/stratocumulus/stratus, altocumulus,
congestus, cirrus and noctilucent components. Its low volumetric layer blends
cumulus and stratiform morphology, with altitude-dependent shaping and erosion.
Weather parameters depend on humidity, temperature, wind and rain; different
cloud families respond differently. Layer composition uses transmittance and
can terminate work after nearer layers become sufficiently opaque.

Takeaway: cloud families need different spatial spectra, edge character,
vertical profiles and weather response. Changing one scalar type on a common
blob field is not an adequate substitute. Weather must influence morphology,
not only total amount. Layer order and opacity can also bound work.

### Revelation

Sources:
- https://github.com/HaringPro/Revelation/blob/dev/shaders/lib/atmosphere/clouds/Shape.glsl
- https://github.com/HaringPro/Revelation/blob/dev/shaders/shaders.properties

Revelation's low cloud field uses a large-scale coverage map, a separate broad
local-coverage sample and a type/height lookup table. Coverage controls vertical
extent while the LUT controls vertical profile. Base 3D noise erodes the
profile; curl noise warps coordinates before sampling; fine detail is separate
from coarse occupancy. High-cloud map channels distinguish cirrus,
cirrostratus and cirrocumulus under shared regional coverage.

Takeaway: separate where clouds may form from what their 3D body looks like.
Keep regional coverage, family selection, vertical profile, base shape and
fine erosion as distinct signals. Coarse occupancy can support empty-space
skipping before expensive detail is sampled.

### Nostalgia

Source: https://modrinth.com/shader/nostalgia-shader

Nostalgia explicitly offers vanilla-style volumetric clouds with multiple
layers and uses the cloud texture supplied by the resource pack. It shows that
layered silhouettes can preserve a recognizable Minecraft visual language.

Takeaway: retain readable silhouettes and a range of scales. Naturalism should
not turn the sky into a uniform noise field without recognizable cloud forms.

### AstraLex

Source: https://modrinth.com/shader/astralex/

A widely used configurable pack with a dedicated clouds feature alongside
atmosphere, volumetric lighting and weather. Public feature descriptions are
less specific about internal morphology, so this is a breadth check rather
than a source for implementation claims.

## Natural-sky criteria

1. Mesoscale organization: coherent streets, clusters, bands and broad humid /
   dry regions, not uniformly scattered independent cells.
2. Scale hierarchy: large parent masses contain medium billows and smaller
   edge erosion; no single frequency dominates the sky.
3. Family separation: fair-weather cumulus, stratocumulus/stratus, congestus
   and wispy cirrus have visibly different silhouettes and vertical profiles.
4. Cloud-rich plausibility: high coverage still contains holes, variable
   thickness, connected decks and clear gaps. Do not tune only for sparse sky.
5. Nonuniformity without obvious tiling, equal spacing or equally sharp edges.
6. Perspective: nearby bodies retain volume; distant fields merge through
   aerial perspective without simply fading all cloud mass away.
7. Weather continuity: rain changes cloud families and organization gradually,
   not merely opacity.
8. Lighting coherence: forms remain legible in side light, backlight, sunset
   and overcast illumination.

## Kavora baseline on this branch

Relevant files:
- utility/cloud_density.slang: CloudColumn samples the weather map, derives
  coverage moments and a scalar type, then selects a small set of body scales
  and a shared vertical profile. Rain/thunder adds a stratiform contribution
  to the same low layer.
- pass/clouds/generate_cloud_weather.comp.slang: a 2D weather map combines
  broad regional Perlin fields, 8/16/32-frequency cumulus groups and a weak
  cellular Worley contribution for broken stratiform decks. It derives
  coverage and type scalars, and stores cirrus density in channel four.
- pass/clouds/generate_cloud_noise.comp.slang: periodic 3D Perlin/Worley volume
  supplies billow shape; a separate detail volume supplies erosion.
- utility/cloud_shape.slang: cirrus silhouettes use an atlas of finite fibres
  grouped into deterministic wind-aligned packets.
- algorithm/clouds.slang: existing transport supports distinct low/high
  shells, shared visibility/lighting paths and bounded ray integration.

This is more sophisticated than one noise layer, but the visible low-cloud
family is still largely a common 3D body field whose scalar weather type
adjusts scale/profile. The weather map decides regional coverage and type but
does not yet provide independently authored overlapping stratiform,
fair-weather cumulus and congestus occupancy fields. This is the structural
hypothesis to test next.

## Proposed direction

Do not add raymarch layers by default. First improve the cloud-field
representation so existing transport can render a richer sky.

1. Keep the current low/high transport shells and shared lighting integration
   until visual evidence proves another shell is necessary.
2. Split low-layer weather into distinct but spatially related family signals:
   broad stratiform/deck mask; broken fair-weather cumulus parent groups; sparse
   congestus/deep-development mask correlated with humid/unstable weather.
3. Derive them from shared broad weather/humidity fields plus decorrelated
   family fields. Do not create unrelated random maps; overlap/exclusion must
   be weather-aware.
4. Keep occupancy and family selection cheap. Evaluate 3D base shape, curl
   distortion and fine erosion only after coarse occupancy detects a cloud.
5. Keep high cirrus as a separate thin-cloud family. Add mid-level families
   only if reference views show a real missing scale.
6. Test amount, scale and family mixture independently. Raising coverage must
   not force every cloud body to become equally thick.
7. Preserve deterministic periodic wind behavior, bounded sampling and cache
   domain contracts.

## Validation gates

Visual matrix: sparse cumulus; broken cumulus at 30-60% apparent coverage;
cloud-rich cumulus at 60-85%; irregular stratocumulus deck; mixed cumulus/deck;
humid congestus; cirrus over low clouds; rain/overcast transition. Review
side-lit, sunward, antisolar, horizon, zenith, sunset and twilight views. The
transport tests also cast 10-degree horizon rays from 12 regional origins
through broken and cloud-rich deck weather, rejecting a uniformly clear or
uniformly cloud-filled local horizon field. The full-distance horizon band is
checked in the rendered A/B matrix.

Structural diagnostics: sky coverage, connected-component size distribution,
multi-scale spatial autocorrelation, edge-length distribution, per-family
vertical density profiles and family overlap. These metrics guide inspection;
they do not replace visual review.

Performance: production GPU timings on target hardware when available; texture
bandwidth, register pressure, ray steps, cache build cost and early-exit rate.
Compare old/new at equal quality and equal visual target. CPU software Vulkan
is useful for correctness but is not an RTX GPU frame-time claim.

Reject a change that improves sparse-sky aesthetics but makes cloud-rich skies
repetitive, flat, uniformly opaque or too sparse. Review horizon and zenith
separately.

## Limitations

This study inspected public descriptions and source for Complementary, Photon
and Revelation, plus public feature descriptions for Nostalgia and AstraLex.
It does not claim to reproduce proprietary output. No Minecraft runtime/device
capture is available from this GitHub-only editing session; previews must state
their renderer, inputs, resolution and whether full game presentation is used.
The separate fix/cloud-shape-and-cost validation artifact is not evidence for
this branch and is not treated as a pass/fail result here.


## Reproducible preview matrix

The branch includes `kavora-runtime/tests/rtx/unit/render_cloud_morphology_matrix.py`.
From the repository root, run it in the runtime's Python environment:

```powershell
python kavora-runtime/tests/rtx/unit/render_cloud_morphology_matrix.py --output .scratch/cloud-morphology
```

It reuses the production shader preview path and texture cache while rendering
five fixed low-cloud cases: broken fair-weather cumulus, cloud-rich fair
weather, mixed development, a stratiform deck, and a rain/thunder transition.
Each case uses the same five views, camera, sun, transport budget and exposure.
If a matching atmosphere fixture is available, pass
`--atmosphere-fixture PATH` to include the production air integrator. Without
that fixture the preview uses its documented diagnostic sky. The outputs are
offline production-shader previews, not full Minecraft captures.

The numerical transport test also writes `cloud-weather-field.npz` and
`cloud-density.npz` when invoked with `--dump DIRECTORY`. These retain the
generated weather field and density maps for quantitative inspection.


## Natural cloud-field references

These satellite/aerial references are used to check spatial organization, not
to copy their exact appearance into a ground-level sky renderer:

- [NASA: Open- and Closed-Cell Stratocumulus Clouds over the Pacific](https://science.nasa.gov/earth/earth-observatory/open-and-closed-cells-over-the-pacific-87456/)
  shows dense cellular cloud fields with open and closed regions. The useful
  lesson is that cloud-rich coverage can remain highly structured and contain
  many clear holes.
- [NASA: Cloud Streets over the Timor Sea](https://science.nasa.gov/earth/earth-observatory/cloud-streets-over-the-timor-sea-88389/)
  shows broad bands of cumulus groups separated by clear lanes. Cloud streets
  are a conditional wind/convection regime, not a pattern to impose on every
  fair-weather sky.
- [NASA: Cloud Streets Trace Cold Coastal Winds](https://science.nasa.gov/earth/earth-observatory/cloud-streets-trace-cold-coastal-winds-87524/)
  shows long aligned cloud bands and their associated clear corridors.
- [WMO International Cloud Atlas: Cumulus rows (streets)](https://cloudatlas.wmo.int/docs/wmo_407_en-v2.pdf)
  describes the alignment, spacing and physical context of cumulus streets.
- [NASA: Curving Cloud Streets](https://science.nasa.gov/earth/earth-observatory/earth-a-photo-essay/atmosphere/)
  is a reminder that mesoscale organization can curve with larger atmospheric
  circulation rather than remaining a fixed straight stripe.

These references argue against a single isotropic blob distribution: cloud
fields may organize into cellular decks, irregular openings, broken clusters,
or wind-aligned streets depending on the weather regime. They also argue
against globally forcing one such pattern. The current weather field's
isotropic Perlin groups are a useful baseline, but a future wind-aware street
component should be conditional and weakly mixed with other organizations.

For a fixed-input baseline/candidate comparison, create a worktree at the
pre-redesign commit and pass its shader directory as
`--reference-shader-root`. For example:

```powershell
git worktree add .scratch/cloud-baseline 469319c7df2fa37a4920cda2cef682cf251c8269
python kavora-runtime/tests/rtx/unit/render_cloud_morphology_matrix.py `
  --output .scratch/cloud-ab `
  --reference-shader-root .scratch/cloud-baseline/kavora-runtime/src/dxvk/shaders
```

This renders both variants with the same scenario inputs and writes separate
`reference/` and `candidate/` result directories. It still does not include
the complete Minecraft presentation path unless the atmosphere fixture and
other required game inputs are supplied.

## Implementation progress on fix/cloud-system-redesign

The first field-representation change now stores two independent low-cloud masks
in the existing RGBA16F weather map:

- R: regionalized cumulus parent-group coverage.
- G: stratiform deck coverage, built from the broad moisture field, independent
  8/16-cell Perlin detail and a weak cellular perturbation for irregular
  openings. The family field keeps broad regional organization while avoiding
  a single smooth blob frequency.
- B: broad cloud-family/development type.
- A: high-cloud cirrus atlas density.

The density evaluator samples the two filtered masks and blends their coverage
moments using the local family type. The low/high shell count, texture formats,
resource bindings and ray transport remain unchanged. This avoids introducing
another volume, descriptor or raymarch pass just to establish a distinct
stratiform occupancy field.

The weather-map regression now checks both masks independently for normalized
range, spatial variation and broad opening/cloud-rich quantiles. The existing
cumulus autocorrelation checks remain tied to the cumulus channel. The weather
map no longer stores the old R mean / G second-moment pair; both family masks
are mip-filtered independently. The density evaluator reconstructs a bounded
unresolved-coverage variance from each family mean and the selected weather-map
LOD. This is deliberately conservative rather than pretending the two family
means contain exact second moments. The grazing/horizon preview must verify
that this approximation retains openings without inflating cloud coverage into
a continuous opaque deck. If it cannot meet both requirements, the next
iteration should add separately filtered family moments instead of silently
reinterpreting either family channel.

This change is a structural foundation, not a claim that stratiform and
cumulus now have fully independent 3D shape generators. They still share the
existing base/detail volumes and ray transport, with their distinct
occupancy, family-dependent body scale and vertical shaping. Further work must
separate their 3D silhouette/erosion where the visual matrix demonstrates that
the shared shape field remains limiting.


## Natural-photo morphology anchors

Use the following open/public meteorological references to judge shape and
distribution, not color/exposure matching:

- Met Office, *Cloud Types for Observers*, especially the stratocumulus
  examples: patches and layers of rounded masses or rolls, often merging at
  their edges, sometimes arranged in parallel bands, and sometimes broken by
  visible gaps.
  https://www.metoffice.gov.uk/binaries/content/assets/metofficegovuk/pdf/research/library-and-archive/library/publications/weather--climate-guides/cloud_types_for_observers_rev_2014.pdf
- ETH Zurich / Institute for Atmospheric and Climate Sciences teaching plate:
  an oblique view showing altocumulus sheets/bands coexisting with separate
  cumulus masses in the same sky.
  https://ethz.ch/content/dam/ethz/special-interest/usys/iac/iac-dam/documents/edu/courses/cloud_microphysics/CMP_HS_2024_Zamin/CMP_Fall_2024_Kanji.pdf
- Hereon / German Weather Service teaching material: a comparative photograph
  of stratus, broken stratocumulus and vertically developed cumulus in spatial
  relationship.
  https://www.hereon.de/imperia/md/assets/clm/neu_the3.4.pdf
- Wikimedia Commons, *White Cumulus Clouds against Blue Sky*: a wide 16:9
  fair-weather reference with separated puffy masses and broad blue gaps.
  https://commons.wikimedia.org/wiki/File:White_Cumulus_Clouds_against_Blue_Sky.jpg
- Wolkenatlas, *Cumulus congestus*: a tall cauliflower-like body with strong
  vertical growth, a comparatively dark base and a bright, structured crown.
  https://www.meteo-julianadorp.nl/wolkenatlas/Cumulus-congestus.html

These references make an important distinction visible: cloud-rich skies do
not mean a uniformly filled noise texture. Stratocumulus can occupy most of
the sky while retaining irregular holes, rounded rolls and banding; cumulus
can coexist in front of or below broad sheets; congestus should be a relatively
rare vertical accent rather than the default shape everywhere.


## Historical production-preview baseline (not validation of this branch)

A separate, earlier cloud/atmosphere branch completed a 24-view perspective
matrix plus two 32 km top-down diagnostics using the production cloud and air
Slang shaders on software Vulkan. Its source tree was
`038e1d7618c8bee9a8bc0b85f8449ce20c2185b3` (branch
`fix/low-cloud-lighting`); it is an ancestor of this redesign's starting
point, but its preview results are not a pass for the current changes.

The useful findings are:

- Fair-weather cumulus in side-lit, antisolar and zenith views had readable
  white bodies, grey folds, irregular openings and acceptable distribution.
- The 32 km low-cloud top-down distribution was broadly acceptable, although
  local shapes remained somewhat similar.
- The horizon view still showed a dense, nearly continuous horizontal cloud
  band. The top-down and horizon views therefore expose different failure
  modes; one cannot replace the other.
- Strong sunset orange/red illumination did not match the natural references.
  This is a lighting/atmosphere issue as well as a cloud-shape issue.
- High-cloud fibre shapes were generally acceptable, but dense heads were too
  soft in several views.

The complete historical side-by-side review and source provenance are retained
in the Library artifact `kavora-cloud-natural-photo-review.html`. Its renders
exclude Minecraft terrain, sun/moon disks, game fog and temporal
reconstruction, so they are production-shader offline previews, not in-game
captures.

For this redesign, the horizon band is a specific regression target. The
family-mask mip variance reconstruction is intended to keep distant cloud
openings from averaging into a continuous deck. It must be verified against
the same horizon and top-down views, while retaining the accepted cloud-rich
side-lit and zenith morphology. Do not solve the band by simply fading all
distant clouds or by making the whole sky sparse.


The rain-driven stratiform contribution is also multiplied by the sampled
family coverage. This prevents a nonzero weather scalar from creating a
globally continuous low-altitude sheet through otherwise dry regions. Strong
rain still thickens the existing cloud-bearing regions; it does not erase
their weather-map openings.


The branch's cloud validation workflow now renders a fixed-input A/B matrix
against the redesign starting point `469319c7df2fa37a4920cda2cef682cf251c8269`.
It covers five weather presets, side/sunward/antisolar/sunset lighting, and
oblique plus horizon views. The artifact contains both baseline and candidate
radiance/opacity images with their manifests and numerical diagnostics.
