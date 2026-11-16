# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Check density continuity where weather filtering begins using child samples."""
import argparse
import json
from pathlib import Path
import re

import numpy as np
import slangpy as spy


def check_filter_transition(probe, textures, clouds, texel_width):
    rng = np.random.default_rng(7281)
    count = 65536
    points = np.column_stack((rng.uniform(-32768, 32768, count),
                              rng.uniform(clouds["baseHeight"], clouds["baseHeight"] + clouds["thickness"], count),
                              rng.uniform(-32768, 32768, count), np.zeros(count))).astype(np.float32)
    values = []
    for footprint in (texel_width - 0.001, texel_width, texel_width + 0.001, texel_width + 0.002):
        points[:, 3] = footprint
        values.append(probe.run("densities", points, clouds=clouds, textures=textures)[:, 0])
    values = np.asarray(values)
    assert np.isfinite(values).all() and np.any((values > 0.01) & (values < 0.99))
    maximum = float(np.max(np.abs(np.diff(values, axis=0))))
    assert maximum < 1e-3, ("weather filtering jumps at its first mip transition", maximum)
    print(f"PASS weather filter transition: {count} positions, maximum adjacent density delta {maximum:.7f}")
    return maximum


def main():
    from test_cloud_transport import OPTIONS, SHADERS, Probe, cloud_parameters, cloud_textures, cloud_weather_periods

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path)
    args = parser.parse_args()
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options=OPTIONS)
    clouds = cloud_parameters()
    configuration = (SHADERS / "rtx/pass/cloud_noise.h").read_text()
    resolution = int(re.search(r"kCloudWeatherResolution\s*=\s*(\d+)", configuration)[1])
    texel_width = cloud_weather_periods()[0] * clouds["shapeScale"] / resolution
    delta = check_filter_transition(Probe(device), cloud_textures(device, args.dump), clouds, texel_width)
    if args.dump:
        args.dump.mkdir(parents=True, exist_ok=True)
        (args.dump / "cloud-filter-transition.json").write_text(json.dumps({
            "positions": 65536, "maximumAdjacentDensityDelta": delta, "weatherTexelMeters": texel_width}, indent=2))


if __name__ == "__main__":
    main()
