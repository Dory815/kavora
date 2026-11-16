# Cloud-system redesign research

This document records the visual and architectural references used for the cloud redesign. The goal is not to reproduce any shaderpack's screenshots or source. It is to identify recurring design decisions that produce plausible skies across different cloud amounts, weather states, sun angles and camera elevations, then implement those decisions in Kavora's own world-space density and transport pipeline.

## Reference survey

### Photon

Repository: https://github.com/sixthsurge/photon

Photon exposes separate controls for cumulus, altocumulus, cumulus congestus, cirrus and noctilucent clouds, alongside a common cloud scale and temporal upscaling. Its cloud menu is evidence of a type-based sky rather than one generic layer with one noise function. Its daily weather system also varies the sky as a coherent environment rather than changing only one coverage scalar.

Visual principles to study:
- distinct cloud families have different characteristic scales, vertical profiles and edge structures;
- multiple families may coexist without sharing identical coverage or motion;
- weather changes the composition and illumination of the whole sky;
- temporal reconstruction is part of the cloud quality/performance strategy.

Photon is ARR. No Photon source code, textures, screenshots as runtime assets, or derived source implementation are copied.

### Complementary Reimagined / Unbound

Official site: https://www.complementary.dev/reimagined/
Repository: https://github.com/ComplementaryDevelopment/ComplementaryReimagined
Cloud entry point: https://github.com/ComplementaryDevelopment/ComplementaryReimagined/blob/main/shaders/lib/atmospherics/clouds/mainClouds.glsl
Settings reference: https://github.com/ComplementaryDevelopment/ComplementaryReimagined/blob/main/shaders/lang/en_US.lang

Complementary deliberately offers different cloud styles. Reimagined supports a second cloud layer at a separately configured altitude; Unbound exposes cloud amount and cloud size independently. The renderer selects between cloud layers according to the view and whether the nearer layer actually contributes. This is a useful lesson: cloud amount, characteristic size, vertical placement and style are independent artistic controls, not interchangeable ways of turning one noise threshold.

Visual principles:
- a dense sky can remain natural when cloud size and regional coverage vary independently;
- secondary layers should add a different scale/type, not duplicate the first layer;
- a style should have coherent defaults while retaining independent controls for amount and scale.

### Revelation

Repository: https://github.com/HaringPro/Revelation
License: Apache-2.0
Cloud settings: https://github.com/HaringPro/Revelation/blob/dev/shaders/shaders.properties
Cloud renderer: https://github.com/HaringPro/Revelation/blob/dev/shaders/lib/atmosphere/clouds/Render.glsl

Revelation separates low, middle and high cloud configuration. Its low layer has distinct coverage, base/thickness/density and minimum/maximum view samples. High-level types have independent coverage and wind settings. It uses separate low/high weather maps, a vertical profile lookup, and a cirrus morphology input. It also includes empty-space skipping and a cloud-specific temporal upsampling path.

Visual and engineering principles:
- coverage and density profile should not be conflated;
- low, middle and high clouds have distinct morphology and distribution inputs;
- quality should adapt to ray length and empty regions, rather than assigning every ray a fixed expensive march;
- cloud temporal reconstruction is a targeted subsystem, not an accidental side effect of generic sky reprojection.

Kavora may use the same broad architectural ideas, but does not copy Revelation's shader code, density equations, lookup textures, authored maps or assets. Apache-2.0 permits reuse subject to its terms, but this redesign does not need source reuse.

### Nostalgia

Project page: https://modrinth.com/shader/nostalgia-shader
Source mirror: https://github.com/rre36/NostalgiaShader_Mirror

Nostalgia documents multiple volumetric cloud layers and also offers resource-pack-driven vanilla-style cloud texture support. Its release history notes that the volumetric approach replaced its earlier separate realistic and 2D cloud paths for performance and visual consistency.

Principles:
- preserve coherent cloud silhouettes across layers;
- multiple layers need not all be volumetric at the same complexity;
- a simple authored cloud map can be a valid distribution input when its visual role is clear, while lighting remains volumetric.

The published shaderpack is ARR/custom licensed; no code or assets are copied.

### Sildur's Vibrant Shaders

Project and changelog references:
- https://www.curseforge.com/minecraft/shaders/sildurs-vibrant-shaders
- https://github.com/Sildurs-shaders/sildurs-shaders.github.io/blob/master/changelogs/index.html

Sildur's documents selectable default, 2D and volumetric cloud modes, including combined modes. This is a useful contrasting design point: cloud representation and rendering cost are exposed as deliberate choices. Kavora's path-traced scene should keep its own physical volume representation, but can still use separate distribution/shape inputs and explicit quality budgets.

