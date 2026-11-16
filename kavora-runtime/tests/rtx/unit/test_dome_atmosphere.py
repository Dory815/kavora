# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Read back the production dome compositor's full-sky and finite-air boundaries.

Requires NumPy and SlangPy. A software Vulkan ICD is sufficient. This verifies
layer ownership and texture values, not game presentation or performance.
"""
from pathlib import Path
import re

import numpy as np
import slangpy as spy


SHADERS = Path(__file__).resolve().parents[3] / "src/dxvk/shaders"


def decode_r11g11b10(texture):
    packed = texture.to_numpy().view(np.uint32).reshape(-1)
    result = []
    for shift, mantissa_bits in ((0, 6), (11, 6), (22, 5)):
        bits = (packed >> shift) & ((1 << (mantissa_bits + 5)) - 1)
        exponent = (bits >> mantissa_bits).astype(np.int32)
        mantissa = (bits & ((1 << mantissa_bits) - 1)).astype(np.float32)
        result.append(np.where(exponent == 0, mantissa * 2.0 ** (-14 - mantissa_bits),
                               (1 + mantissa / (1 << mantissa_bits)) * np.exp2(exponent - 15)))
    return np.stack(result, axis=-1)


def main():
    device = spy.Device(type=spy.DeviceType.vulkan, compiler_options={
        "include_paths": [str(SHADERS)], "defines": {"__SLANG__": "1"}, "disable_warnings": ["30081"]})
    source_text = (SHADERS / "rtx/pass/dome_composite/dome_composite.comp.slang").read_text(encoding="utf-8")
    # SlangPy writes a constant buffer and combined-sampler descriptor handles.
    # Native push constants and descriptor slots are compiled separately without this adapter.
    source_text = re.sub(r"layout\([^)]*\)\s*", "", source_text)
    source_text = source_text.replace("Sampler2D<float4> DomeSource;", "Sampler2D<float4>.Handle DomeSource;")
    source_text = source_text.replace("Sampler2D<float3> DomeTransmittance;", "Sampler2D<float3>.Handle DomeTransmittance;")
    session = device.create_slang_session({"include_paths": [str(SHADERS), str(SHADERS / "rtx/pass/dome_composite")],
                                         "defines": {"__SLANG__": "1"}, "disable_warnings": ["30081"]})
    module = session.load_module_from_source("dome_atmosphere_contract", source_text)
    kernel = device.create_compute_kernel(session.link_program([module], [module.entry_point("main")]))
    sampler = device.create_sampler(address_u=spy.TextureAddressingMode.clamp_to_edge,
                                    address_v=spy.TextureAddressingMode.clamp_to_edge)
    usage = spy.TextureUsage.shader_resource | spy.TextureUsage.unordered_access
    outputs = {name: device.create_texture(type=spy.TextureType.texture_2d,
               format=spy.Format.r11g11b10_float, width=8, height=4, usage=usage)
               for name in ("DomeOutput", "VisibleBackground", "Boundary")}

    def source(color):
        texture = device.create_texture(type=spy.TextureType.texture_2d, format=spy.Format.rgba32_float,
                                        width=1, height=1, usage=spy.TextureUsage.shader_resource,
                                        data=np.asarray([[color]], dtype=np.float32))
        return texture.create_view(sampler=sampler)

    unit = source([1, 1, 1, 1])
    transmission = source([.5, .25, .125, 1])
    sky = source([1, 2, 4, 1])
    disk = source([2, 1, .5, 1])
    air = source([.125, .25, .5, 1])
    identity = np.asarray([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]], dtype=np.float32)

    def draw(texture, flags, blend=0, transmittance=unit):
        kernel.dispatch(thread_count=[8, 4, 1], vars={
            **outputs, "DomeSource": texture.descriptor_handle_combined,
            "DomeTransmittance": transmittance.descriptor_handle_combined,
            "cb": {"worldToLight": identity, "outputToWorld": identity,
                   "radiance": [1, 1, 1], "opacity": 1, "width": 8, "height": 4,
                   "flags": flags, "blendType": blend}})

    # First-layer state must clear a preceding frame of either transport mode.
    for finite in (False, True, False, True):
        flags = 2 | 32 | (128 if finite else 0)
        draw(sky, flags | 1)
        draw(disk, flags | 16, blend=6)
        draw(air, flags | 4 | 2048, transmittance=transmission)
        np.testing.assert_allclose(decode_r11g11b10(outputs["DomeOutput"]),
                                   np.tile([.625, .75, 1], (32, 1)), rtol=0, atol=0)
        visible = [3, 3, 4.5] if finite else [1.625, 1, 1.0625]
        np.testing.assert_allclose(decode_r11g11b10(outputs["VisibleBackground"]),
                                   np.tile(visible, (32, 1)), rtol=0, atol=0)
        if finite:
            np.testing.assert_allclose(decode_r11g11b10(outputs["Boundary"]),
                                       np.tile([1, 2, 4], (32, 1)), rtol=0, atol=0)
    print("PASS production dome: full lighting, raw visible/lighting boundaries, and air-mode transitions")


if __name__ == "__main__":
    main()
