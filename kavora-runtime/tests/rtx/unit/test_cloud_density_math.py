# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Compare production threshold moments with an independent double-precision integral."""
import argparse
import json
from pathlib import Path

import numpy as np
import slangpy as spy


def moment_cases():
    cases = []
    for width in np.geomspace(1e-5, 2.0, 24):
        for threshold in (0.0, 0.4, 0.8):
            for ramp in (0.08, 0.12, 1.0):
                for position in (-1.0, -0.1, 0.0, 0.1, 0.25, 0.5, 0.9, 1.0, 1.1, 2.0):
                    mean = np.float32(threshold + ramp * position)
                    second = np.float32(mean * mean + width * width / 3.0)
                    cases.append((mean, second, threshold, ramp))
    return np.asarray(cases, np.float32)


def moment_reference(samples):
    # Match the representable input variance and documented zero-width cutoff.
    shape = samples[:, 0]
    variance = np.maximum(samples[:, 1] - shape * shape, 0).astype(np.float64)
    width = np.sqrt(3.0 * variance)
    value = (shape - samples[:, 2]).astype(np.float64)
    ramp = np.maximum(samples[:, 3], 1e-4).astype(np.float64)
    result = np.empty((len(samples), 2), np.float64)
    for index, (v, w, r) in enumerate(zip(value, width, ramp)):
        if w <= 1e-4:
            density = np.clip(v / r, 0, 1)
            result[index] = density, density * density
            continue
        begin, end = max(v - w, 0.0), min(v + w, r)
        plateau = max(0.0, v + w - max(v - w, r))
        linear = (end ** 2 - begin ** 2) / (2.0 * r) if end > begin else 0.0
        squared = (end ** 3 - begin ** 3) / (3.0 * r * r) if end > begin else 0.0
        result[index] = (linear + plateau) / (2.0 * w), (squared + plateau) / (2.0 * w)
    return result


def check_moments(run):
    samples = moment_cases()
    actual = run(samples)
    expected = moment_reference(samples)
    assert actual.shape == expected.shape and np.isfinite(actual).all()
    assert np.all((actual >= 0) & (actual <= 1))
    np.testing.assert_allclose(actual, expected, atol=3e-5, rtol=3e-5,
                               err_msg="clipped-ramp moments lose precision for narrow distributions")
    assert np.all(actual[:, 1] >= actual[:, 0] ** 2 - 3e-5)
    assert np.all(actual[:, 1] <= actual[:, 0] + 3e-5)
    report = {"cases": len(samples), "maximumAbsoluteError": float(np.max(np.abs(actual - expected)))}
    print(f"PASS threshold moments: {report['cases']} narrow/wide/clipped cases, "
          f"maximum error {report['maximumAbsoluteError']:.8f}")
    return report


def main():
    from test_cloud_transport import OPTIONS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path)
    args = parser.parse_args()
    # The reference models individually rounded float32 operations. Other
    # density/transport tests retain the production-default compiler mode.
    options = {**OPTIONS, "floating_point_mode": spy.SlangFloatingPointMode.precise}
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options=options)
    kernel = device.create_compute_kernel(device.load_program("cloud_density_moments.comp.slang", ["main"]))

    def run(samples):
        output = device.create_buffer(element_count=len(samples), struct_size=8,
                                      usage=spy.BufferUsage.unordered_access)
        kernel.dispatch(thread_count=[len(samples), 1, 1], vars={
            "Inputs": device.create_buffer(data=samples, usage=spy.BufferUsage.shader_resource),
            "Results": output, "Count": len(samples)})
        return output.to_numpy().view(np.float32).reshape(-1, 2)

    report = check_moments(run)
    if args.dump:
        args.dump.mkdir(parents=True, exist_ok=True)
        (args.dump / "cloud-density-moments.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
