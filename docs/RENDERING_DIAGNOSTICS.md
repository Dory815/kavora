# Rendering diagnostics

Use the source and configuration from the same build. Record the mod version,
runtime provenance, resource packs, dimension, quality options, DLSS and frame
generation state. Preserve logs before another launch replaces them.

## Startup and world transitions

The runtime is the custom Vulkan 1.5.0 API build under `kavora-runtime/`.
An old DLL or missing dependent payload can fail before world capture starts.
Check the extraction/provenance log and the earliest native error.

A frozen process is more useful with a Java thread dump and native crash data
than repeated restarts. Use the JDK's `jcmd <pid> Thread.print` and preserve
`hs_err_pid*.log` if present. Do not collect launcher credentials. Development
launch redacts account arguments before loading the runtime.

World transitions must release the preceding generation even when JOIN and
DISCONNECT are not paired. Queue clears through the client executor and
recheck the session after the hop. Render hooks stop while the world is null;
a pending render-hook flag can accidentally clear the next world.

## Missing terrain

Inspect near capture, column assembly, native publication and coverage as
separate steps. A visible-set count alone does not show that a mesh reached
the runtime. A retained instance must be submitted after mutation.

A recapture snapshots built sections before vanilla reload, clears native
terrain, reloads vanilla terrain and explicitly queues the preceding built set.
`KavoraMod.rebuildLoadedTerrain()` owns this sequence.

Kavora Horizon observes delivered chunks only. Its metadata, read, mesh, expand,
upload and retire stages have separate counters. Check its bounded queues and
committed near-coverage mask before changing distance or adding wait times.
See [far terrain](FAR_TERRAIN.md).

## Materials and particles

Compare authored albedo, LabPBR channels, native upload/mip interpretation,
material flags and final lighting. A low-resolution or color-space mistake
can resemble a lighting difference. Animated upload order is part of the ABI.

Particles retain world-space positions and previous-vertex history. Motion
vectors and frame generation must use the same scene-frame IDs. A submitted
generated frame is not proof that it reached the display.

For water, distinguish the reflected and transmitted paths and their temporal
guides. Medium attenuation belongs to each segment; applying it twice can
produce dark overlays or visible quad boundaries.

## Cloud inspection without a game window

The opt-in scripts in `kavora-runtime/tests/rtx/unit/` execute production cloud
shaders on a Vulkan device, including a software ICD. Install NumPy, Pillow,
SlangPy and the Python `vulkan` binding in the test environment. The atmosphere
export also needs `glslangValidator` and a JDK with `Math.clamp` (Java 21 or
newer). These tools are not runtime dependencies.

`render_cloud_atmosphere.py` compiles the repository's `SkyAtmosphere.java` for
its optical constants and altitude-dependent direct irradiance, then runs the
four passes of `sky_atmosphere.comp`. It saves the sky, irradiance and optical
tables with source hashes and lighting parameters. From the repository root:

```sh
python kavora-runtime/tests/rtx/unit/render_cloud_atmosphere.py \
  --output /tmp/cloud-day --sun-elevation 40 --sun-azimuth 135 \
  --world-height 139 --profile-heights 800 2300 6300 6500
python kavora-runtime/tests/rtx/unit/render_cloud_preview.py \
  --output /tmp/cloud-inspection --layers low --radiance \
  --atmosphere-fixture /tmp/cloud-day --origin 8043,139,1240 \
  --low-base 800 --low-thickness 1500 --low-coverage 0.45 \
  --low-extinction 0.03 --low-max-distance 96000 --air \
  --width 1280 --height 800 --views zenith,45,horizon --exposure 0.1
```

Use the actual native cloud parameters for the revision under inspection;
`--shader-root` changes the shader source, not the CLI defaults. Update the
four light-profile heights when changing the low/high layer bounds. The
fixture's observer height must match the preview camera. The scripts also
have explicit Meson run targets, `render_cloud_atmosphere` and
`render_cloud_preview`, for their default diagnostic inputs.

`--air` uses the exported optical tables in the same finite-distance air/cloud
segment integrator as production. Without it the tool renders cloud-only
transport over the full sky, which remains useful for isolating density and
lighting. The contact sheet and manifest identify the selected transport.

Keep camera, sun, cloud parameters, view size and display exposure identical
for a revision comparison. Inspect several world positions and views toward,
across and away from the sun, including the zenith and horizon. Repeat with a
low sun. Inspect the opacity panels separately from radiance to distinguish
distribution problems from lighting problems. Raw linear HDR values and
manifests accompany the PNGs; the default PNG display uses fixed exposure and
sRGB, without the game's tonemapper or automatic exposure.

For a readable display of bright forward-scattering clouds, add
`--tone-map aces`. This executes the repository's `ACESFitted` curve at the same fixed
exposure and retains a `*-linear.png` clipped diagnostic. It does not run local
exposure fusion, automatic exposure or color grading. Redisplay existing raw
results with `--output <capture-directory> --redisplay --tone-map aces`; no cloud
transport is recomputed, raw source provenance remains intact, and the manifest
records the display history and curve source hash. Apply one display mode and
exposure to an entire comparison group, including its baseline.

Compare whole views with attributed natural photographs: clear openings,
cluster sizes and near-to-far distribution matter as much as individual cloud
edges. Photos with different exposure, white balance or camera processing are
shape and relative-lighting references, not absolute radiance calibration.
Keep rejected views in the review record. Finite values, shader compilation
and coverage statistics are correctness checks, not visual acceptance.

