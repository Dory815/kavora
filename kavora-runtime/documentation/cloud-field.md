# Cloud density and transport

The native density field adapts the weather distribution and cloud profiles
from [Community Edition](https://github.com/CuteEthanLeo/rtx-remix-minecraft-ce),
revision `94400621dabc6b315d8e53b701c7be7beffa9303`. Its source and Apache-2.0
notice are recorded under `documentation/licenses/RTX-Remix-CE-Clouds.txt`.

[Photon](https://github.com/sixthsurge/photon/tree/2a3d502c17d2e310412c717be47241f014cba7fc)
was studied as a visual reference for cloud layers, weather, erosion and
atmospheric lighting. No Photon shader code or assets are included.

High-cloud morphology also draws on these published methods and observations:

- [WMO International Cloud Atlas](https://cloudatlas.wmo.int/en/species-cirrus-ci.html):
  distinct fine filaments, irregular curvature, and detached cloud patches.
  Parallel bands occur in nature, but should not impose uniform spacing and
  identical lengths across the whole field.
- [Nubis, 2017](https://www.guerrilla-games.com/read/nubis-authoring-real-time-volumetric-cloudscapes-with-the-decima-engine):
  regional coverage and smaller cloud footprints have separate controls. The
  presentation's PDF page 50 describes a two-dimensional cirrus lookup.
- [Hillaire, Frostbite, 2016](https://media.contentapi.ea.com/content/dam/eacom/frostbite/files/s2016-pbs-frostbite-sky-clouds-new.pdf),
  sections 5.3.1 and 5.4.1: separate distribution, shape and detail, and precombine
  density shaping to reduce per-sample work.
- [Bridson et al., Curl-Noise for Procedural Fluid Flow, 2007](https://www.cs.ubc.ca/~rbridson/docs/bridson-siggraph2007-curlnoise.pdf),
  sections 2.1 and 2.2: derive a spatially varying velocity field from the curl
  of a smooth noise potential. This informs the density bake, not a runtime
  fluid simulation.
- [Webanck et al., Procedural Cloudscapes, 2018](https://doi.org/10.1111/cgf.13373),
  sections 4.1 and 4.2: finite cloud-cover primitives and type-specific detail.
  The paper's own evaluation found its cirrus unconvincing, so its hierarchy
  informs the model rather than establishing a visual acceptance criterion.

The procedural high-cloud field is independently authored. These references
contribute modeling principles, not copied shader code or texture assets.

## Density and filtering

`Resources::prepareCloudNoise` generates three periodic textures once per
device. All three have complete mip chains, built by the cloud noise filter:

| Texture | Extent | Format | Channels |
| --- | --- | --- | --- |
| Base shape | 128 cubed | RG16F | Cumulus shape and its square |
| Erosion | 32 cubed | RGBA8 | Three detail frequencies |
| Weather | 512 square | RGBA16F | Coverage and its square, cumulus type, finished high-cloud density |

The base period defaults to 1024 meters. Erosion occupies one quarter of that
period and weather sixteen periods. Camera motion neither regenerates noise
nor publishes a different density field. Wind translates both layers in the
same world frame, with a shared sixteen-period wrap.

Clouds have two non-overlapping curved shells. The lower shell contains
cumulus with local thickness, taper and anvil development driven by weather.
Rain builds a continuous stratiform component beneath the taller cells. The
upper shell contains swept filaments, irregular tufts and larger clear regions.
`cloud_shape.slang` evaluates multiscale material through a periodic curl-flow
coordinate map, then combines it with local and regional coverage. Twelve
backward midpoint steps run only during the density bake. The potential uses
the analytic derivative of the existing Perlin primitive in `cloud_noise.slangh`.
The continuous velocity is divergence-free; its finite-step coordinate map
only approximates area preservation.

The finished horizontal density is stored in the weather texture's alpha
channel. Its 16384-meter period and 512 texels give a 32-meter texel spacing at
the default scale. A continuous height profile turns this field into a thin
volume with a base of 6300 meters, thickness of 200 meters and unit-density
extinction of 0.006 per meter. These defaults retain the 6400-meter layer center
and extinction-times-thickness product of the former 800-meter layer, while
reducing the horizontal averaging of fine filaments along oblique rays.
The runtime keeps it at least 1000 meters above the cumulus top. Its coverage
can be set to zero without changing lower-cloud transport.

For cumulus, `cloud_density.slang` applies the coverage threshold once, followed
by bounded erosion and a continuous height profile. Footprints select the noise
mip level. The first and second moments preserve unresolved variation through the
nonlinear coverage threshold, using a moment-matched distribution. This is a
filtering approximation: it does not retain every correlation between weather,
shape and the local height profile. The smooth height profile is integrated
analytically over the vertical footprint so a coarse sample cannot lose an
entire thin column just because its midpoint lies above the column top.
At a shell boundary, that vertical footprint uses the actual last cell span.
Prefix checkpoints retain the original cell's sample and footprint so splitting
a ray does not change its medium evaluation.

High-cloud amount fades the pre-shaped density, including the tails, instead
of applying another threshold to filtered fine detail. Low-frequency weather
changes the relative amount between regions. This control is monotone and
bounded, with exact empty/full endpoints; it is not a literal percentage of
sky area. Extinction independently controls optical thickness. Its mip chain
stores linear mean density. Filtering the material and regional control
separately still approximates their unresolved correlation.
The volume participates in the shared extinction,
light visibility and in-scattering calculations. The horizontal morphology is
procedural, not a thermodynamic simulation of ice formation.

All rays share shells with a 6360-kilometer radius and a tangent frame for the
current view. Stable sphere roots and altitude evaluation avoid subtracting
nearly equal squared planet radii. A grazing ray may intersect either shell
twice. View bounds retain both segments and skip the clear air between them.
The shells supply bounds and altitude only; they introduce no opaque ground
sphere below the horizon.

## Light and weather ownership

The host publishes the atmosphere and celestial lights from the current
environment state. When volumetric clouds are active, the authored weather
panorama is not drawn and rain does not apply an additional empirical dimming
factor to direct sunlight. Cloud extinction supplies the weather occlusion.
Classic clouds and disabled volumetric clouds retain their authored weather
behavior.

`SkyAtmosphere` evaluates clear-air solar and lunar transport at the bottom and
top of both cloud shells. These four RGB/world-altitude samples travel through
the optional `LightInfoCloudRadianceProfileEXT` extension. The SDK copies and
validates the inline data. Existing clients can omit it and retain constant
cloud irradiance. A source that is dark at the camera can remain available to
high clouds without becoming an active surface light.

The shader interpolates this profile at each cloud sample's altitude. It uses
the same Rayleigh and aerosol coefficients as the host atmosphere. Four height
knots and the shared tangent-frame celestial direction are approximations to
full per-position spherical atmospheric transport. They do not introduce a
sunset color ramp or a saturation multiplier.

Diffuse cloud illumination uses the upper-hemisphere radiance integral divided
by four pi. `RtxGlobalVolumetrics` integrates the current lighting environment
once per frame into a shared one-texel image. The GPU reduction uses 8192
equal-area Hammersley directions fixed in the world frame, including low sky
elevations that carry twilight radiance. Its pattern does not rotate with the
sun or align a coarse azimuth sample with the narrow aerosol peak. A constant
environment contributes exactly half its radiance. Dome lighting and the
fallback cube probe use the same rule. Camera, secondary, sky-map and composite
paths read the same result without a CPU readback.

## Transport

World-volume transport integrates extinction and in-scattering along each ray
through the existing atmosphere-segment integrator. Fog and cloud contributions
share a Beer-Lambert transfer. Camera, reflection, refraction and light
visibility use the same density field, with footprints appropriate to each
integration. View distance fading remains a rendering approximation; it does
not shorten the celestial shadow path.

Self-shadowing integrates optical depth toward the sun and moon on fixed
exponential cells. The moving shell exit clips the last cell instead of
stretching every cell. Wide cells use two-point Gaussian quadrature, with the
refinement decision based on the unclipped cell width. Light rays keep one
grid across the inner clear-air gap, so a new grazing intersection cannot
reset the far segment's samples. Each sample evaluates only the current layer.
The high shell uses its maximum chord above the lower atmosphere and a smaller
cell budget. These choices reduce
undersampling and temporal jumps without allocating a shadow volume or adding
a separate shadow history. Real low-sun shadow motion remains in the geometry.

Single scattering uses a normalized dual-lobe Henyey-Greenstein phase function
and the measured optical depth toward each light. Diffuse illumination uses a
local plane-parallel column aligned with the shell's radial direction. The
column fixes its weather sample and uses the shared density evaluator for its
three-dimensional shape and erosion. Its support includes both the cumulus
and rain profiles at that same weather-filter footprint. The resulting optical
depths above and below the scattering point are reused for sky and celestial
illumination.

`cloud_scattering.slang` solves a two-stream boundary-lit slab with ordinate
cosine `1 / sqrt(3)`. Its upper boundary is the measured sky radiance and its lower
boundary is black. The boundary solution uses transport optical depth
`(1 - meanCosine) * opticalDepth`. It preserves a uniform environment on both
boundaries, approaches the hemisphere average as the slab becomes transparent,
and attenuates the sky reaching a thick cloud base. No ground-reflection source
is assumed.

The collimated-light solution generates a separate diffuse source from the
incident beam. Its two vertical streams use unit cosine, a conservative escape
approximation for the independently resolved single-scattering phase. It
vanishes continuously at zero thickness and grazing incidence.
The illuminated boundary follows the sign of the radial light cosine. Cloud
optical depth beyond that local column attenuates its incident beam. The direct
source retains the full three-dimensional light ray. This closure approximates
horizontal diffusion and multiple scattering in an irregular cloud. It does
not replace their transport with a second density field or a color ramp.

Fog subdivisions reuse a cloud cell's extinction and incident source. A prefix
checkpoint recomputes the same fixed cell sample, so splitting a ray preserves
the medium evaluation. This is deterministic volume ray marching with
approximate multiple scattering, **not a stochastic volumetric path tracer**.
The surface path tracer remains the renderer for surfaces.

Atmosphere segments also accumulate cloud opacity and the first extinction
distance moment. The constant-cell moment is analytic and composes across
prefix checkpoints and clipped continuations. The stored motion guide packs
conditional mean distance and opacity into one half2 word; radiance and
transmittance retain their existing precision. The guide reaches the normal
G-buffer motion path, including camera translation and inter-frame wind.
Camera cuts and discontinuous cloud frames reset the wind history.

Sky-map transport integrates the same layers into a camera-centered
equirectangular radiance/transmittance texture. Background rays reuse it,
while light visibility stays world-space. Its distance texture supplies the
cloud motion guide. Secondary rays approximate parallax with the camera-origin
map, and map transport approximates cloud occlusion against local geometry.
The transport option remains independent of host quality-profile names.

## Quality and cost

The host uses Ultra as the reference configuration. Lower profiles reduce
integration and map budgets while preserving the same density and lighting
model:

| Profile | View transport | Map height | View quality | Light cells |
| --- | --- | ---: | ---: | ---: |
| Ultra | World volume | 1024 when map mode is selected | 160 | 16 |
| High | Sky map | 1024 | 128 | 12 |
| Medium | Sky map | 640 | 96 | 8 |
| Low | Sky map | 384 | 64 | 4 |

Maps have a 2:1 aspect ratio. World-volume mode can generate a separate
64-pixel-high map for fog illumination. View quality controls spatial spacing,
so long rays can take more samples than the quality value. Light cells are
integration intervals; a wide interval uses two density queries. The upper
layer uses half the light-cell budget with a minimum of four cells.

Diffuse-column sampling uses half the light-cell budget, rounded up with a
minimum of two. Ultra, High, Medium and Low therefore use 8, 6, 4 and 2 samples
per occupied low-cloud cell. One shared weather lookup and at most two
base/detail lookups per sample add at most 17 texture reads at Ultra. The
high layer uses two density samples. Both celestial lights and the sky reuse
the same column. No additional volume texture or lighting history is allocated.
The environment integral uses one 256-thread workgroup and 8192 texture reads
per frame, shared across all quality levels. Its output contains one RGBA32F
texel, with allocation overhead determined by the driver. Each cloud ray reads
that cached texel instead of repeating a hemisphere integration.

The three noise textures and their mip chains occupy about 12.0 MiB before
driver allocation overhead. They are independent of output resolution. Motion
guides add one word per primary atmosphere record and one per checkpoint. At
1920 by 1080 internal resolution with the Ultra checkpoint layout this adds
about 19.8 MiB to path storage. These are storage calculations, not measured
GPU performance. Wider shadow cells, the extra cloud layer and larger map
budgets require hardware profiling before assigning a frame-time cost.
High-density evaluation needs one weather-texture lookup. Curl-flow construction
and material shaping are confined to the once-per-device generator. The finite
16384-meter texture period remains a memory/detail tradeoff and is visible in
large orthographic distribution maps.

## Numerical validation

The optional Vulkan readback tests execute production Slang helpers and can
use either a hardware device or a software ICD. Install `numpy` and `slangpy`
in the Python environment used by the test, then run from `kavora-runtime`:

```sh
python tests/rtx/unit/test_cloud_transport.py
python tests/rtx/unit/test_cloud_scattering.py --device vulkan
python tests/rtx/unit/test_atmosphere_moments.py
```

Equivalent Meson run targets have the same names. The tests compare Beer
integration, shell intersections, noise mip averages, light profiles, shadow
quadrature and motion moments with independent analytic or numerical
references. High-cloud checks also compare analytic noise derivatives with
finite differences and column transmission at 100-, 200- and 800-meter layer
thicknesses with the independent height-profile integral. They do not validate
game presentation, temporal reconstruction quality or GPU frame time.
The scattering test checks sky quadrature normalization and angular moments
in several up frames. It compares the production boundary and beam solutions
with independent integrals, exercises the thin and grazing limits, and integrates
outgoing slab flux with the actual dual-HG single-scattering phase. Its parameter
grid covers the supported anisotropy range and maximum multiple-scattering
strength. This checks that grid, not energy conservation for every heterogeneous
three-dimensional cloud. `--device cpu` also runs these math kernels through
Slang's CPU backend. The normal Slang compiler and SPIR-V validation
remain separate build gates.

## Visual morphology inspection

Install `numpy`, `Pillow` and `slangpy`, then run the optional preview from
`kavora-runtime`:

```sh
python tests/rtx/unit/render_cloud_preview.py --output /path/to/cloud-preview --radiance
```

The `render_cloud_preview` Meson run target writes to its build directory.
The script executes the production noise generators, mip filter, density,
transmittance and cloud scattering helpers on Vulkan. It saves a vertical
column optical-depth map and perspective views at several elevations and
headings, along with linear numerical output and a parameter/source manifest.
The default map is 32 kilometers wide. `--origin`, `--wind`, `--coverage`,
`--weather` and `--layers` vary the test conditions. `--shader-root` selects a
different revision's shader directory for a matched comparison. Generated
textures are cached by their source fingerprint. A test-only `--noise-seed`
override exercises other realizations of the same generator.
`--sun-elevation` and `--sun-azimuth` select diagnostic light direction;
`--sun-irradiance-rgb` and `--ambient-rgb` select diagnostic illumination.
`--high-base`,
`--high-thickness` and `--high-extinction` isolate the physical layer geometry.
Selecting an earlier shader root does not load its historical native option
defaults. Pass the intended layer parameters explicitly when comparing revisions.

Radiance previews default to fixed diagnostic sunlight, ambient radiance and a
constant background. `--atmosphere-fixture` instead reads a directory containing
`atmosphere.npz` and `manifest.json`. The NPZ supplies a linear RGBA `sky` array.
The manifest records the observer's `worldHeight`, dome `verticalScale`,
`sunDirection`, and `javaLighting.cloudIrradianceProfile`: four RGB/world-height
knots generated by `SkyAtmosphere`. The preview uses the production dome
projection and hemisphere quadrature. Fixture producers must record their
atmosphere inputs and source hashes in the manifest; the preview preserves that
manifest and hashes the NPZ in its output. The fixture observer height must
match the camera. An older shader root retains its own quadrature rule.

`--lighting all`, `direct` and `ambient` isolate the cloud sources while keeping
the same density and sky background. `--exposure` applies a fixed display-only
multiplier before sRGB encoding for PNGs. The saved numerical radiance and
transmittance remain unmodified. Compare revisions at identical fixture,
camera, layer parameters and exposure, including below-horizon solar angles.

These are cloud-transport diagnostics, not game captures. Even with a production
atmosphere fixture, they do not integrate air along the cloud ray, terrain,
visible celestial disks, exposure adaptation or temporal reconstruction.
Compare both opacity and radiance at identical settings. Inspect
distinct patches, fine internal filaments, tapered ends, spatial repetition
and distant merging. Inspect additional positions and wind phases before
accepting a shape change. Coverage statistics and numerical test success do
not establish natural appearance.
