# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Read back optical-depth prefix precision and bounded view-ray grids.

Synthetic linear prefix fields isolate coordinate, interpolation and subtraction
errors. Actual cloud-field comparisons remain in test_cloud_transport.py.
Neither test measures gameplay frame times or establishes visual acceptance.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import slangpy as spy

from test_cloud_transport import SHADERS, cloud_parameters

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', type=Path)
    options = parser.parse_args()
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options={
        'include_paths': [str(HERE), str(SHADERS)], 'defines': {'__SLANG__': '1'}})
    sampler = device.create_sampler(min_filter=spy.TextureFilteringMode.linear,
        mag_filter=spy.TextureFilteringMode.linear, mip_filter=spy.TextureFilteringMode.point,
        address_u=spy.TextureAddressingMode.clamp_to_edge,
        address_v=spy.TextureAddressingMode.clamp_to_edge,
        address_w=spy.TextureAddressingMode.clamp_to_edge)
    N = 256
    SIGMA = 0.03
    def texture(data, fmt):
        tex = device.create_texture(type=spy.TextureType.texture_3d, format=fmt,
            width=data.shape[2], height=data.shape[1], depth=data.shape[0],
            usage=spy.TextureUsage.shader_resource)
        tex.copy_from_numpy(data)
        return tex.create_view(sampler=sampler)
    programs = {}
    def run(name, origins, directions, args, sun=None):
        origins = np.asarray(origins, np.float32).reshape(-1, 4)
        directions = np.asarray(directions, np.float32).reshape(-1, 4)
        if name not in programs:
            programs[name] = device.create_compute_kernel(device.load_program('cloud_lighting_contracts.comp.slang', [name]))
        output = device.create_buffer(element_count=len(origins), struct_size=16,
            usage=spy.BufferUsage.unordered_access)
        bindings = {'Origins': device.create_buffer(data=origins, usage=spy.BufferUsage.shader_resource),
            'Directions': device.create_buffer(data=directions, usage=spy.BufferUsage.shader_resource),
            'Results': output, 'Count': len(origins), 'Clouds': args}
        if name in ('depths', 'energyParts'):
            bindings.update(Sun=sun.descriptor_handle_combined)
        programs[name].dispatch(thread_count=[len(origins), 1, 1], vars=bindings)
        return output.to_numpy().view(np.float32).reshape(-1, 4)

    args = cloud_parameters(baseHeight=800.0, thickness=1500.0, extinction=SIGMA,
        maxDistance=24000.0, highMaxDistance=24000.0)
    report = {'scope': 'Synthetic homogeneous R32 prefix readback and production grid mapping. Not GPU frame timing or visual acceptance.'}
    depth_reports = []
    for angle in (-1.0, 0.0, 1.0, 45.0, 90.0):
        a = np.deg2rad(angle)
        direction = np.array([0, np.sin(a), np.cos(a)])
        args['lights'] = [{'directionToLight': direction.tolist(), 'irradiance': [1, 1, 1]},
                          {'directionToLight': (-direction).tolist(), 'irradiance': [0, 0, 0]}]
        height = args['baseHeight'] + args['thickness'] + 24000**2 / args['planetRadius']
        length = 2 * 24000 * abs(direction[2]) + height * abs(direction[1]) + args['lightMaxDistance']
        values = np.broadcast_to(np.linspace(length * SIGMA, 0, N, dtype=np.float32)[:, None, None],
            (N, N // 2, N)).copy()
        sun = texture(values, spy.Format.r32_float)
        distances = np.array([0, 1, 8, 32, 256, 1024, 60000], np.float32)
        origins = [[0, 1200, 0, d] for d in distances]
        actual = run('depths', origins, [[*direction, 0]] * len(origins), args, sun)
        expected = distances * SIGMA
        assert np.all(actual[:, 1] == 1), actual
        error = np.max(np.abs(actual[:, 0] - expected))
        assert error < 0.002, (angle, error, actual[:, 0], expected)
        reverse = run('depths', [[0, 1200, 0, 1024]], [[*(-direction), 0]], args, sun)
        assert reverse[0, 1] == 1 and abs(reverse[0, 0] - 1024 * SIGMA) < 0.002
        depth_reports.append({'solarElevationDegrees': angle, 'maximumAbsoluteTauError': float(error),
                              'reverseLocalTau': float(reverse[0, 0])})
    report['prefixDepths'] = depth_reports
    grid_inputs = [[start, end, spacing, angle] for start, end in ((0, 24000), (800, 24000), (20000, 24000),
                   (800, 1000), (0, 96000)) for spacing in (1, 8, 16, 128) for angle in (0, 0.0013)]
    grids = run('grids', grid_inputs, [[160, 0, 0, 0]] * len(grid_inputs), args)
    assert np.all(grids[:, 0] <= 160) and np.all(grids[:, 0] >= 1)
    assert np.all(grids[:, 2] == 0), grids[grids[:, 2] != 0]
    np.testing.assert_allclose(grids[:, 1], np.array(grid_inputs)[:, 1], atol=0.01)
    report['gridCases'] = len(grids)
    report['maximumCloudCells'] = int(grids[:, 0].max())

    # A point in the middle of two shadow columns sees one local blocker and
    # one remote blocker. Filter transmitted energy before taking its logarithm;
    # independently filtered optical-depth parts cannot be added afterward.
    args['lights'][0]['directionToLight'] = [0, 0, 1]
    args['lights'][0]['angularRadius'] = 0.004625123
    depth_axis = np.linspace(0, 1, N, dtype=np.float32)
    field = np.empty((N, N // 2, N), np.float32)
    field[:, :, :N // 2] = np.clip((0.5 - depth_axis) * 8, 0, 2)[:, None, None]
    field[:, :, N // 2:] = np.clip((0.75 - depth_axis) * 8, 0, 2)[:, None, None]
    sun = texture(field, spy.Format.r32_float)
    length = 2 * args['maxDistance'] + args['lightMaxDistance']
    origin = [0, 1200, -args['maxDistance'] + 0.25 * length, 0.5 * length]
    parts = run('energyParts', [origin], [[0, 0, 1, 0.5]], args, sun)[0]
    assert parts[3] == 1
    assert abs(parts[2] - 2) < 0.01
    assert parts[0] + parts[1] < parts[2] - 0.5
    report['filteredEnergyParts'] = parts[:3].tolist()

    # Every direction sampled inside the finite solar disk selects the same
    # central-axis far field. Outside directions and large area lights stay on
    # the bounded fallback; stochastic NEE must not randomly change precision.
    radius = args['lights'][0]['angularRadius']
    cone_fractions = np.array([-1.05, -1, -0.5, 0, 0.5, 1, 1.05])
    samples = [[np.sin(radius * fraction), 0, np.cos(radius * fraction), 0] for fraction in cone_fractions]
    indices = run('lightIndices', samples, np.zeros((len(samples), 4)), args)[:, 0]
    np.testing.assert_array_equal(indices, [-1, 0, 0, 0, 0, 0, -1])
    args['lights'][0]['angularRadius'] = 0.1
    large = run('lightIndices', [[0, 0, 1, 0]], [[0, 0, 0, 0]], args)[0, 0]
    assert large == -1
    report['solarDiskMatching'] = indices.tolist()
    if options.dump:
        options.dump.mkdir(parents=True, exist_ok=True)
        (options.dump / 'cloud-lighting-contracts.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
