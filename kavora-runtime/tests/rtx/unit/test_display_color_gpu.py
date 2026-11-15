# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Execute shared color math and production tone/output passes on Vulkan.

Requires NumPy and SlangPy. --dump also requires Pillow and writes raw scene/HDR
arrays plus explicitly labelled SDR previews. --scene accepts a cloud-preview
NPZ containing result (RGB scattering, A transmission) and sky (linear RGB).
Software Vulkan is supported; this does not validate an HDR monitor or timing.
"""
import argparse
import json
from pathlib import Path
import re

import numpy as np
import slangpy as spy


HERE = Path(__file__).resolve().parent
SHADERS = HERE.parents[2] / "src/dxvk/shaders"
OPTIONS = {"include_paths": [str(HERE), str(SHADERS)], "defines": {"__SLANG__": "1"}}
USAGE = spy.TextureUsage.shader_resource | spy.TextureUsage.unordered_access


class ColorPasses:
    def __init__(self, device):
        self.device = device
        self.kernels = {}
        self.sampler = device.create_sampler(address_u=spy.TextureAddressingMode.clamp_to_edge,
                                             address_v=spy.TextureAddressingMode.clamp_to_edge,
                                             min_filter=spy.TextureFilteringMode.linear,
                                             mag_filter=spy.TextureFilteringMode.linear)
        self.exposure = device.create_texture(type=spy.TextureType.texture_1d, format=spy.Format.r32_float,
                                              width=1, usage=USAGE, data=np.ones(1, np.float32))

    def probe(self, operation, data):
        data = np.asarray(data, np.float32).reshape(-1, 4)
        if "probe" not in self.kernels:
            program = self.device.load_program("display_color_contracts.comp.slang", ["colorContracts"])
            self.kernels["probe"] = self.device.create_compute_kernel(program)
        result = self.device.create_buffer(element_count=len(data), struct_size=16,
                                           usage=spy.BufferUsage.unordered_access)
        self.kernels["probe"].dispatch(thread_count=[len(data), 1, 1], vars={
            "Inputs": self.device.create_buffer(data=data, usage=spy.BufferUsage.shader_resource),
            "Results": result, "Count": len(data), "Operation": operation,
        })
        return result.to_numpy().view(np.float32).reshape(-1, 4)[:, :3]

    def kernel(self, relative, inversion=False):
        key = (relative, inversion)
        if key in self.kernels:
            return self.kernels[key]
        defines = {"__SLANG__": "1", **({"DISPLAY_COLOR_INVERSION": "1"} if inversion else {})}
        session = self.device.create_slang_session({**OPTIONS, "defines": defines,
            "include_paths": [*OPTIONS["include_paths"], str((SHADERS / relative).parent)]})
        source = (SHADERS / relative).read_text(encoding="utf-8")
        # ShaderCursor binds a constant buffer; production push layouts are compiled separately.
        source = source.replace("layout(push_constant)", "")
        # Descriptor handles become ordinary uniforms, so let ShaderCursor assign the test slots.
        source = re.sub(r"\[\[vk::binding\([^)]*\)\]\]", "", source)
        source = re.sub(r"layout\(binding\s*=\s*[^)]+\)", "", source)
        source = re.sub(r",\s*binding\s*=\s*[^)]+\)", ")", source)
        # SlangPy exposes combined samplers through descriptor handles, without changing their samples.
        samplers = re.findall(r"\b(Sampler[123]D(?:<[^>]+>)?)\s+(\w+)\s*;", source)
        for sampler_type, name in samplers:
            explicit_type = sampler_type if "<" in sampler_type else sampler_type + "<float4>"
            source = source.replace(f"{sampler_type} {name};", f"{explicit_type}.Handle {name};")
            source = source.replace(f"{name}.SampleLevel", f"{explicit_type}({name}).SampleLevel")
        module = session.load_module_from_source(Path(relative).stem.replace(".", "_"), source)
        kernel = self.device.create_compute_kernel(session.link_program([module], [module.entry_point("main")]))
        self.kernels[key] = kernel
        return kernel

    def image(self, width, height, image_format=spy.Format.rgba16_float, data=None, mips=1):
        if data is not None:
            data = np.asarray(data, np.float16 if image_format == spy.Format.rgba16_float else np.float32)
        return self.device.create_texture(type=spy.TextureType.texture_2d, format=image_format,
                                           width=width, height=height, mip_count=mips, usage=USAGE, data=data)

    @staticmethod
    def rgba(rgb):
        return np.concatenate([np.asarray(rgb, np.float32), np.ones((*rgb.shape[:2], 1), np.float32)], axis=-1)

    def global_tone(self, rgb, hdr, peak=5.0, exposure=1.0):
        height, width = rgb.shape[:2]
        color = self.image(width, height, data=self.rgba(rgb))
        histogram = self.device.create_texture(type=spy.TextureType.texture_1d, format=spy.Format.r32_uint,
                                               width=256, usage=USAGE, data=np.zeros(256, np.uint32))
        curve = self.device.create_texture(type=spy.TextureType.texture_1d, format=spy.Format.r32_float,
                                           width=256, usage=USAGE, data=np.zeros(256, np.float32))
        if not hdr:
            self.kernel("rtx/pass/tonemap/tonemapping_histogram.comp.slang").dispatch(
                thread_count=[width, height, 1], vars={
                    "InColorBuffer": color, "InExposure": self.exposure, "InOutHistogram": histogram,
                    "cb": {"toneCurveMinStops": -24.0, "toneCurveMaxStops": 8.0,
                           "enableAutoExposure": 0, "exposureFactor": exposure},
                })
            self.kernel("rtx/pass/tonemap/tonemapping_tone_curve.comp.slang").dispatch(
                thread_count=[256, 1, 1], vars={
                    "InOutHistogram": histogram, "InOutToneCurve": curve,
                    "cb": {"dynamicRange": 15.0, "shadowMinSlope": 0.0, "shadowContrast": 0.0,
                           "shadowContrastEnd": 0.0, "maxExposureIncrease": 5.0, "curveShift": 0.0,
                           "needsReset": 1, "toneCurveMinStops": -24.0, "toneCurveMaxStops": 8.0},
                })
        curve_view = curve.create_view(sampler=self.sampler)
        self.kernel("rtx/pass/tonemap/tonemapping_apply_tonemapping.comp.slang").dispatch(
            thread_count=[width, height, 1], vars={
                "InColorBuffer": color, "OutColorBuffer": color, "InExposure": self.exposure,
                "InToneCurve": curve_view.descriptor_handle_combined,
                "cb": {"toneMappingEnabled": 1, "debugMode": 0, "enableAutoExposure": 0,
                       "hdrScene": hdr, "shadowContrast": 0.0, "shadowContrastEnd": 0.0,
                       "exposureFactor": exposure, "peakToWhite": peak,
                       "toneCurveMinStops": -24.0, "toneCurveMaxStops": 8.0,
                       "finalizeWithACES": 0, "useLegacyACES": 0},
            })
        return color.to_numpy().astype(np.float32)[..., :3]

    def local_tone(self, rgb, hdr, peak=5.0, exposure=1.0, shadows=2.0, highlights=4.0, sigma=4.0, offset=0.0):
        height, width = rgb.shape[:2]
        levels = min(4, int(np.log2(min(width, height))) + 1)
        color = self.image(width, height, data=self.rgba(rgb))
        luminance = self.image(width, height, mips=levels)
        weights = self.image(width, height, spy.Format.rgb10a2_unorm, mips=levels)
        assembled = self.image(width, height, spy.Format.r16_float, mips=levels)
        debug = self.image(width, height, spy.Format.rgba32_float)
        # Retain every descriptor view until readback completes, including all mip dependencies.
        views = []

        def view(texture, mip, sampled=False):
            result = texture.create_view(mip=mip, mip_count=1, sampler=self.sampler if sampled else None)
            views.append(result)
            return result.descriptor_handle_combined if sampled else result

        self.kernel("rtx/pass/local_tonemap/luminance.comp.slang").dispatch(
            thread_count=[width, height, 1], vars={
                "OriginalTexture": color, "OutLuminanceTexture": view(luminance, 0),
                "DebugView": debug, "AutoExposureTexture": self.exposure,
                "cb": {"exposure": exposure, "shadows": 2 ** shadows, "highlights": 2 ** -highlights, "debugView": 0,
                       "useLegacyACES": 0, "hdrScene": hdr, "enableAutoExposure": 0},
            })
        precision = sigma ** 2
        if hdr:
            span = 0.5 * (max(0, shadows, -highlights) - min(0, shadows, -highlights))
            precision /= 1 + precision * span ** 2
        self.kernel("rtx/pass/local_tonemap/exposure_weight.comp.slang").dispatch(
            thread_count=[width, height, 1], vars={
                "LuminanceTexture": view(luminance, 0), "WeightTexture": view(weights, 0), "DebugView": debug,
                "cb": {"sigmaSq": precision, "offset": offset, "debugView": 0, "hdrScene": hdr},
            })
        for texture in (luminance, weights):
            for mip in range(1, levels):
                size = [max(1, width >> mip), max(1, height >> mip)]
                self.kernel("rtx/pass/image_utils/generate_mipmap.comp.slang").dispatch(
                    thread_count=[*size, 1], vars={
                        "InputTexture": view(texture, mip - 1, True), "OutputTexture": view(texture, mip),
                        "cb": {"resolution": size, "method": 1},
                    })
        top = levels - 1
        self.kernel("rtx/pass/local_tonemap/blend.comp.slang").dispatch(
            thread_count=[width >> top, height >> top, 1], vars={
                "ExposureTexture": view(luminance, top), "WeightTexture": view(weights, top),
                "MipsAssembleTexture": view(assembled, top), "DebugView": debug, "cb": {"debugView": 0},
            })
        for mip in range(top, 0, -1):
            size = [width >> (mip - 1), height >> (mip - 1)]
            self.kernel("rtx/pass/local_tonemap/blend_laplacian.comp.slang").dispatch(
                thread_count=[*size, 1], vars={
                    "ExposuresTexture": view(luminance, mip - 1, True),
                    "ExposuresCoarserTexture": view(luminance, mip, True),
                    "WeightTexture": view(weights, mip - 1, True),
                    "AccumulateTexture": view(assembled, mip, True), "OutputTexture": view(assembled, mip - 1),
                    "DebugView": debug,
                    "cb": {"resolution": size, "boostLocalContrast": 0, "debugView": 0},
                })
        self.kernel("rtx/pass/local_tonemap/final_combine.comp.slang").dispatch(
            thread_count=[width, height, 1], vars={
                "MipAssembleTexture": view(assembled, 0, True), "OriginalMip0Texture": view(luminance, 0),
                "WeightMip0Texture": view(weights, 0), "OriginalMipTexture": view(luminance, 0, True),
                "OutputTexture": color, "DebugView": debug, "AutoExposureTexture": self.exposure,
                "cb": {"mipPixelSize": [width, height, 1 / width, 1 / height], "resolution": [width, height],
                       "exposure": exposure, "debugView": 0, "finalizeWithACES": 1, "enableAutoExposure": 0,
                       "useLegacyACES": 0, "hdrScene": hdr, "peakToWhite": peak},
            })
        result = color.to_numpy().astype(np.float32)[..., :3]
        packed_weights = weights.to_numpy().view(np.uint32)
        weight_sum = sum((packed_weights >> shift) & 1023 for shift in (0, 10, 20))
        assert np.all(weight_sum > 0), "all local exposure weights vanished"
        return result

    def output(self, rgb, extended, dither=0, frame=0, inversion=False):
        height, width = rgb.shape[:2]
        color = self.image(width, height, data=self.rgba(rgb))
        noise = self.device.create_texture(type=spy.TextureType.texture_2d, format=spy.Format.rgba32_float,
                                           width=1, height=1, array_length=1, usage=USAGE,
                                           data=np.zeros((1, 1, 1, 4), np.float32))
        self.kernel("rtx/pass/srgb_dither/srgb_dither.comp.slang", inversion).dispatch(
            thread_count=[width, height, 1], vars={
                "InOutColorBuffer": color, "BlueNoise": noise,
                "cb": {"performSRGBConversion": 1, "ditherMode": dither, "frameIndex": frame,
                       "colorGradingEnabled": 1, "colorBalance": [1, 1, 1], "contrast": 1.0, "saturation": 1.0,
                       "inversionAmount": 0.0, "inversionMode": 0, "inversionThreshold": 0.5,
                       "extendedSrgb": extended},
            })
        return color.to_numpy().astype(np.float32)[..., :3]


def srgb_encode(value):
    magnitude = np.abs(value)
    return np.sign(value) * np.where(magnitude <= 0.0031308, 12.92 * magnitude,
                                     1.055 * magnitude ** (1 / 2.4) - 0.055)


def assert_half_readback(actual, expected):
    # Storage-image conversion may round differently from NumPy's float16 cast.
    rounded = np.asarray(expected, np.float16)
    unit = np.maximum(np.abs(np.spacing(rounded)), np.finfo(np.float16).smallest_subnormal).astype(np.float32)
    error = np.abs(actual - rounded.astype(np.float32))
    assert np.all(error <= unit), f"FP16 readback differs by {np.max(error / unit):.3f} representable steps"


def check_math(passes):
    values = np.r_[-np.geomspace(1e-8, 16, 256)[::-1], 0, np.geomspace(1e-8, 16, 256)]
    rows = np.column_stack([values, values, values, np.zeros(len(values))])
    encoded = passes.probe(0, rows)
    np.testing.assert_allclose(encoded[:, 0], srgb_encode(values), atol=4e-7, rtol=2e-6)
    decoded = passes.probe(1, np.column_stack([encoded, np.zeros(len(values))]))
    np.testing.assert_allclose(decoded[:, 0], values, atol=4e-7, rtol=4e-6)
    nits = np.array([0, 1, 100, 203, 1000, 10000])
    pq = passes.probe(2, np.column_stack([nits, nits, nits, np.zeros(len(nits))]))[:, 0]
    np.testing.assert_allclose(pq, [7.309559e-7, 0.14994573, 0.50807842, 0.58068888, 0.75182710, 1], atol=2e-5)
    for peak in (1, 2, 5, 10, 50):
        ramp = np.geomspace(1e-8, 65504, 2048)
        mapped = passes.probe(4, np.column_stack([ramp, ramp * 0.5, ramp * 0.125, np.full(len(ramp), peak)]))
        assert np.isfinite(mapped).all() and np.all(np.diff(mapped[:, 0]) >= 0)
        assert np.all(mapped >= 0) and np.max(mapped) <= peak
        np.testing.assert_allclose(mapped[:, 1:], mapped[:, :1] * [0.5, 0.125], atol=2e-6)
    luminance = np.geomspace(1e-10, 65504 ** 2, 2048)
    log_result = passes.probe(6, np.column_stack([luminance, np.zeros((len(luminance), 3))]))
    np.testing.assert_allclose(log_result[:, 1], luminance, atol=1e-9, rtol=5e-6)
    assert np.all(np.diff(log_result[:, 0]) > 0)
    identity = passes.probe(7, np.column_stack([rows[:, :3].clip(0), np.ones(len(rows))]))
    np.testing.assert_allclose(identity, srgb_encode(rows[:, :3].clip(0)), atol=4e-7, rtol=2e-6)
    inverted_zero = passes.probe(8, np.column_stack([rows[:, :3].clip(0), np.ones(len(rows))]))
    np.testing.assert_allclose(inverted_zero, identity, atol=4e-7, rtol=2e-6)
    print("PASS GPU color math: extended transfer, PQ, HDR ratios/monotonicity, reversible HDR fusion and grading")


def check_passes(passes):
    ramp = np.geomspace(1e-5, 65504, 256).astype(np.float32)
    gradient = np.tile(np.stack([ramp, ramp * 0.5, ramp * 0.125], axis=-1)[None, ...], (64, 1, 1))
    hdr = passes.global_tone(gradient, True)
    expected = passes.probe(4, np.column_stack([gradient.astype(np.float16).astype(np.float32).reshape(-1, 3),
                                              np.full(gradient.shape[0] * gradient.shape[1], 5)]))
    assert_half_readback(hdr.reshape(-1, 3), expected)
    assert np.max(hdr) > 4 and np.all(np.diff(hdr[0, :, 0]) >= 0)
    shared = passes.output(hdr, True, dither=2, frame=83)
    np.testing.assert_allclose(shared, passes.output(hdr, True, dither=0, frame=0), atol=0, rtol=0)
    assert_half_readback(shared, srgb_encode(hdr))
    assert np.max(shared) > 1
    legacy = passes.output(hdr, False)
    np.testing.assert_allclose(legacy, np.clip(hdr, 0, 1) ** (1 / 2.2), atol=0.0005, rtol=0)
    local = passes.local_tone(gradient, True)
    assert np.isfinite(local).all() and np.all(local >= 0) and np.max(local) <= 5
    assert np.max(local) > 4, "local fusion lost HDR highlights"
    for value in (0.0, 0.18, 1.0, 16.0, 65504.0):
        uniform = passes.local_tone(np.full((32, 32, 3), value, np.float32), True)
        assert np.isfinite(uniform).all() and np.max(np.ptp(uniform, axis=(0, 1))) < 0.002
        if value > 0:
            assert np.min(uniform) > 0, "bright uniform local image turned black"
    y, x = np.indices((64, 128))
    edge_luminance = np.where(x > 48 + y // 3, 256.0, 0.18).astype(np.float32)
    edges = edge_luminance[..., None] * np.array([1.0, 0.5, 0.25], np.float32)
    fused = passes.local_tone(edges, True)
    # The reconstruction must remain within the two supplied synthetic exposure gains.
    # FP16 storage on the log axis introduces a small relative error after inversion.
    bounds = []
    for gain in (0.0625, 4.0):
        rows = np.column_stack([edges.reshape(-1, 3) * gain, np.full(edges.shape[0] * edges.shape[1], 5)])
        bounds.append(passes.probe(4, rows).reshape(edges.shape))
    assert np.all(fused >= bounds[0] * 0.99), "local HDR reconstruction exceeded its minimum exposure"
    assert np.all(fused <= bounds[1] * 1.01), "local HDR reconstruction exceeded its maximum exposure"
    assert np.all(fused > 0), "positive high-contrast scene produced black halos"
    values = np.geomspace(0.001, 10000, 64).astype(np.float32)
    tiles = np.repeat(np.repeat(values.reshape(8, 8), 64, axis=0), 64, axis=1)
    neutral = np.repeat(tiles[..., None], 3, axis=-1)
    for shadows, highlights, sigma, offset in ((2, 4, 4, 0), (2, 6, 4, 0), (-10, 10, 100, 1)):
        mapped = passes.local_tone(neutral, True, shadows=shadows, highlights=highlights, sigma=sigma, offset=offset)
        centers = mapped[32::64, 32::64, 0].ravel()
        assert np.all(np.diff(centers) >= 0), ("HDR exposure preference reversed uniform gray levels",
                                               (shadows, highlights, sigma, offset), centers.tolist())
    for mapper in (passes.global_tone, passes.local_tone):
        sdr = mapper(gradient, False)
        assert np.isfinite(sdr).all() and np.min(sdr) >= 0 and np.max(sdr) <= 1
    print("PASS production FP16 passes: global/local pipelines, uniform extremes, bounded edge exposure, shared no-dither and legacy output")
    return gradient


def dump_examples(passes, directory, gradient, scene_path):
    from PIL import Image, ImageDraw
    directory.mkdir(parents=True, exist_ok=True)
    examples = {"gradient": gradient}
    if scene_path:
        data = np.load(scene_path)
        examples["sunset"] = data["result"][..., :3] + data["result"][..., 3, None] * data["sky"]
    manifest = {"device": "Vulkan", "paper_white_nits": 203, "peak_nits": 1000,
                "preview": "SDR fallback of HDR data; not an HDR monitor capture", "examples": {}}
    for name, raw in examples.items():
        exposure = 0.25 if name == "sunset" else 1.0
        peak = 1000 / 203
        outputs = {"raw_scene": raw}
        panels = []
        for label, mapper in (("global", passes.global_tone), ("local", passes.local_tone)):
            hdr = mapper(raw, True, peak, exposure)
            sdr = mapper(raw, False, peak, exposure)
            outputs[label + "_hdr_linear"] = hdr
            outputs[label + "_hdr_extended_srgb"] = passes.output(hdr, True)
            outputs[label + "_sdr_linear"] = sdr
            fallback = passes.probe(5, np.column_stack([hdr.reshape(-1, 3), np.full(hdr.shape[0] * hdr.shape[1], peak)]))
            fallback = fallback.reshape(hdr.shape)
            for title, image in ((label + " SDR tone path", srgb_encode(sdr)),
                                 (label + " HDR -> SDR preview", srgb_encode(fallback))):
                image = Image.fromarray(np.rint(np.clip(image, 0, 1) * 255).astype(np.uint8))
                image.thumbnail((768, 512))
                panel = Image.new("RGB", (image.width, image.height + 30), (22, 24, 28))
                panel.paste(image, (0, 30))
                ImageDraw.Draw(panel).text((8, 8), title, fill="white")
                panels.append(panel)
        width = max(panel.width for panel in panels)
        height = max(panel.height for panel in panels)
        sheet = Image.new("RGB", (2 * width, 2 * height + 50), (22, 24, 28))
        ImageDraw.Draw(sheet).text((8, 8), "Production tone passes | HDR shown through SDR fallback", fill="white")
        ImageDraw.Draw(sheet).text((8, 26), "Paper white 203 nits; peak 1000 nits; FP16 source/output; fixed exposure", fill="white")
        for i, panel in enumerate(panels):
            sheet.paste(panel, ((i % 2) * width, 50 + (i // 2) * height))
        sheet.save(directory / f"{name}-sdr-preview.png")
        np.savez_compressed(directory / f"{name}-hdr-data.npz", **outputs)
        manifest["examples"][name] = {"exposure": exposure, "source": str(scene_path) if name == "sunset" else "log RGB gradient",
                                      **{key: {"minimum": float(value.min()), "maximum": float(value.max())}
                                         for key, value in outputs.items()}}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path)
    parser.add_argument("--scene", type=Path)
    args = parser.parse_args()
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options=OPTIONS)
    passes = ColorPasses(device)
    check_math(passes)
    gradient = check_passes(passes)
    if args.dump:
        dump_examples(passes, args.dump, gradient, args.scene)


if __name__ == "__main__":
    main()