This preview contains production cloud transport and the production sky as
background and ambient input. It does not contain terrain, the scene fog
cache, celestial disks, temporal reconstruction or the full presentation
pipeline. The constant environment used without `--atmosphere-fixture` is a
diagnostic input and is unsuitable for judging daylight cloud brightness.
Use an in-game capture to assess those remaining interactions and performance.

## GPU analysis

On the host, `KavoraSceneFrame.renderAndSubmitFrame` orders captured lights,
terrain, entities and environment updates, then hands the prepared scene to
`KavoraFramePresentation`. The presentation owner pairs Submit and Present.
`kavora/src/main/effects/scene-stages.txt` declares when scene effects run and
which captured values their handlers consume. Gradle generates the ordered
Java calls. Capture hooks run at their vanilla call sites, and frame cleanup
runs even when submission is interrupted.

Choose the pass that owns the effect before tracing the host call chain.
`RtxFramePipeline::record` in `rtx_frame_pipeline.inl` orders scene lighting,
reconstruction, display effects and export. Lighting in `rtx_frame_lighting.inl`
produces HDR composite color and reconstruction guides. Reconstruction in
`rtx_frame_reconstruction.inl` writes display-resolution linear HDR into
`m_finalOutput`. Display effects in `rtx_frame_post_processing.inl` use it in
place, with motion blur before tonemapping and lens effects after it.
The frame stages compile with their caller in `rtx_context.cpp` so the
compiler can inline them. Pass implementations own their bindings and image
access modes.

Pass implementations declare their borrowed frame resources in their headers.
`FrameResourceView` limits access to those members at compile time. Passes
resolve aliased resources at their point of use, in command order. The
resource manager owns allocation and history rotation, and the frame
pipeline hands each pass its inputs.

`rtx_frame_schedule.h` expands ordered stage declarations and reconstruction
alternatives into direct calls. The lighting schedules assert the order of
G-buffer production, direct and indirect integration, radiance-cache resolve,
denoising and composition. Reconstruction schedules assert exposure preparation
before its consumers and the history update before capture. A pass can use
`BorrowedPass` to construct its typed resource view and resolves aliases at
the point where it records access.

For an effect change, start at its Slang calculation owner and the native pass
that supplies its resources. Java's sky and cloud owners share one camera-local
environment snapshot. They publish scene inputs through the existing Remix API.
Keep the input encoding, output extent, image access and history lifetime at
that boundary. If the change needs new per-frame shader parameters, follow
the shared [shader buffer contract](../kavora-runtime/src/dxvk/shaders/rtx/README.md#ray-tracing-constant-buffer).
See the [effect entry points](../kavora-runtime/src/dxvk/shaders/rtx/README.md#visual-effect-boundaries).

Rain-wet terrain follows this boundary. The scene schedule registers the
exposure snapshot before Submit and acknowledges it after Submit succeeds.
Java sends world-column heights only when they change. The G-buffer owns the
exposure buffer binding and adapts the existing rain ring texture to the
opaque material stage. The Slang effect reads those inputs and modifies
albedo, roughness and the shading normal before BSDF construction.

Water already uses this boundary. Java submits a `WaterSimulationFrame`
through the public FFM contract, and the native simulation produces the
shared `WaterSurfaceArgs` block. The shader layout check verifies the block
inside `RaytraceArgs` independently of the Java-to-native layout probe.

For the cloud-sky map, the dispatch and bindings live in `dispatchCloudSky`.
The density and lighting used to fill the map live on the shader side.
[Native cloud pass](../kavora-runtime/src/dxvk/rtx_render/rtx_global_volumetrics.cpp) ·
[Cloud-sky shader](../kavora-runtime/src/dxvk/shaders/rtx/pass/clouds/generate_cloud_sky.comp.slang)

For final color grading, start at the shader that consumes the tonemapped
image and writes the exported color.
[Final color shader](../kavora-runtime/src/dxvk/shaders/rtx/pass/srgb_dither/srgb_dither.comp.slang)

For a frozen frame, follow `KavoraFramePresentation` from Submit through image
acquire and release to Present. Submit publishes the producer timeline signal
from `D3D9SwapchainExternal::Present`, including when scene rendering is skipped.
Present completes that handoff after the host encoder submits its release.
When a caller renders through `GameRenderer.render()` directly, the handoff
finishes before it returns, with no window image. Window source-image lifetime
belongs to `NativeVulkanSurface`. Particle worker
lifetime and stale-world payloads belong to `ParticleFramePipeline`.
The renderer marks phase boundaries. `KavoraFrameMetrics` owns the metric IDs,
presentation deltas and reporting for those phases.

Use a Release runtime. `build-runtime.ps1 -Profiling` enables on-demand Tracy;
use Nsight Graphics for pass execution, shader variants, register/local-memory
pressure, synchronization and residency. Include warm-up and resource upload
state when comparing captures.

Compare equal visual settings and camera poses. Whole-frame budgets matter;
pass times can overlap or include children. Native-resolution performance,
DLSS, frame generation and quality-tier tradeoffs are separate measurements.
See [profiling tools](../kavora/tools/docs/PROFILING.md).

Intermediate image/readback probes are opt-in. Do not keep unconditional
readbacks, extra synchronization or persistent CPU texture copies in normal
rendering. Remove one-off captures after retaining the results needed for a fix.
