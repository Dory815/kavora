# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Check density continuity where weather filtering begins using child samples."""
import argparse
import json
from pathlib import Path
import re

import numpy as np


def check_filter_transition(probe, textures, clouds, texel_width, dump=None):
    rng = np.random.default_rng(7281)
    count = 65536
    points = np.column_stack((rng.uniform(-32768, 32768, count),
                              rng.uniform(clouds["baseHeight"], clouds["baseHeight"] + clouds["thickness"], count),
                              rng.uniform(-32768, 32768, count), np.zeros(count))).astype(np.float32)
    report = []
    for level in range(5):
        edge = texel_width * (2 ** level)
        footprints = np.asarray([edge - 0.001, edge, edge + 0.001, edge + 0.002], np.float32)
        values = []
        for footprint in footprints:
            points[:, 3] = footprint
            values.append(probe.run("densities", points, clouds=clouds, textures=textures)[:, 0])
        values = np.asarray(values)
        differences = np.abs(np.diff(values, axis=0))
        worst = np.unravel_index(np.argmax(differences), differences.shape)
        maximum = float(differences[worst])
        # Keep the failing positions and outputs before asserting so a device
        # precision/filtering failure can be reproduced without a new trace.
        if dump:
            dump.mkdir(parents=True, exist_ok=True)
            np.savez(dump / f"cloud-filter-transition-{level}.npz", points=points[:, :3],
                     footprints=footprints, density=values, worstIndex=worst)
        assert np.isfinite(values).all() and np.any((values > 0.01) & (values < 0.99))
        assert maximum < 1e-3, ("weather filtering jumps across a mip transition", level,
                                maximum, points[worst[1], :3].tolist(), values[:, worst[1]].tolist())
        report.append({"level": level, "footprintMeters": edge, "positions": count,
                       "maximumAdjacentDensityDelta": maximum})
    print(f"PASS weather filter transitions: {count} positions at five mip boundaries, "
          f"maximum adjacent density delta {max(row['maximumAdjacentDensityDelta'] for row in report):.7f}")
    return report


def main():
    import slangpy as spy
    from test_cloud_transport import OPTIONS, SHADERS, Probe, cloud_parameters, cloud_textures, cloud_weather_periods

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path)
    args = parser.parse_args()
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options=OPTIONS)
    clouds = cloud_parameters()
    configuration = (SHADERS / "rtx/pass/cloud_noise.h").read_text()
    resolution = int(re.search(r"kCloudWeatherResolution\s*=\s*(\d+)", configuration)[1])
    texel_width = cloud_weather_periods()[0] * clouds["shapeScale"] / resolution
    report = check_filter_transition(Probe(device), cloud_textures(device, args.dump), clouds, texel_width, args.dump)
    if args.dump:
        args.dump.mkdir(parents=True, exist_ok=True)
        (args.dump / "cloud-filter-transition.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
