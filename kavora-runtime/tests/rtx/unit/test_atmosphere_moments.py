# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Read back production atmospheric motion moments on a Vulkan device.

Requires numpy and slangpy. Software Vulkan is sufficient; this test does not
validate game presentation or temporal reconstruction quality.
"""
from pathlib import Path

import numpy as np
import slangpy as spy


HERE = Path(__file__).resolve().parent
SHADERS = HERE.parents[2] / "src/dxvk/shaders"
MAX_DISTANCE = 96000.0


def run(device, entry, inputs):
    inputs = np.asarray(inputs, dtype=np.float32).reshape(-1, 4)
    program = device.load_program("atmosphere_moment_contracts.comp.slang", [entry])
    kernel = device.create_compute_kernel(program)
    output = device.create_buffer(element_count=len(inputs), struct_size=16,
                                  usage=spy.BufferUsage.unordered_access)
    kernel.dispatch(thread_count=[len(inputs), 1, 1], vars={
        "Inputs": device.create_buffer(data=inputs, usage=spy.BufferUsage.shader_resource),
        "Results": output, "Count": len(inputs), "MaxDistance": MAX_DISTANCE,
    })
    return output.to_numpy().view(np.float32).reshape(-1, 4)


def reference(cells):
    # Independent Gaussian quadrature in optical-depth coordinates. Beyond 40
    # optical depths the omitted probability is less than 5e-18.
    nodes, weights = np.polynomial.legendre.leggauss(64)
    expected = []
    for extinction, begin, length, _ in cells:
        tau = float(extinction) * float(length)
        if tau == 0:
            expected.append([0, 0])
            continue
        bound = min(tau, 40.0)
        depth = (nodes + 1) * bound * 0.5
        probability = weights * bound * 0.5 * np.exp(-depth)
        opacity = probability.sum()
        first = (probability * (float(begin) + depth / float(extinction))).sum()
        expected.append([first / MAX_DISTANCE, opacity])
    return np.asarray(expected)


def main():
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options={
        "include_paths": [str(HERE), str(SHADERS)], "defines": {"__SLANG__": "1"},
    })
    cells = np.asarray([(extinction, begin, length, 1)
                        for extinction in (0, 1e-10, 1e-7, 1e-4, 0.001, 0.1, 1)
                        for begin in (0, 16, 400, 7000, 80000, 160000, 30000000)
                        for length in (0, 0.01, 1, 37, 4000)], dtype=np.float32)
    expected = reference(cells)
    actual = run(device, "moments", cells)
    np.testing.assert_allclose(actual[:, :2], expected, rtol=2e-5, atol=2e-7)
    assert np.isfinite(actual).all()
    assert np.all((actual[:, 1] >= 0) & (actual[:, 1] <= 1))
    print(f"PASS extinction moments: {len(cells)} cells against independent quadrature")

    visible = actual[:, 3] >= 1e-5
    mean = np.divide(actual[visible, 0], actual[visible, 1])
    compressed = np.divide(actual[visible, 2], actual[visible, 3])
    # Half precision has a relative error below 0.05% for normal means; the
    # absolute allowance covers the subnormal range near the camera.
    np.testing.assert_allclose(compressed, mean, rtol=5e-4, atol=3e-8)
    np.testing.assert_array_equal(actual[actual[:, 1] == 0, 2:], 0)
    print("PASS packed motion guides: thin edges, finite neutral values and half precision")

    split = np.repeat(cells, 4, axis=0)
    split[:, 3] = np.tile([1, 2, 7, 31], len(cells))
    composed = run(device, "composition", split)
    np.testing.assert_allclose(composed[:, :2], np.repeat(expected, 4, axis=0), rtol=3e-5, atol=4e-7)
    np.testing.assert_array_equal(composed[:, 2], 0)
    print(f"PASS prefix/tail composition: {len(split)} subdivisions including zero-length cells")

    grids = np.asarray([(begin, spacing, cone, split)
                        for begin in (0, 139, 800, 6300, 12000, 91700, MAX_DISTANCE)
                        for spacing in (8, 25, 51.2)
                        for cone in (0, 0.0005, 0.0038, 0.012)
                        for split in (0, 0.031, 0.5, 0.999, 1)], dtype=np.float32)
    values = run(device, "rayGrid", grids)
    begin = grids[:, 0].astype(np.float64)
    expected_depth = 1e-6 * (MAX_DISTANCE - begin + (MAX_DISTANCE**2 - begin**2) / 20000)
    np.testing.assert_allclose(values[:, 0], expected_depth, rtol=3e-5, atol=1e-7)
    np.testing.assert_allclose(values[:, 1], values[:, 0], rtol=3e-5, atol=1e-7)
    np.testing.assert_array_equal(values[:, 2], 0)
    assert np.isfinite(values).all()
    assert np.all(values[:, 3] <= np.ceil((MAX_DISTANCE - begin) / grids[:, 1]) + 1)
    print(f"PASS adaptive cloud ray grid: {len(grids)} full/prefix/tail integrations through 96 km")


if __name__ == "__main__":
    main()
