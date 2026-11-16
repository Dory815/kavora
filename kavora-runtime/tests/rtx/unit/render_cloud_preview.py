# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Render actual production Slang cloud density without starting Minecraft.

Requires numpy, Pillow and slangpy. A software Vulkan ICD is sufficient.

Perspective opacity uses cloudTransmittance directly. Top-down optical depth
integrates cloudExtinction without the camera-distance fade. Optional radiance
uses production cloudIncidentRadiance under a constant diagnostic environment.

--shader-root selects code, not that revision's native option defaults; pass the
same explicit CLI parameters when comparing shader revisions.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time

import numpy as np
from PIL import Image, ImageDraw
import slangpy as spy


HERE = Path(__file__).resolve().parent
DEFAULT_REPO = HERE.parents[3]
VIEWS = {
    'top': (0.0, -90.0), 'zenith': (0.0, 90.0),
    '45': (0.0, 45.0), 'horizon': (0.0, 10.0), 'zenith90': (90.0, 90.0),
}


def triple(value):
    result = [float(v) for v in value.split(',')]
    if len(result) != 3 or not np.isfinite(result).all():
        raise argparse.ArgumentTypeError('expected three finite values: x,y,z')
    return result


def basis(yaw, pitch):
    yaw, pitch = np.radians([yaw, pitch])
    forward = np.array([np.sin(yaw) * np.cos(pitch), np.sin(pitch), np.cos(yaw) * np.cos(pitch)])
    right = np.array([np.cos(yaw), 0, -np.sin(yaw)])
    return forward.tolist(), right.tolist(), np.cross(forward, right).tolist()


def texture_cache(device, support, shaders, cache_dir, noise_seed=None):
    files = ('rtx/pass/clouds/generate_cloud_noise.comp.slang',
             'rtx/pass/clouds/generate_cloud_weather.comp.slang',
             'rtx/pass/clouds/filter_cloud_noise.comp.slang',
             'rtx/utility/cloud_noise.slangh', 'rtx/pass/cloud_noise.h',
             'rtx/utility/cloud_shape.slang', 'rtx/utility/cirrus_shapes.slangh')
    shader_files = [shaders / name for name in files]
    digest = hashlib.sha256()
    source_hashes = {}
    for path in shader_files:
        if path.exists():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
            source_hashes[str(path.relative_to(shaders))] = hashlib.sha256(path.read_bytes()).hexdigest()
    atlas = support.cloud_atlas_path() if hasattr(support, 'cloud_atlas_path') else None
    if atlas is not None and atlas.exists():
        atlas_bytes = atlas.read_bytes()
        digest.update(atlas_bytes)
        source_hashes['cirrus_density.dds'] = hashlib.sha256(atlas_bytes).hexdigest()
    if noise_seed is not None:
        # A test-only seed input: compile the unchanged production algorithms
        # against a copied include with just their fixed seed constant changed.
        source = (shaders / 'rtx/utility/cloud_noise.slangh').read_text()
        source, replacements = re.subn(r'(kCloudNoiseSeed\s*=\s*)0x[0-9a-fA-F]+u',
                                        lambda match: match[1] + f'0x{noise_seed:08x}u', source)
        if replacements != 1:
            raise RuntimeError('Could not identify the production noise seed')
        overlay = cache_dir / 'seed-overlays' / f'{noise_seed:08x}'
        include = overlay / 'rtx/utility/cloud_noise.slangh'
        include.parent.mkdir(parents=True, exist_ok=True)
        include.write_text(source)
        support.OPTIONS = {**support.OPTIONS,
                           'include_paths': [str(overlay), *support.OPTIONS['include_paths']]}
        digest.update(source.encode())
    cache = cache_dir / f'textures-{digest.hexdigest()[:20]}.npz'
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        started = time.monotonic()
        textures = support.cloud_textures(device)
        np.savez(cache, **{f'{name}_{mip}': view.texture.to_numpy(mip=mip)
                          for name, view in textures.items() for mip in range(view.texture.mip_count)})
        print(f'Cached production textures: {cache.name} ({time.monotonic() - started:.2f}s)', flush=True)
    sampler = device.create_sampler(min_filter=spy.TextureFilteringMode.linear,
                                    mag_filter=spy.TextureFilteringMode.linear,
                                    mip_filter=spy.TextureFilteringMode.linear,
                                    address_u=spy.TextureAddressingMode.wrap,
                                    address_v=spy.TextureAddressingMode.wrap,
                                    address_w=spy.TextureAddressingMode.wrap)
    textures = {}
    with np.load(cache) as values:
        for name in ('Base', 'Detail', 'Weather'):
            data = values[f'{name}_0']
            size, dimensions = data.shape[0], data.ndim - 1
            texture_format = spy.Format.rgba8_unorm
            if data.dtype.kind == 'f':
                texture_format = spy.Format.rg16_float if data.shape[-1] == 2 else spy.Format.rgba16_float
            texture = device.create_texture(
                type=spy.TextureType.texture_3d if dimensions == 3 else spy.TextureType.texture_2d,
                format=texture_format,
                width=size, height=size, depth=size if dimensions == 3 else 1,
                mip_count=int(np.log2(size)) + 1, usage=spy.TextureUsage.shader_resource)
            for mip in range(texture.mip_count):
                texture.copy_from_numpy(values[f'{name}_{mip}'], mip=mip)
            textures[name] = texture.create_view(sampler=sampler)
    return textures, str(cache), {'fingerprint': digest.hexdigest(), 'sourceHashes': source_hashes}