No Sildur's source or assets are copied.

### BSL and AstraLex

Project references:
- https://bitslablab.com/
- https://modrinth.com/shader/astralex/

These packs are included in the visual survey as widely used alternatives with distinct stylization and weather presentation. Their screenshots should be compared as complete skies, not used as density-field templates. No code or assets are copied.

## Natural-cloud references and review rules

The WMO International Cloud Atlas is the morphology reference for cloud genera and species:
- Cumulus: https://cloudatlas.wmo.int/en/species-cumulus-cu.html
- Stratocumulus: https://cloudatlas.wmo.int/en/species-stratocumulus-sc.html
- Altocumulus: https://cloudatlas.wmo.int/en/species-altocumulus-ac.html
- Cirrus: https://cloudatlas.wmo.int/en/species-cirrus-ci.html
- Cirrocumulus: https://cloudatlas.wmo.int/en/species-cirrocumulus-cc.html

Whole-sky and landscape photographs used to assess distribution, not just isolated cloud crops:
- Cumulus humilis, Toby Hudson: https://commons.wikimedia.org/wiki/File:Cumulus_humilis_clouds.jpg
- Cumulus humilis, Juan Lacruz: https://commons.wikimedia.org/wiki/File:Cumulus-humilis.jpg
- Cumulus mediocris, Janne Naukkarinen: https://commons.wikimedia.org/wiki/File:Cumulus_mediocris_3.JPG
- Cumulus mediocris, Kreuzschnabel: https://commons.wikimedia.org/wiki/File:Cumulus_mediocris-1.jpg

Review criteria:
1. Compare complete sky composition at matched field of view and exposure: cloud occupancy, connected groups, clear gaps, scale distribution and horizon behaviour.
2. Compare individual morphology: connected lobes, variable vertical development, soft but non-flat undersides, broken edges and internal billows.
3. Check multiple cloud amounts. A naturally overcast or cloud-rich sky is a valid target; a large blue-sky fraction is not a quality requirement.
4. Check sun-facing, side-lit and back-lit views at noon, golden hour and twilight. Reject global darkening as a substitute for shading.
5. Inspect multiple world positions and wind offsets for repetition, seams and periodicity.
6. Keep all failed renders in the review set. Do not choose only attractive views.
7. Numerical checks support filtering, energy and stability; they do not establish visual acceptance.

Photographs have different exposure, focal length, weather and viewing geometry. They are visual references, not direct measurements of 3D cloud size or optical depth. Any derived scalar mask must be documented and must not be used as a color texture.

## Kavora design direction

The previous single lower-shell field is too constrained as a model for the full range of natural skies. The redesign will treat cloud scene composition as a set of independently controlled but coexisting cloud families:

- boundary-layer cumulus: broad regional moisture/coverage, connected parent bodies, billow-scale vertical shape and fine erosion;
- stratocumulus / overcast: large connected sheets with cellular openings and variable thickness, not a screen-filling grid of isolated clumps;
- congestus: locally stronger vertical development within otherwise related cumulus regions;
- mid-level altocumulus: broad patches and rolls with a different scale and vertical profile;
- high cirrus: thin, detached and connected fibrous structures, with broad clear regions and varied orientation.

These are not required to be five expensive independent raymarches. Distribution and type selection should be baked into the existing weather resources; overlapping families should share a bounded ray traversal where practical. A type's density evaluator must be cheap, branch-coherent and bounded. Per-family coverage and vertical profile are independent of the scene-wide weather regime.

The existing world-space extinction, in-scattering, atmosphere coupling, path-traced surface lighting and shared directional cloud-shadow prefix remain the transport foundation. The redesign must not restore the former per-view-sample 60 km nested sun march. Any added family must have explicit view and light budgets, early empty-space rejection and a measured worst-case path.

The first implementation step is to prototype the new multi-family distribution as a deterministic weather bake and inspect top-down and whole-sky previews before changing transport. Later steps will integrate each family into a shared shell traversal, then validate performance and all affected ray consumers (camera, PSR, reflection, transmission and visibility).

## Licensing

References are studied for visual and architectural ideas only. The Kavora implementation remains independently authored. No ARR/custom shaderpack source, binaries, textures or photographs are shipped. Any separately licensed reference material used for a diagnostic mask must be explicitly attributed, license-checked and stored as a derived scalar field with source and transformation records; the preferred production direction is an independently generated procedural distribution.
