# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Numerical readback checks for production cloud geometry, density and transport.

Install numpy and slangpy. The Vulkan device may use a software ICD. These
checks do not measure game performance or validate presentation.
"""
import argparse
from pathlib import Path

import numpy as np
import slangpy as spy


HERE = Path(__file__).resolve().parent
SHADERS = HERE.parents[2] / "src/dxvk/shaders"
OPTIONS = {"include_paths": [str(HERE), str(SHADERS)], "defines": {"__SLANG__": "1"}}


def cloud_parameters(**changes):
    # These are fixed numerical fixtures, including the 400 m shell used by the
    # geometry probes below. The visual preview passes current native defaults.
    result = {
        "up": [0, 1, 0], "enable": 1, "windOffset": [0, 0, 0],
        "baseHeight": 400.0, "thickness": 1500.0, "shapeScale": 1024.0,
        "extinction": 0.06, "coverage": 0.45, "maxDistance": 12000.0,
        "albedo": 1.0, "steps": 160, "lightSteps": 16,
        "anisotropy": 0.65, "multipleScattering": 0.8, "weather": 0.0,
        "thunder": 0.0, "groundReference": [0, 0, 0], "planetRadius": 6360000.0,
        "transportMode": 0, "skyResolution": 512, "night": 0.0,
        "lightMaxDistance": 60000.0, "previousWindDelta": [0, 0, 0],
        "viewAngularFootprint": 0.0, "highBaseHeight": 6000.0,
        "highThickness": 900.0, "highExtinction": 0.0, "highCoverage": 0.4,
        "highMaxDistance": 60000.0, "groundAlbedo": 0.18,
    }
    result.update(changes)
    return result


class Probe:
    def __init__(self, device):
        self.device = device
        self.kernels = {}

    def run(self, entry, inputs, directions=None, clouds=None, textures=None):
        data = np.asarray(inputs, dtype=np.float32).reshape(-1, 4)
        if entry not in self.kernels:
            program = self.device.load_program("cloud_transport_contracts.comp.slang", [entry])
            self.kernels[entry] = self.device.create_compute_kernel(program)
        output = self.device.create_buffer(element_count=len(data), struct_size=16,
                                           usage=spy.BufferUsage.unordered_access)
        bindings = {
            "Inputs": self.device.create_buffer(data=data, usage=spy.BufferUsage.shader_resource),
            "Results": output, "Count": len(data),
        }
        if directions is not None:
            bindings["Directions"] = self.device.create_buffer(
                data=np.asarray(directions, dtype=np.float32), usage=spy.BufferUsage.shader_resource)
        if clouds is not None:
            bindings["Clouds"] = clouds
        if textures is not None:
            bindings.update({key: value.descriptor_handle_combined for key, value in textures.items()})
        self.kernels[entry].dispatch(thread_count=[len(data), 1, 1], vars=bindings)
        return output.to_numpy().view(np.float32).reshape(-1, 4)


def check_homogeneous(probe):
    samples = np.array([(sigma, 100.0, 0.93, steps)
                        for sigma in (0.0, 1e-4, 0.01, 0.2)
                        for steps in (1, 7, 64, 256)], dtype=np.float32)
    actual = probe.run("homogeneous", samples)
    transmission = np.exp(-samples[:, 0].astype(np.float64) * samples[:, 1])
    expected = np.column_stack([(1 - transmission)[:, None] * samples[:, 2, None] * [1, 2, 4],
                                transmission])
    np.testing.assert_allclose(actual, expected, atol=3e-5, rtol=5e-4)
    print("PASS homogeneous Beer integration: 16 density/subdivision cases")


def check_noise_gradient(probe):
    axis = np.linspace(-0.75, 1.75, 16, endpoint=False)
    points = [(x, y, period, 1e-3) for period in (2, 4) for x in axis for y in axis]
    result = probe.run("noiseGradient", points)
    assert np.isfinite(result).all()
    # A 1e-3 UV difference balances float32 cancellation against truncation error.
    np.testing.assert_allclose(result[:, :2], result[:, 2:], atol=1.5e-3, rtol=5e-4,
                               err_msg="curl-flow potential gradient differs from the noise derivative")
    print(f"PASS periodic noise gradient: 512 finite differences, "
          f"maximum error {np.max(np.abs(result[:, :2] - result[:, 2:])):.7f}")


def shell_interval(clouds, origin, direction, limit):
    radius = clouds["planetRadius"]
    point = np.asarray(origin, np.float64) + [0, radius, 0]
    direction = np.asarray(direction, np.float64)

    def roots(altitude):
        b = point @ direction
        c = point @ point - (radius + altitude) ** 2
        disc = b * b - c
        return (-1, -1) if disc < 0 else (-b - np.sqrt(disc), -b + np.sqrt(disc))

    outer = roots(clouds["baseHeight"] + clouds["thickness"])
    begin, end = max(0, outer[0]), min(limit, clouds["maxDistance"], outer[1])
    inner = roots(clouds["baseHeight"])
    if inner[1] > begin:
        if inner[0] <= begin:
            begin = inner[1]
        else:
            end = min(end, inner[0])
    return [begin, end] if end > begin else [0, 0]


def check_intervals(probe):
    clouds = cloud_parameters(maxDistance=60000.0)
    origins, directions, expected = [], [], []
    for height in (-50, 0, 399, 400, 401, 900, 1899, 1900, 1901, 3000):
        for angle in (-90, -10, -1, -0.01, 0, 0.01, 1, 10, 90):
            radians = np.radians(angle)
            origin = [250, height, -170]
            direction = [np.cos(radians), np.sin(radians), 0]
            origins.append([*origin, 60000])
            directions.append([*direction, 0])
            expected.append(shell_interval(clouds, origin, direction, 60000))
    actual = probe.run("intervals", origins, directions, clouds)[:, :2]
    np.testing.assert_allclose(actual, expected, atol=0.3, rtol=4e-5)
    assert np.isfinite(actual).all() and np.all(actual[:, 1] >= actual[:, 0])
    print("PASS cloud-shell intersections: 90 above/inside/below and grazing rays")


def check_layer_intervals(probe):
    clouds = cloud_parameters(highExtinction=0.01)
    origins, directions, expected = [], [], []
    for layer, base, thickness in ((0, clouds["baseHeight"], clouds["thickness"]),
                                   (1, clouds["highBaseHeight"], clouds["highThickness"])):
        for height in (0, base + 0.5 * thickness, 10000):
            for angle in (-10, -3, -1, 0, 1, 10):
                ray = np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle)), 0])
                origin = np.array([0, height, 0])
                center_relative = origin + [0, clouds["planetRadius"], 0]
                b = center_relative @ ray
                roots = []
                for altitude in (base, base + thickness):
                    c = center_relative @ center_relative - (clouds["planetRadius"] + altitude) ** 2
                    d = b * b - c
                    if d >= 0:
                        roots.extend([-b - np.sqrt(d), -b + np.sqrt(d)])
                endpoints = sorted(set([0.0, 1e6, *[t for t in roots if 0 < t < 1e6]]))
                spans = []
                for begin, end in zip(endpoints[:-1], endpoints[1:]):
                    radius = np.linalg.norm(center_relative + ray * (begin + end) * 0.5)
                    if clouds["planetRadius"] + base < radius < clouds["planetRadius"] + base + thickness:
                        spans.extend([begin, end])
                expected.append(spans + [0.0] * (4 - len(spans)))
                origins.append([*origin, 1e6])
                directions.append([*ray, layer])
    actual = probe.run("layerIntervals", origins, directions, clouds)
    np.testing.assert_allclose(actual, expected, atol=1.0, rtol=2e-5)
    assert np.count_nonzero(actual[:, 3]) > 0, "grazing rays must cover both shell crossings"
    disabled = probe.run("layerIntervals", origins, directions, cloud_parameters(enable=0))
    np.testing.assert_array_equal(disabled, 0)
    print("PASS layered shells: both crossings, high layer and disabled transport")


def check_light_profiles(probe):
    profile = np.array([[0, 0, 0, 0], [0.12, 0.02, 0.005, 400],
                        [0.8, 0.2, 0.05, 1900], [1.0, 0.7, 0.4, 6500]])
    heights = np.array([-100, 0, 100, 400, 700, 1900, 3000, 6500, 8000])
    inputs = np.column_stack([heights, np.zeros((len(heights), 3))])
    light = {"directionToLight": [1, 0, 0], "irradiance": [0.04, 0.06, 0.09],
             "hasRadianceProfile": 1, "radianceProfile": profile.tolist()}
    actual = probe.run("lightProfiles", inputs, clouds=cloud_parameters(lights=[light, light]))[:, :3]
    expected = np.column_stack([np.interp(heights, profile[:, 3], profile[:, channel]) for channel in range(3)])
    np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=0)
    light["hasRadianceProfile"] = 0
    fallback = probe.run("lightProfiles", inputs, clouds=cloud_parameters(lights=[light, light]))[:, :3]
    np.testing.assert_allclose(fallback, np.tile(light["irradiance"], (len(heights), 1)), atol=2e-6, rtol=0)
    print("PASS altitude irradiance: profile boundaries, ground darkness and legacy fallback")


def production_kernel(device, relative, defines=None, combined_source=False):
    session = device.create_slang_session({**OPTIONS, "defines": {"__SLANG__": "1", **(defines or {})}})
    source = (SHADERS / relative).read_text(encoding="utf-8")
    # ShaderCursor writes a constant buffer. SPIR-V compilation checks the production push layout separately.
    source = source.replace("layout(push_constant)", "")
    if combined_source:
        # SlangPy binds combined samplers through descriptor handles.
        source = source.replace("Sampler3D<float4> Source;", "Sampler3D<float4>.Handle Source;")
        source = source.replace("Sampler2D<float4> Source;", "Sampler2D<float4>.Handle Source;")
    module = session.load_module_from_source(Path(relative).stem.replace(".", "_"), source)
    return device.create_compute_kernel(session.link_program([module], [module.entry_point("main")]))


def cloud_textures(device):
    usage = spy.TextureUsage.shader_resource | spy.TextureUsage.unordered_access
    sampler = device.create_sampler(address_u=spy.TextureAddressingMode.wrap,
                                    address_v=spy.TextureAddressingMode.wrap,
                                    address_w=spy.TextureAddressingMode.wrap)
    textures = {}
    noise = {name: production_kernel(device, "rtx/pass/clouds/generate_cloud_noise.comp.slang", defines)
             for name, defines in (("Base", {"CLOUD_NOISE_BASE": "1"}), ("Detail", {}))}
    weather = production_kernel(device, "rtx/pass/clouds/generate_cloud_weather.comp.slang")
    filters = {name: production_kernel(device, "rtx/pass/clouds/filter_cloud_noise.comp.slang", defines, True)
               for name, defines in (("Base", {"CLOUD_NOISE_VOLUME": "1", "CLOUD_NOISE_FLOAT": "1"}),
                                     ("Detail", {"CLOUD_NOISE_VOLUME": "1"}), ("Weather", {}))}
    # The preview tool can replay an earlier shader root with its original storage format.
    base_source = (SHADERS / "rtx/pass/clouds/generate_cloud_noise.comp.slang").read_text(encoding="utf-8")
    base_format = spy.Format.rg16_float if "layout(rg16f," in base_source else spy.Format.rgba16_float
    for name, size, dimensions in (("Base", 128, 3), ("Detail", 32, 3), ("Weather", 512, 2)):
        floating = name != "Detail"
        image_format = base_format if name == "Base" else (spy.Format.rgba16_float if floating else spy.Format.rgba8_unorm)
        texture = device.create_texture(type=spy.TextureType.texture_3d if dimensions == 3 else spy.TextureType.texture_2d,
                                       format=image_format,
                                       width=size, height=size,
                                       depth=size if dimensions == 3 else 1,
                                       mip_count=int(np.log2(size)) + 1, usage=usage)
        view = texture.create_view(mip=0, mip_count=1)
        if dimensions == 3:
            noise[name].dispatch(thread_count=[size, size, size], vars={"CloudNoise": view, "cb": {"detail": name == "Detail"}})
        else:
            weather.dispatch(thread_count=[size, size, 1], vars={"CloudWeather": view})
        data = texture.to_numpy()
        assert np.ptp(data[..., 0]) > (0.12 if floating else 32), (name, "degenerate generated noise")
        if floating:
            # The mean and its square are independently quantized to half precision.
            mean_channels = list(range(0, data.shape[-1], 2)) if name == "Base" else [0]
            moment_channels = [channel + 1 for channel in mean_channels]
            np.testing.assert_allclose(data[..., moment_channels], data[..., mean_channels].astype(np.float32) ** 2,
                                       atol=np.finfo(np.float16).eps, rtol=0, err_msg="unfiltered shape moments")
        # Compare the production filter with independent reference box averages at every level.
        for mip in range(1, texture.mip_count):
            shape = []
            for extent in data.shape[:-1]:
                shape.extend([extent // 2, 2])
            expected = data.reshape(*shape, data.shape[-1]).astype(np.float32).mean(
                axis=tuple(range(1, 2 * dimensions, 2)))
            expected = expected.astype(np.float16) if floating else np.rint(expected).astype(np.uint8)
            source = texture.create_view(mip=mip - 1, mip_count=1, sampler=sampler)
            destination = texture.create_view(mip=mip, mip_count=1)
            extent = size >> mip
            filters[name].dispatch(thread_count=[extent, extent, extent if dimensions == 3 else 1],
                                   vars={"Source": source.descriptor_handle_combined, "Destination": destination})
            data = texture.to_numpy(mip=mip)
            # UNORM interpolation may round each axis before the final texture write.
            np.testing.assert_allclose(data, expected, atol=8e-4 if floating else 2,
                                       rtol=0, err_msg=f"{name} mip {mip}")
        textures[name] = texture.create_view(sampler=sampler)
    print("PASS production noise and mip filters: 2D and 3D reference averages")
    return textures


def check_density(probe, textures, dump):
    axis = np.linspace(-4096, 4096, 128, endpoint=False, dtype=np.float32)
    x, z = np.meshgrid(axis, axis)
    points = np.column_stack([x.ravel(), np.full(x.size, 520), z.ravel(), np.zeros(x.size)])
    fields = []
    for weather in (0.0, 0.5, 1.0):
        field = probe.run("densities", points, clouds=cloud_parameters(weather=weather), textures=textures)[:, 0]
        assert np.isfinite(field).all() and np.all((0 <= field) & (field <= 1))
        fields.append(field)
    assert np.mean(fields[0]) > 0.001, "fair-weather density has collapsed"
    assert np.mean(fields[2]) > np.mean(fields[0]), "rain should build a denser layer"
    filtered_points = points.copy()
    filtered_points[:, 3] = 128
    filtered = probe.run("densities", filtered_points, clouds=cloud_parameters(), textures=textures)[:, 0]
    assert np.isfinite(filtered).all() and np.all((0 <= filtered) & (filtered <= 1))
    assert np.std(filtered) < np.std(fields[0]), "a larger footprint should suppress unresolved variation"
    if dump:
        dump.mkdir(parents=True, exist_ok=True)
        np.savez(dump / "cloud-density.npz", axis=axis, clear=fields[0].reshape(x.shape),
                 rain=fields[2].reshape(x.shape), filtered=filtered.reshape(x.shape))
    print(f"PASS production density: clear/rain means {np.mean(fields[0]):.5f}/{np.mean(fields[2]):.5f}")


def check_visibility(probe, textures, dump):
    positions = [[x, 540, z] for x in (-1200, -400, 400, 1200) for z in (-700, 0, 700)]
    angles = (0.0, 0.001, 1.0, 1.001, 3.0, 3.001, 10.0, 10.001, 45.0, 45.001, 90.0)
    origins, directions = [], []
    for position in positions:
        for angle in angles:
            radians = np.radians(angle)
            origins.append([*position, 60000])
            directions.append([np.cos(radians), np.sin(radians), 0, 0])
    actual = probe.run("visibility", origins, directions, cloud_parameters(), textures)[:, 0]
    reference = probe.run("visibility", origins, directions, cloud_parameters(lightSteps=512), textures)[:, 0]
    assert np.isfinite(actual).all() and np.all((0 <= actual) & (actual <= 1))
    values = actual.reshape(len(positions), len(angles))
    differences = np.abs(values[:, 0:10:2] - values[:, 1:10:2])
    assert np.max(differences) < 0.025, ("low-sun temporal discontinuity", np.max(differences))
    mean_error = np.mean(np.abs(actual - reference))
    maximum_error = np.max(np.abs(actual - reference))
    if dump:
        np.savez(dump / "cloud-visibility.npz", actual=values,
                 reference=reference.reshape(values.shape), angles=angles,
                 origins=np.asarray(origins), directions=np.asarray(directions))
    # Footprint filtering changes individual rays; bound both aggregate bias and missed thin cells.
    assert mean_error < 0.05, ("self-shadow quadrature diverges from the fine reference", mean_error)
    assert maximum_error < 0.45, ("self-shadow quadrature misses a significant cloud cell", maximum_error)
    print(f"PASS cloud visibility: mean/max reference error {mean_error:.5f}/{maximum_error:.5f}, "
          f"angular delta {np.max(differences):.6f}")


def check_high_density(probe, textures, dump):
    axis = np.linspace(-8192, 8192, 128, endpoint=False, dtype=np.float32)
    x, z = np.meshgrid(axis, axis)
    clouds = cloud_parameters(extinction=0.0, highExtinction=0.01)
    points = np.column_stack([x.ravel(), np.full(x.size, 6250), z.ravel(), np.zeros(x.size)])
    actual = probe.run("densities", points, clouds=clouds, textures=textures)[:, 0]
    assert np.isfinite(actual).all() and np.all((0 <= actual) & (actual <= 1))
    assert 0.001 < np.mean(actual) < 0.9, "the high layer must retain variable thin coverage"

    previous = np.zeros_like(actual)
    for coverage in (0.0, 0.1, 0.35, 0.7, 1.0):
        density = probe.run("densities", points, clouds=clouds | {"highCoverage": coverage},
                            textures=textures)[:, 0]
        assert np.isfinite(density).all() and np.all((0 <= density) & (density <= 1))
        if coverage == 0:
            np.testing.assert_array_equal(density, 0)
        assert np.all(density >= previous - 1e-6), "increasing high coverage must not remove condensate"
        previous = density

    # The host wraps wind after sixteen shape periods. All high-layer sampling
    # must have that same period, including its regional envelope and distortion.
    period = 16 * clouds["shapeScale"]
    for wind in ([period, 0, 0], [0, 0, period], [-period, 0, period]):
        wrapped = probe.run("densities", points, clouds=clouds | {"windOffset": wind},
                            textures=textures)[:, 0]
        np.testing.assert_allclose(wrapped, actual, atol=1e-5, rtol=1e-4,
                                   err_msg="high clouds jump when the host wraps wind")

    for height in (5800, 7100):
        points[:, 1] = height
        outside = probe.run("densities", points, clouds=clouds, textures=textures)[:, 0]
        np.testing.assert_array_equal(outside, 0)
    if dump:
        np.savez(dump / "cloud-high-density.npz", axis=axis, density=actual.reshape(x.shape))
    print(f"PASS high-layer density: bounds, coverage monotonicity, wind wrap, mean {np.mean(actual):.5f}")


def check_high_column_transmission(probe, textures):
    positions = [(x, z) for x in (-6144.0, -2048.0, 2048.0, 6144.0)
                 for z in (-6144.0, -2048.0, 2048.0, 6144.0)]
    positions.append((8183.0, 1171.0))
    center_height = 6400.0
    actual, expected = [], []
    for thickness in (100.0, 200.0, 800.0):
        clouds = cloud_parameters(extinction=0.0, highBaseHeight=center_height - 0.5 * thickness,
                                  highThickness=thickness, highExtinction=1.2 / thickness,
                                  highCoverage=0.35, highMaxDistance=96000.0)
        distance = center_height + 0.5 * thickness + 100.0
        for x, z in positions:
            # Put the planet tangent beneath this column so radial altitude equals world Y.
            column = clouds | {"groundReference": [x, 0.0, z]}
            result = probe.run("viewTransmission", [[x, 0.0, z, distance]], [[0.0, 1.0, 0.0, 0.0]],
                               column, textures)[0]
            # A vertical ray has no horizontal span in the two-dimensional high
            # field. Layer thickness must not select a coarser horizontal mip.
            density = probe.run("densities", [[x, center_height, z, 0.0]],
                                clouds=column, textures=textures)[0, 0]
            # Smooth ramps over [0, .15] and [.65, 1] enclose area .75; the midpoint
            # lies on the unit plateau. This is an independent Beer-law column reference.
            optical_depth = float(density) * 0.75 * thickness * clouds["highExtinction"]
            actual.append(result[0])
            expected.append(np.exp(-optical_depth))
    actual = np.asarray(actual)
    expected = np.asarray(expected)
    assert np.isfinite(actual).all() and np.all((0 <= actual) & (actual <= 1))
    assert np.any(expected < 1.0 - 1e-5), "column integration must exercise nonzero cloud density"
    np.testing.assert_allclose(actual, expected, atol=2e-6, rtol=2e-5,
                               err_msg="changing high-layer thickness must preserve its optical column")
    print(f"PASS high-layer view columns: 51 columns at 100/200/800m, "
          f"maximum Beer-law error {np.max(np.abs(actual - expected)):.7f}")


def check_tangent_visibility(probe, textures):
    maximum_change = 0.0
    offsets = np.radians([-0.001, -0.0001, 0.0, 0.0001, 0.001])
    # Reduced extinction keeps the tangent rays measurable instead of completely opaque.
    for layer, base, height, extinction in ((0, 400.0, 540.0, 3e-4), (1, 6000.0, 6400.0, 2e-5)):
        clouds = cloud_parameters(extinction=extinction if layer == 0 else 0.0,
                                  highExtinction=extinction if layer == 1 else 0.0)
        origins, directions = [], []
        for x in (-1200.0, 0.0, 1200.0):
            for z in (-700.0, 700.0):
                radial_y = clouds["planetRadius"] + height
                radial_xy = np.hypot(x, radial_y)
                c = x * x + z * z + radial_y * radial_y - (clouds["planetRadius"] + base) ** 2
                tangent = np.arcsin(-np.sqrt(c) / radial_xy) - np.arctan2(x, radial_y)
                for angle in tangent + offsets:
                    origins.append([x, height, z, 400000.0])
                    directions.append([np.cos(angle), np.sin(angle), 0.0, 0.0])
        values = probe.run("visibility", origins, directions, clouds, textures)[:, 0].reshape(-1, len(offsets))
        assert np.isfinite(values).all() and np.all((0 <= values) & (values <= 1))
        assert np.any((values > 0.01) & (values < 0.99)), "tangent continuity must exercise visible attenuation"
        change = np.max(np.abs(np.diff(values, axis=1)))
        assert change < 0.01, ("shadow grid jumps when a second shell interval appears", layer, change)
        maximum_change = max(maximum_change, change)
    print(f"PASS below-horizon shell tangencies: maximum transmission change {maximum_change:.6f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, help="Optional scratch directory for numerical diagnostics")
    args = parser.parse_args()
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options=OPTIONS)
    probe = Probe(device)
    check_homogeneous(probe)
    check_noise_gradient(probe)
    check_intervals(probe)
    check_layer_intervals(probe)
    check_light_profiles(probe)
    textures = cloud_textures(device)
    check_density(probe, textures, args.dump)
    check_high_density(probe, textures, args.dump)
    check_high_column_transmission(probe, textures)
    check_visibility(probe, textures, args.dump)
    check_tangent_visibility(probe, textures)


if __name__ == "__main__":
    main()