def save_image(path, rgb):
    Image.fromarray(np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(path)


def compare_texture_channels(reference, candidate):
    report = {}
    with np.load(reference) as before, np.load(candidate) as after:
        for name, channels in (('Base', [0, 1]), ('Weather', [0, 1, 2]), ('Detail', [0, 1, 2, 3])):
            exact = True
            maximum = 0.0
            changed = 0
            count = 0
            for key in sorted(key for key in before.files if key.startswith(name + '_')):
                a, b = before[key][..., channels], after[key][..., channels]
                if a.shape != b.shape or a.dtype != b.dtype:
                    report[name] = {'compatible': False, 'referenceShape': list(a.shape), 'candidateShape': list(b.shape)}
                    break
                exact &= np.array_equal(a, b)
                changed += int(np.count_nonzero(a != b))
                count += a.size
                maximum = max(maximum, float(np.max(np.abs(a.astype(np.float32) - b.astype(np.float32)))))
            else:
                report[name] = {'channels': channels, 'exactEqual': bool(exact), 'changedValues': changed,
                                'valueCount': count, 'maximumStoredValueDifference': maximum}
    return report


def contact_sheet(output, label, views, width, height, radiance, origin, vfov):
    panels = []
    for view in views:
        panels.append((f'{view}: production cloud opacity (white = 1-T)', output / f'{view}-opacity.png'))
        if view == 'top':
            panels.append(('top: vertical optical depth, fixed display range 0..1', output / 'top-tau.png'))
        elif radiance:
            panels.append((f'{view}: production scattering + diagnostic sky', output / f'{view}-radiance.png'))
    columns = 2
    title_height, caption_height = 64, 34
    rows = (len(panels) + columns - 1) // columns
    sheet = Image.new('RGB', (columns * width, title_height + rows * (height + caption_height)), '#191c24')
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 9), label, fill='white')
    draw.text((12, 29), f'Production Slang; VFOV{vfov:g}; camera{tuple(origin)}; no game/atmosphere/temporal reconstruction', fill='#bec6d4')
    for index, (caption, path) in enumerate(panels):
        x, y = (index % columns) * width, title_height + (index // columns) * (height + caption_height)
        draw.text((x + 7, y + 8), caption, fill='white')
        sheet.paste(Image.open(path).convert('RGB'), (x, y + caption_height))
    sheet.save(output / 'contact-sheet.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=DEFAULT_REPO)
    parser.add_argument('--shader-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='Production cloud inspection')
    parser.add_argument('--cache-dir', type=Path, help='Generated texture cache; defaults beside output')
    parser.add_argument('--compare-textures', type=Path, help='Reference texture cache for exact low-field channel comparisons')
    parser.add_argument('--width', type=int, default=384)
    parser.add_argument('--height', type=int, default=256)
    parser.add_argument('--vfov', type=float, default=75)
    parser.add_argument('--origin', type=triple, default=[0, 139, 0])
    parser.add_argument('--wind', type=triple, default=[0, 0, 0])
    parser.add_argument('--views', default='top,zenith,45,horizon,zenith90')
    parser.add_argument('--layers', choices=['high', 'low', 'both'], default='high')
    parser.add_argument('--high-base', type=float, default=6300.0, help='High cloud base in meters')
    parser.add_argument('--high-thickness', type=float, default=200.0, help='High cloud thickness in meters')
    parser.add_argument('--high-extinction', type=float, default=0.006, help='High cloud extinction per meter')
    parser.add_argument('--coverage', type=float, default=0.35, help='High layer coverage')
    parser.add_argument('--weather', type=float, default=0)
    parser.add_argument('--sun-elevation', type=float,
                        help='Diagnostic sun elevation in degrees at fixed 30-degree azimuth; no atmospheric coloring')
    parser.add_argument('--noise-seed', type=lambda value: int(value, 0),
                        help='Test-only generator seed override; production default if omitted')
    parser.add_argument('--top-span', type=float, default=32000)
    parser.add_argument('--radiance', action='store_true')
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0 or not np.isfinite(args.top_span) or args.top_span <= 0:
        parser.error('width, height and top-span must be positive')
    if not 0 < args.vfov < 180:
        parser.error('vfov must be between 0 and 180 degrees')
    if args.sun_elevation is not None and not -90 <= args.sun_elevation <= 90:
        parser.error('sun-elevation must be between -90 and 90 degrees')
    if (not np.isfinite([args.high_base, args.high_thickness, args.high_extinction]).all()
            or args.high_base < 0 or args.high_thickness <= 0 or args.high_extinction < 0):
        parser.error('high cloud base/extinction must be nonnegative and thickness must be positive')
    views = args.views.split(',')
    unknown_views = sorted(set(views) - VIEWS.keys())
    if unknown_views:
        parser.error('unknown views: ' + ', '.join(unknown_views))
    shaders = args.shader_root or args.repo / 'kavora-runtime/src/dxvk/shaders'
    support_path = args.repo / 'kavora-runtime/tests/rtx/unit/test_cloud_transport.py'
    spec = importlib.util.spec_from_file_location('cloud_test_support', support_path)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    support.SHADERS = shaders
    support.OPTIONS = {'include_paths': [str(shaders), str(HERE)], 'defines': {'__SLANG__': '1'}}
    if re.search(r'\bpublic\s+float\s+spanAt\s*\(', (shaders / 'rtx/algorithm/clouds.slang').read_text()):
        support.OPTIONS['defines']['CLOUD_PREVIEW_HAS_CELL_SPAN'] = '1'
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options=support.OPTIONS)
    if args.noise_seed is not None and not 0 <= args.noise_seed <= 0xffffffff:
        parser.error('--noise-seed must fit in an unsigned 32-bit value')
    cache_dir = args.cache_dir or args.output.parent / 'cloud-preview-cache'
    textures, cache, texture_sources = texture_cache(device, support, shaders, cache_dir, args.noise_seed)
    program = device.load_program('cloud_preview.comp.slang', ['main'])
    kernel = device.create_compute_kernel(program)
    output = device.create_buffer(element_count=args.width * args.height, struct_size=16,
                                  usage=spy.BufferUsage.unordered_access)
    sun = [0.3, 0.8, np.sqrt(1 - 0.3 ** 2 - 0.8 ** 2)]
    if args.sun_elevation is not None:
        elevation = np.radians(args.sun_elevation)
        sun = [0.5 * np.cos(elevation), np.sin(elevation), np.sqrt(0.75) * np.cos(elevation)]
    light = {'directionToLight': sun, 'irradiance': [np.pi, np.pi, np.pi], 'hasRadianceProfile': 0}
    dark = {'directionToLight': [0, -1, 0], 'irradiance': [0, 0, 0], 'hasRadianceProfile': 0}
    clouds = support.cloud_parameters(
        highBaseHeight=args.high_base, highThickness=args.high_thickness, highExtinction=args.high_extinction,
        highCoverage=args.coverage, highMaxDistance=96000.0,
        groundReference=[args.origin[0], 0, args.origin[2]], windOffset=args.wind,
        viewAngularFootprint=2 * np.tan(np.radians(args.vfov) * 0.5) / args.height,
        weather=args.weather, lights=[light, dark])
    if args.layers == 'high': clouds['extinction'] = 0
    if args.layers == 'low': clouds['highExtinction'] = 0
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'label': args.label, 'shaderRoot': str(shaders), 'textureCache': cache,
                'textureSources': texture_sources,
                'previewShaderHash': hashlib.sha256((HERE / 'cloud_preview.comp.slang').read_bytes()).hexdigest(),
                'previewDefines': support.OPTIONS['defines'],
                'camera': args.origin, 'verticalFovDegrees': args.vfov, 'resolution': [args.width, args.height],
                'layers': args.layers, 'topSpanMeters': args.top_span, 'topHeightMeters': 10000.0,
                'clouds': clouds, 'views': {}, 'diagnosticAmbient': [0.04, 0.06, 0.10],
                'diagnosticSunElevationDegrees': float(np.degrees(np.arcsin(sun[1]))),
                'diagnosticSkyLinearRgb': [0.12, 0.26, 0.48],
                'displayTransfer': 'linear RGB to sRGB; no tone mapping or auto exposure',
                'testNoiseSeedOverride': args.noise_seed,
                'coordinateConvention': 'Y up; yaw0 faces +Z; elevation positive up',
                'sourceHashes': {str(path.relative_to(shaders)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in (shaders / 'rtx/utility/cloud_density.slang',
                                              shaders / 'rtx/algorithm/clouds.slang')}}
    if args.compare_textures:
        manifest['lowFieldTextureComparison'] = compare_texture_channels(args.compare_textures, cache)
        print('Low-field assets:', json.dumps(manifest['lowFieldTextureComparison']), flush=True)
    for view in views:
        yaw, pitch = VIEWS[view]
        forward, right, up = basis(yaw, pitch)
        origin = [args.origin[0], 10000, args.origin[2]] if view == 'top' else args.origin
        started = time.monotonic()
        kernel.dispatch(thread_count=[args.width, args.height, 1], vars={
            'Clouds': clouds, 'Results': output, 'Size': [args.width, args.height],
            'Origin': origin, 'Forward': forward, 'Right': right, 'CameraUp': up,
            'TanHalfFov': np.tan(np.radians(args.vfov) * 0.5), 'TopSpan': args.top_span,
            'Ambient': [0.04, 0.06, 0.10], 'Projection': int(view == 'top'),
            'Radiance': int(args.radiance and view != 'top'),
            **{name: value.descriptor_handle_combined for name, value in textures.items()},
        })
        data = output.to_numpy().view(np.float32).reshape(args.height, args.width, 4)
        if not np.isfinite(data).all(): raise RuntimeError(f'Nonfinite production output in {view}')
        opacity = 1 - data[:, :, 3]
        np.savez(args.output / f'{view}.npz', result=data)
        save_image(args.output / f'{view}-opacity.png', np.repeat(opacity[:, :, None], 3, axis=2))
        if view == 'top':
            save_image(args.output / 'top-tau.png', np.repeat(data[:, :, :1], 3, axis=2))
        elif args.radiance:
            rgb = data[:, :, :3] + data[:, :, 3:] * np.array([0.12, 0.26, 0.48])
            rgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - 0.055)
            save_image(args.output / f'{view}-radiance.png', rgb)
        statistics = {'yawDegrees': yaw, 'elevationDegrees': pitch, 'seconds': time.monotonic() - started,
                      'meanOpacity': float(opacity.mean()), 'maxOpacity': float(opacity.max()),
                      'opacityAboveOnePercent': float(np.mean(opacity > 0.01))}
        manifest['views'][view] = statistics
        print(view, json.dumps(statistics), flush=True)
        (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    contact_sheet(args.output, args.label, views, args.width, args.height, args.radiance, args.origin, args.vfov)
    print('Saved', args.output / 'contact-sheet.png', flush=True)


if __name__ == '__main__':
    main()
