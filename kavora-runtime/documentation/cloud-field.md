# Cloud density and transport

The native density field adapts the weather distribution and cloud profiles
from [Community Edition](https://github.com/CuteEthanLeo/rtx-remix-minecraft-ce),
revision `94400621dabc6b315d8e53b701c7be7beffa9303`. Its source and Apache-2.0
notice are recorded under `documentation/licenses/RTX-Remix-CE-Clouds.txt`.

[Photon](https://github.com/sixthsurge/photon/tree/2a3d502c17d2e310412c717be47241f014cba7fc)
was studied as a visual reference for cloud layers, weather, erosion and
atmospheric lighting. No Photon shader code or assets are included.

## Density and filtering

`Resources::prepareCloudNoise` generates three periodic textures once per
device. All three have complete mip chains, built by the cloud noise filter:

| Texture | Extent | Format | Channels |
| --- | --- | --- | --- |
| Base shape | 128 cubed | RGBA16F | Cumulus shape and its square, high-cloud shape and its square |
| Erosion | 32 cubed | RGBA8 | Three detail frequencies |
| Weather | 512 square | RGBA16F | Coverage and its square, cumulus type, high-cloud coverage |

The base period defaults to 1024 meters. Erosion occupies one quarter of that
period and weather sixteen periods. Camera motion neither regenerates noise
nor publishes a different density field. Wind translates both layers in the
same world frame, with a shared sixteen-period wrap.

Clouds have two non-overlapping curved shells. The lower shell contains
cumulus with local thickness, taper and anvil development driven by weather.
Rain builds a continuous stratiform component beneath the taller cells. The
upper shell contains stretched, sheared wisps with independent weather
coverage. Its default base is 6000 meters and its thickness is 800 meters.
The runtime keeps it at least 1000 meters above the cumulus top. Its coverage
can be set to zero without changing lower-cloud transport.

`cloud_density.slang` applies the coverage threshold once, followed by bounded
erosion and a continuous height profile. Footprints select the noise mip level.
The first and second moments preserve unresolved variation through the
nonlinear coverage threshold, using a moment-matched distribution. This is a
filtering approximation: it does not retain every correlation between weather,
shape and the local height profile. The smooth height profile is integrated
analytically over the vertical footprint so a coarse sample cannot lose an
entire thin column just because its midpoint lies above the column top.

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

Diffuse cloud illumination uses a sixteen-sample upper-hemisphere radiance
integral divided by four pi. It is evaluated once per cloud integration ray,
not once per density cell. The quadrature includes low sky elevations that
carry twilight radiance. A constant environment therefore contributes half
its radiance to this upper-hemisphere source.

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

The phase function is a normalized dual-lobe Henyey-Greenstein mixture.
Higher-order scattering and thick-layer diffuse transmission remain explicit
approximations. Each higher order includes the probability of another
scattering event, preserving the optically thin limit. This is deterministic
volume ray marching with approximate multiple scattering, **not a stochastic
volumetric path tracer**. The surface path tracer remains the renderer for
surfaces.

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

The three noise textures and their mip chains occupy about 21.1 MiB before
driver allocation overhead. They are independent of output resolution. Motion
guides add one word per primary atmosphere record and one per checkpoint. At
1920 by 1080 internal resolution with the Ultra checkpoint layout this adds
about 19.8 MiB to path storage. These are storage calculations, not measured
GPU performance. Wider shadow cells, the extra cloud layer and larger map
budgets require hardware profiling before assigning a frame-time cost.

## Numerical validation

The optional Vulkan readback tests execute production Slang helpers and can
use either a hardware device or a software ICD. Install `numpy` and `slangpy`
in the Python environment used by the test, then run from `kavora-runtime`:

```sh
python tests/rtx/unit/test_cloud_transport.py
python tests/rtx/unit/test_atmosphere_moments.py
```

Equivalent Meson run targets have the same names. The tests compare Beer
integration, shell intersections, noise mip averages, light profiles, shadow
quadrature and motion moments with independent analytic or numerical
references. They do not validate game presentation, temporal reconstruction
quality or GPU frame time. The normal Slang compiler and SPIR-V validation
remain separate build gates.
