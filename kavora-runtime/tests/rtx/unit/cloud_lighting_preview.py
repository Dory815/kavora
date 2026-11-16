# SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
# SPDX-License-Identifier: MIT
"""Build the production cloud optical-depth tables for offline ray consumers."""
import re
import time

import numpy as np
import slangpy as spy


def build_lighting_cache(device, clouds, textures, shaders, lighting_enabled=True, warmup=False, repeats=1):
    source = (shaders / 'rtx/pass/clouds/cloud_lighting_cache.h').read_text()

    def constant(name):
        return int(re.search(rf'^#define {name}\s+(\d+)$', source, re.M).group(1))

    quality = np.clip(clouds['lightSteps'], constant('CLOUD_LIGHTING_MIN_QUALITY'),
                      constant('CLOUD_LIGHTING_MAX_QUALITY'))
    resolution = int(quality) * constant('CLOUD_LIGHTING_RESOLUTION_PER_STEP')
    light_height = resolution // constant('CLOUD_LIGHTING_LIGHT_HEIGHT_DIVISOR')
    sampler = device.create_sampler(min_filter=spy.TextureFilteringMode.linear,
                                    mag_filter=spy.TextureFilteringMode.linear,
                                    address_u=spy.TextureAddressingMode.clamp_to_edge,
                                    address_v=spy.TextureAddressingMode.clamp_to_edge,
                                    address_w=spy.TextureAddressingMode.clamp_to_edge)
    usage = spy.TextureUsage.shader_resource | spy.TextureUsage.unordered_access
    bindings = {'Clouds': clouds,
                **{name: value.descriptor_handle_combined for name, value in textures.items()}}
    resources = []
    result = {}
    measurements = {'resolution': resolution, 'volumes': []}
    enabled = lighting_enabled and clouds['enable'] and clouds['extinction'] > 0 and clouds['thickness'] > 0
    light_program = device.load_program('cloud_lighting_preview.comp.slang', ['buildLight'])
    light_kernel = device.create_compute_kernel(light_program)
    for index, name in enumerate(('CloudSunDepth', 'CloudMoonDepth')):
        light = clouds['lights'][index]
        active = enabled and (max(light['irradiance']) > 0
                              or (light.get('hasRadianceProfile', 0)
                                  and np.max(np.array(light['radianceProfile'])[:, :3]) > 0))
        width, height, depth = ((resolution, light_height, resolution)
                                if active else (1, 1, 1))
        texture = device.create_texture(type=spy.TextureType.texture_3d,
                                        format=spy.Format.r32_float,
                                        width=width, height=height, depth=depth, mip_count=1, usage=usage)
        if not active:
            texture.copy_from_numpy(np.zeros((1, 1, 1), np.float32))
        count = [resolution, light_height, 1]
        output_binding = {'LightIndex': index, 'LightOutput': texture}
        if active and warmup:
            light_kernel.dispatch(thread_count=count, vars={**bindings, **output_binding})
            device.wait_for_idle()
        samples = []
        for _ in range(repeats):
            started = time.monotonic()
            if active:
                light_kernel.dispatch(thread_count=count, vars={**bindings, **output_binding})
            device.wait_for_idle()
            samples.append(time.monotonic() - started)
        elapsed = float(np.median(samples))
        view = texture.create_view(sampler=sampler)
        resources.extend((texture, view))
        result[name] = view.descriptor_handle_combined
        measurements['volumes'].append({'name': name, 'extent': [width, height, depth], 'active': bool(active),
                                       'bytes': width * height * depth * 4,
                                       'dispatchWaitSeconds': elapsed, 'dispatchWaitSamplesSeconds': samples,
                                       'warmedUp': bool(warmup)})
    measurements['bytes'] = sum(v['bytes'] for v in measurements['volumes'])
    measurements['dispatchWaitSeconds'] = sum(v['dispatchWaitSeconds'] for v in measurements['volumes'])
    measurements['scope'] = 'Software or hardware Vulkan dispatch and host wait; not a game frame time.'
    return result, resources, measurements
