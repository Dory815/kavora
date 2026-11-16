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
- [Dobashi et al., Modeling of Clouds from a Single Photograph, 2010](https://imelab.jp/doba/projects/photo_cloud_modeling/photo_cloud_modeling.htm):
  cloud types benefit from different representations, including two-dimensional
  morphology for cirrus. A photograph does not uniquely recover a cloud volume.
- [Webanck et al., Procedural Cloudscapes, 2018](https://doi.org/10.1111/cgf.13373),
  sections 4.1 and 4.2: finite cloud-cover primitives and type-specific detail.
  The paper's own evaluation found its cirrus unconvincing, so its hierarchy
  informs the model rather than establishing a visual acceptance criterion.

These rendering references contribute modeling principles, not copied code
or assets. High-cloud morphology uses a separately credited CC0 scalar atlas
derived from small cloud groups in three photographs by Estormiz and John
Robert McPherson. Its sources, crop bounds, reproducible preparation and
limitations are recorded in
[CIRRUS.md](../../kavora/packaging/runtime-textures/CIRRUS.md).

## Low-cloud morphology

The low layer follows the weather/shape/detail separation described in
[Schneider and Vos, 2015](https://www.guerrilla-games.com/read/the-real-time-volumetric-cloudscapes-of-horizon-zero-dawn).
The implementation and texture weights are authored here. Inverse-Worley
feature centers add convex billows to a broader Perlin envelope. A periodic
detail field displaces those billows and erodes their boundaries, so smaller
lobes remain attached to the main cloud instead of appearing only as detached
fragments. No Beer-Powder brightness term is used.

The low weather tile organizes regional cloud groups and clear corridors.
At the default shape scale its coverage octaves span 8192, 4096, 2048 and
1024 meters. A 512-meter cell field adds smaller updraft groups. The finest
coverage octave and cell field have eight and four weather texels per cell,
respectively. Cloud type changes over larger 16384- and 8192-meter scales.

A separate vector phase varies the base volume within each region. Four
integer hashes define the corners of a lattice with four shape periods per
cell, and quintic interpolation joins them with continuous first and second
derivatives. Each component stays within one quarter of a shape period:
4096-meter lattice cells and up to 256 meters of displacement at the default
scale. The largest component derivative is `0.5 * 1.875 / 4 = 0.234375`.
The horizontal derivative row sum remains below one, preventing folds of the
horizontal coordinate mapping. This field is independent of coverage and
weather controls, follows the same world advection, and is cached with the
local column for density and illumination. It is a bounded procedural shape
variation, not a simulated wind velocity or a thermodynamic cloud model.

Coverage controls occupancy separately from the condensation ramp. The height
profile and erosion are applied before the density threshold; decreasing
regional coverage therefore opens the sky without turning every remaining
cloud into transparent smoke. Vertical noise coordinates are relative to the
cloud base, so changing altitude moves the same field instead of silently
selecting another three-dimensional noise slice. The default condensation offset
is 608 meters above the host cloud height: an 800-meter base with the usual
192-meter host height. A 1500-meter maximum thickness still bounds the layer;
local weather determines each formation's smaller actual height.

The default unit-density extinction is 0.03 per meter. Separating coverage
from condensation increased density inside the retained cores; keeping the
former 0.06-per-meter coefficient made the fair-weather field too optically
thick in the photo comparisons. Recalibrating that coefficient changes optical
depth rather than color or exposure. For scale, the large-droplet relation
`sigma = 3 * LWC / (2 * rho_water * r_effective)` in
[Wood, 2006, equation 5](https://faculty.washington.edu/robwood2/wordpress/wp-content/uploads/2014/06/optical_depth_relations.pdf)
associates 0.03 per meter at unit density with 0.2 grams of liquid water per cubic
meter if the effective droplet radius is 10 micrometers. These are illustrative
microphysical assumptions, not values measured from the reference photographs.

Review uses both individual clouds and whole-sky views of natural shallow
cumulus, including [Toby Hudson's whole-sky photograph](https://commons.wikimedia.org/wiki/File:Cumulus_humilis_clouds.jpg)
and [Juan Lacruz's shallow cumulus photograph](https://commons.wikimedia.org/wiki/File:Cumulus-humilis.jpg):
unequal connected lobes, mostly white sunlit bodies with local soft gray
undersides, irregular blue openings, and a continuous near/middle/far size
hierarchy. Mixed cumulus/stratocumulus photographs also retain locally darker
cloud bases; the review does not require every shaded face to become white.
Numerical density moments are filtering checks, not a visual acceptance criterion.

## Density and filtering

`Resources::prepareCloudNoise` generates three periodic textures once per
device. All three have complete mip chains, built by the cloud noise filter:

| Texture | Extent | Format | Channels |
| --- | --- | --- | --- |
| Base shape | 128 cubed | RG16F | Cumulus shape and its square |
| Erosion | 32 cubed | RGBA8 | Three detail frequencies |
| Weather | 1024 square | RGBA16F | Coverage and its square, cumulus type, finished high-cloud density |

The base period defaults to 1024 meters. Erosion occupies one sixteenth of that
period. Low-cloud weather occupies 128 base periods (131072 meters by default),
and high-cloud weather occupies 32. Camera motion neither regenerates noise nor
publishes a different density field. Wind translates both layers in the same
world frame, with a shared wrap at the larger of these power-of-two periods.
The low shape phase has the same 128-period wrap. These are finite periodic
fields; a sufficiently large orthographic map can still expose the full repeat.

Clouds have two non-overlapping curved shells. The lower shell contains
cumulus with local thickness, taper and anvil development driven by weather.
Rain builds a continuous stratiform component beneath the taller cells. The
upper shell contains feathered cloud groups and larger clear regions.
`cloud_shape.slang` places four finite scalar morphology variants in regional
groups with varied size, position, heading and transverse reflection. The
source crops' aspect ratios are retained, and their main directions follow
a smooth regional flow. Regional humidity controls the amount of cloud,
including broad clear areas. Placement and atlas sampling run only during
the weather bake. Analytic texture-coordinate gradients preserve the
anisotropic footprint of each transformed tile.

`Resources` loads the linear R8 atlas through the existing texture manager,
waits for its upload before enabling cloud sampling, and releases its pinned
reference after recording the bake. The 1024-square atlas and its mip chain
occupy about 1.33 MiB while resident. No source photographs are loaded at
runtime, and no per-ray atlas lookup or placement loop is added.

The finished horizontal density is stored in the weather texture's alpha
channel. Its 32768-meter period and 1024 texels give a 32-meter texel spacing at
the default scale. A continuous height profile turns this field into a thin
volume with a base of 6300 meters, thickness of 200 meters and unit-density
extinction of 0.006 per meter. These defaults retain the 6400-meter layer center
and extinction-times-thickness product of the former 800-meter layer, while
reducing the horizontal averaging of fine filaments along oblique rays.
The runtime keeps it at least 1000 meters above the cumulus top. Its coverage
can be set to zero without changing lower-cloud transport.
The weather mip chain occupies about 10.67 MiB, an 8 MiB increase over the
512-square field. The smaller texel spacing retains more feather structure
than a 512-square texture over this larger period, though very fine source
fibres remain unresolved. These are storage sizes, not measured GPU timings.

For cumulus, `cloud_density.slang` applies its continuous height profile,
bounded shape displacement and boundary erosion before one condensation
threshold. View footprints select the noise mip level. The first and second
moments preserve unresolved variation through this nonlinear threshold, using
a moment-matched distribution. This is a filtering approximation: it does not
retain every correlation between weather, shape, erosion and the local height
profile. The smooth height profile is integrated
analytically over the vertical footprint so a coarse sample cannot lose an
entire thin column just because its midpoint lies above the column top.
At a shell boundary, that vertical footprint uses the actual last cell span.
Prefix checkpoints retain the original cell's sample and footprint so splitting
a ray does not change its medium evaluation.
For the high layer's two-dimensional field, the density footprint uses the
ray cell's horizontal projection and the pixel footprint. The independent
height footprint integrates the layer profile. A vertical ray therefore
does not blur horizontal filaments merely because it advances through height.

High-cloud amount fades the pre-shaped density, including the tails, instead
of applying another threshold to filtered fine detail. Low-frequency weather
changes the relative amount between regions. This control is monotone and
bounded, with exact empty/full endpoints; it is not a literal percentage of
sky area. Extinction independently controls optical thickness. Its mip chain
stores linear mean density. Filtering the material and regional control
after combining them retains the mean of their product. The volume participates
in the shared extinction, light visibility and in-scattering calculations.
The scalar input is an authored relative shape estimate, not measured optical
depth or a thermodynamic simulation of ice formation. The native volume model
supplies extinction, layer thickness and atmospheric lighting.

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
through the existing atmosphere-segment integrator. Physical air, authored fog
and cloud contributions share a Beer-Lambert transfer. Camera, reflection, refraction and light
visibility use the same density field, with footprints appropriate to each
integration. Both cloud layers default to a 96-kilometer view range. View
distance fading remains a rendering approximation; it does
not shorten the celestial shadow path.

The host publishes the existing atmospheric optical tables and completed light
state through `LightInfoAtmosphereEXT`. Finite air transport attenuates distant
cloud contrast and adds in-scattered atmospheric radiance at the actual ray
distance. Full clear-sky radiance remains the cloud lighting environment;
view rays begin with an exterior boundary that excludes the integrated air.
See [air-transport.md](air-transport.md) for ownership, units and approximations.

The shared `CloudRayGrid` resolves nearby clouds at the spatial budget and
grows cells geometrically once the projected pixel footprint is wider. Its
forward boundaries and inverse cell lookup are shared by view transmission,
atmosphere segments and the sky pass. Prefix checkpoints and clipped tails
therefore retain the same samples. Density filtering uses the actual cell span
and pixel cone, including the final partial cell.

Low-cloud self-shadowing integrates optical depth toward the sun and moon on
a fixed distance grid anchored at the ray origin. With the default shape scale
and Ultra quality, each 64-meter cell has two Gaussian nodes; each node
represents one fixed 32-meter half-cell. The shell entry selects the existing
support index rather than moving the grid. Shell boundaries, finite endpoints
and the local illumination boundary clip only integration weights. Samples
and their density and height footprints stay fixed. The local and exterior
optical depths therefore partition the same positive sampled field.

Ordinary density lookups are filtered to at most one base texel across the
light ray: a cell-sized isotropic mip would mix neighboring off-ray clouds
into otherwise clear sunlight paths. Height-profile integration uses each
sample's vertical support. Very small custom shape scales can exceed the
finite query budget; only then does the fixed support widen, with an additional
continuous density filter for the unresolved width. That budget fallback loses
shadow detail and is not equivalent in precision to an unlimited fine trace.
It leaves the default grid and its filtering unchanged.

The high shell retains fixed exponential cells with two-point quadrature when
wide enough. It uses its maximum chord above the lower atmosphere and a smaller
cell budget. Both layers keep one grid across the inner clear-air gap, so a new
grazing intersection cannot reset the far segment's samples. Each sample
evaluates only the current layer. No shadow volume or separate shadow history
is allocated. Real low-sun shadow motion remains in the geometry.

Single scattering uses a normalized dual-lobe Henyey-Greenstein phase function
and the measured optical depth toward each light. Diffuse illumination uses a
local plane-parallel column aligned with the shell's radial direction. The
column fixes its weather sample and uses the shared density evaluator for its
three-dimensional shape and erosion. Its support includes both the cumulus
and rain profiles at that same weather-filter footprint. The resulting optical
depths above and below the scattering point are reused for sky and celestial
illumination.

`cloud_scattering.slang` solves a two-stream boundary-lit slab with ordinate
cosine `1 / sqrt(3)`. Its upper boundary is the measured sky radiance. The
lower boundary is a local Lambertian terrain approximation with mean reflectance
`rtx.clouds.groundAlbedo` (default 0.18). Terrain receives the sky and celestial
flux transmitted through the cloud, including the downward diffuse beam flux.
The closure sums repeated reflections between the conservative column and the
terrain: `L_ground = rho * (T * L_sky + E_beam / pi) / (1 - rho * R)`, where
`T + R = 1`. Reflected flux returns only through the lower boundary; it is not
also added directly to the cloud source. A black terrain recovers the previous
boundary, while a uniformly lit conservative white cavity preserves radiance.

The boundary solution uses transport optical depth
`(1 - meanCosine) * opticalDepth`. This is an average local terrain boundary,
not a readback of actual terrain materials or full three-dimensional indirect
lighting. Surface path tracing continues to use the scene's materials. Cloud
irradiance profiles describe the cloud-altitude light; the separate light
irradiance member supplies the host's actual observer-height irradiance for
the terrain approximation, avoiding use of the brighter high-cloud profile
as a ground source at sunset.

The collimated-light solution generates a separate diffuse source from the
incident beam. Its two vertical streams use unit cosine, a conservative escape
approximation for the independently resolved single-scattering phase. It
vanishes continuously at zero thickness and grazing incidence.
The illuminated boundary follows the sign of the radial light cosine. Cloud
optical depth beyond that local column attenuates its incident beam. The direct
source retains the full three-dimensional light ray. This closure approximates
horizontal diffusion and multiple scattering in an irregular cloud. It does
not replace their transport with a second density field or a color ramp.

For finite cumulus, the same directional shadow trace separates optical depth
inside one shape-period neighborhood from optical depth outside it. The fixed
sample supports are weighted on both sides of this boundary, rather than
assigning a Gaussian node discontinuously to a side. A second ray measures only the
opposite half of that local neighborhood when a side-light contribution is
needed. The existing vertical samples also define a continuous piecewise-linear
profile; integrating it along each light ray predicts the optical depth of a
plane-parallel column over the **same local range**, without additional density
lookups. The difference between that prediction and the measured local depth
controls a convex blend with a beam-axis two-stream slab. Exterior blockers
attenuate the side slab's incident beam exponentially and cannot change the
geometric blend weight. A homogeneous column recovers the vertical model; a
horizontal beam can illuminate a finite cloud through its side. No tint or
ambient brightness floor is added.

This finite neighborhood is not a connected-cloud detector: it can include
several nearby billows or truncate a larger cloud. The method also omits diffuse
exchange between separate neighborhoods and does not solve a full 3D radiance
field. [Hogan et al., 2016](https://www.met.reading.ac.uk/~swrhgnrj/publications/spartacus_part2.pdf)
explains the physical role of lateral cloud transport; this local rendering
closure is independently derived and does not implement the SPARTACUS solver.

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
model. With the physical atmosphere, every profile uses world-volume transport.
The requested sky-map mode applies only to hosts without that extension:

| Profile | Requested transport without physical air | Map height | View quality | Light quality |
| --- | --- | ---: | ---: | ---: |
| Ultra | World volume | 1024 when map mode is selected | 160 | 16 |
| High | Sky map | 1024 | 128 | 12 |
| Medium | Sky map | 640 | 96 | 8 |
| Low | Sky map | 384 | 64 | 4 |

Maps have a 2:1 aspect ratio. World-volume mode can generate a separate
64-pixel-high map for fog illumination. View quality controls spatial spacing,
so long rays can take more samples than the quality value. At the default
1024-meter shape period, the low-layer base spacing is 8 meters at Ultra, down
from 16 meters before this rework. Light quality controls spatial resolution,
not the actual density-query count. At Ultra, low-layer shadow paths of
0.25, 1, 5 and 60 kilometers require up to 8, 32, 157 and 1875 density evaluations
at the default scale. The previous sparse exponential quadrature used up to
124 evaluations but could miss entire narrow clouds. This is a substantial
sampling-cost increase. Visibility can terminate once transmittance is below
`1e-8`. The illumination trace retains the additional depth needed by the local
column closure; near-horizontal light can require the full range even through
occupied clouds. The 1875-query bound must not be interpreted as an empty-ray
case alone. An out-of-column evaluation returns after its weather lookup;
occupied samples also read base and detail textures.
Preparing a column with nonzero cumulus coverage adds four integer hashes and
quintic interpolation for its shape phase, with no additional texture lookup.
The vertical lighting samples reuse that prepared phase. Empty coverage skips
the hash calculation. This arithmetic is additional work, even though texture
memory and the number of density queries are unchanged.
Splitting the local boundary adds no queries. A finite-side solve can add up
to 32 queries for its 1024-meter reverse ray, giving a default low-layer maximum
of 1907 queries per celestial light before early termination. Light visibility
does not need that reverse trace. The upper layer uses half the light-quality
value, with a minimum of four cells and at most two queries per cell.

The low-layer forward trace has an explicit cap of `256 * lightSteps` queries:
4096, 3072, 2048 and 1024 for Ultra, High, Medium and Low. Its support is at least
the full configured shadow range divided by one less than that cap. This
limit depends on the full range, never the current shell exit or prefix length,
so clipping cannot relocate the grid. At the standard 60-kilometer range the
cap affects shape scales smaller than about 469 meters; ordinary default
sampling remains below it. This prevents extreme user scales from creating
unbounded GPU work. The fallback's extra filtering widens continuously with
the square root of the additional squared support width.

Diffuse-column sampling uses the light-cell budget with a minimum of two.
Ultra, High, Medium and Low therefore use 16, 12, 8 and 4 samples per occupied
low-cloud cell. One shared weather lookup and two base/detail lookups per
sample add at most 33 texture reads at Ultra. The high layer uses two density
samples. Both celestial lights and the sky reuse
the same column. No additional volume texture or lighting history is allocated.
The environment integral uses one 256-thread workgroup and 8192 texture reads
per frame, shared across all quality levels. Its output contains one RGBA32F
texel, with allocation overhead determined by the driver. Each cloud ray reads
that cached texel instead of repeating a hemisphere integration.

The three noise textures and their mip chains occupy about 20.0 MiB before
driver allocation overhead. They are independent of output resolution. Motion
guides add one word per primary atmosphere record and one per checkpoint. At
1920 by 1080 internal resolution with the Ultra checkpoint layout this adds
about 19.8 MiB to path storage. These are storage calculations, not measured
GPU performance. Denser shadow integration, the extra cloud layer and larger
map budgets require hardware profiling before assigning a frame-time cost.
High-density evaluation needs one weather-texture lookup. The finite feather
atlas is sampled only during the once-per-device weather bake, then released.
The high field's 32768-meter texture period remains a memory/detail tradeoff
and is visible in large orthographic distribution maps. Finite-air resource
costs are recorded separately in [air-transport.md](air-transport.md).

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
references. High-cloud checks also compare column transmission at 100-,
200- and 800-meter layer
thicknesses with the independent height-profile integral. They do not validate
game presentation, temporal reconstruction quality or GPU frame time.
Low-cloud checks exercise the shared 128-period wind wrap, negative
coordinates, phase bounds, continuity and derivative bounds at the phase
lattice boundaries, and independence from coverage and weather controls.
Fixed light-support checks exercise clipped-prefix linearity, local/exterior
partition invariance, unchanged default quality grids and full-range traces
at the smallest supported shape scales.
The scattering test checks sky quadrature normalization and angular moments
in several up frames. It compares the production boundary and beam solutions
with independent integrals, exercises reflective-terrain, finite-domain,
external-blocker, thin and grazing limits, and integrates
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
textures are cached by their shader and atlas-byte fingerprint. A test-only `--noise-seed`
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

These are cloud-transport diagnostics, not game captures. A production
atmosphere fixture supplies sky and cloud illumination. Adding `--air` also
runs the production finite-distance air/cloud integrator. The preview does
not include terrain, visible celestial disks, exposure adaptation or temporal
reconstruction. Orthographic maps retain cloud-only optical depth.
Compare both opacity and radiance at identical settings. Inspect
distinct patches, fine internal filaments, tapered ends, spatial repetition
and distant merging. Inspect additional positions and wind phases before
accepting a shape change. Coverage statistics and numerical test success do
not establish natural appearance.
