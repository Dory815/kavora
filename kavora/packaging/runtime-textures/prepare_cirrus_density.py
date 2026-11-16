# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: Apache-2.0

"""Extract a scalar cirrus morphology atlas from the credited CC0 photos.

This is an offline asset preparation tool, not part of the build. Input paths
follow the source order in cirrus_sources.json. It also writes the shader's
crop geometry and variant groups. Requires NumPy and Pillow.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


DIRECTORY = Path(__file__).resolve().parent
GEOMETRY_OUTPUT = DIRECTORY.parents[2] / "kavora-runtime/src/dxvk/shaders/rtx/utility/cirrus_shapes.slangh"


def crop_bounds(image, patch):
    return tuple(round(p * s) for p, s in zip(
        patch["bounds"], (image.width, image.height, image.width, image.height)))


def extract_patch(image, patch, size):
    left, top, right, bottom = patch["bounds"]
    crop = image.crop(crop_bounds(image, patch))
    rgb = np.asarray(crop.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float64) / 255
    rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    ratio = rgb[..., 0] / np.maximum(rgb[..., 2], 1e-5)
    y, x = np.mgrid[-1:1:complex(0, size), -1:1:complex(0, size)]
    fit = np.stack([x, y, x * y, x * x, y * y, np.ones_like(x)], -1)
    border = np.maximum(np.abs(x), np.abs(y)) > 0.80
    valid = rgb[..., 2] > 0.08
    # White cloud cores are valid morphology, but must not fit the blue sky.
    clear_candidate = valid & (ratio < 0.8)
    clear = border & clear_candidate
    # Reject bright cloud outliers while fitting the blue-sky colour gradient.
    for _ in range(4):
        coefficients = np.linalg.lstsq(fit[clear], ratio[clear], rcond=None)[0]
        residual = ratio - fit @ coefficients
        tolerance = max(0.003, np.percentile(np.abs(residual[clear]), 65) * 2)
        clear = border & clear_candidate & (residual < tolerance)
    background = np.clip(fit @ coefficients, 0, 0.7)
    noise = np.median(np.abs(residual[clear] - np.median(residual[clear]))) / 0.6745
    relative = np.maximum(ratio - background - max(0.005, 2.5 * noise), 0) / (1 - background)
    relative[~valid] = 0
    # One shared scale retains the relative strength of the different clouds.
    relative = np.clip(relative * 2, 0, 1)
    if "selection" in patch:
        selection = Image.new("L", (size, size))
        points = [((u - left) / (right - left) * size, (v - top) / (bottom - top) * size)
                  for u, v in patch["selection"]]
        ImageDraw.Draw(selection).polygon(points, fill=255)
        selection = selection.filter(ImageFilter.GaussianBlur(7))
        relative *= np.asarray(selection, dtype=np.float32) / 255
    if "foregroundExclusion" in patch:
        u = (x + 1) * 0.5 * (right - left) + left
        v = (y + 1) * 0.5 * (bottom - top) + top
        u_limit, v_limit = patch["foregroundExclusion"]
        relative[(u < u_limit) & (v < v_limit)] = 0
    # Clear-sky padding prevents filter taps from reaching adjacent atlas tiles.
    edge = np.minimum(1 - np.abs(x), 1 - np.abs(y))
    fade = np.clip(edge / 0.12, 0, 1)
    relative *= fade * fade * (3 - 2 * fade)
    for axis in (0, 1):
        padding = [(0, 0), (0, 0)]
        padding[axis] = (1, 1)
        padded = np.pad(relative, padding)
        relative = (0.106507 * np.take(padded, np.arange(size), axis=axis)
                    + 0.786986 * np.take(padded, np.arange(size) + 1, axis=axis)
                    + 0.106507 * np.take(padded, np.arange(size) + 2, axis=axis))
    return relative


def encode_dds(atlas):
    height, width = atlas.shape
    mip_count = max(width, height).bit_length()
    # DX10 R8_UNORM stores linear relative density, with no RGB or sRGB decode.
    header = [124, 0x2100F, height, width, width, 0, mip_count] + [0] * 11
    header += [32, 4, int.from_bytes(b"DX10", "little"), 0, 0, 0, 0, 0]
    header += [0x401008, 0, 0, 0, 0]
    data = bytearray(b"DDS " + struct.pack("<31I", *header) + struct.pack("<5I", 61, 3, 0, 1, 0))
    for level in range(mip_count):
        data.extend(np.uint8(np.rint(atlas * 255)).tobytes())
        if level + 1 < mip_count:
            height, width = atlas.shape
            if height % 2 == 0 and width % 2 == 0:
                atlas = atlas.reshape(height // 2, 2, width // 2, 2).mean(axis=(1, 3))
            else:
                atlas = np.asarray(Image.fromarray(atlas).resize(
                    (max(1, width // 2), max(1, height // 2)), Image.Resampling.BOX))
    return data


def encode_geometry(metadata, images, columns, rows):
    patches = metadata["patches"]
    groups = metadata["groups"]
    if len(groups) != 3 or any(not 1 <= len(group) <= 4 for group in groups):
        raise ValueError("The three cirrus groups must each contain one to four distinct shapes")
    if sorted(tile for group in groups for tile in group) != list(range(len(patches))):
        raise ValueError("Cirrus groups must partition the atlas shapes without repetition")
    lines = [
        "/* SPDX-FileCopyrightText: Copyright (c) 2026 GBwater",
        " * SPDX-License-Identifier: MIT",
        " */",
        "#pragma once",
        "",
        "// Generated by prepare_cirrus_density.py from cirrus_sources.json.",
        f"static const uint2 kCirrusAtlasGrid = uint2({columns}u, {rows}u);",
        f"static const uint kCirrusGroupCount = {len(groups)}u;",
        f"static const float2 kCirrusGeometry[{len(patches)}] = {{",
    ]
    for patch in patches:
        left, top, right, bottom = crop_bounds(images[patch["source"]], patch)
        if right <= left or bottom <= top or not np.isfinite(patch["flowAngle"]):
            raise ValueError("Cirrus crop geometry must be finite and nonempty")
        lines.append(f"  float2({(right - left) / (bottom - top):.8f}f, {patch['flowAngle']:.8f}f),")
    lines += ["};", "", f"static const uint kCirrusGroupSizes[{len(groups)}] = {{",
              "  " + ", ".join(f"{len(group)}u" for group in groups), "};", "",
              f"static const uint4 kCirrusGroups[{len(groups)}] = {{"]
    lines += ["  uint4(" + ", ".join(f"{tile}u" for tile in [*group, *([0] * (4 - len(group)))]) + "),"
              for group in groups]
    lines += ["};", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path, metavar="PHOTO")
    parser.add_argument("--output", type=Path, default=DIRECTORY / "cirrus_density.dds")
    parser.add_argument("--geometry-output", type=Path, default=GEOMETRY_OUTPUT,
                        help="Generated shader metadata; defaults to the native cirrus shape include")
    parser.add_argument("--preview", type=Path, help="Optional scalar PNG for visual inspection")
    args = parser.parse_args()
    metadata = json.loads((DIRECTORY / "cirrus_sources.json").read_text())
    if len(args.sources) != len(metadata["sources"]):
        parser.error(f"Expected {len(metadata['sources'])} source photographs in manifest order")
    images = []
    for path, source in zip(args.sources, metadata["sources"]):
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Expected the original {source['name']}")
        images.append(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))
    size = metadata["tileSize"]
    if size <= 0 or size & (size - 1):
        raise ValueError("Cirrus tile size must be a positive power of two")
    columns = 1
    while columns * columns < len(metadata["patches"]):
        columns += 1
    rows = (len(metadata["patches"]) + columns - 1) // columns
    geometry = encode_geometry(metadata, images, columns, rows)
    atlas = np.zeros((size * rows, size * columns), dtype=np.float32)
    for index, patch in enumerate(metadata["patches"]):
        row, column = divmod(index, columns)
        atlas[row * size:(row + 1) * size, column * size:(column + 1) * size] = extract_patch(
            images[patch["source"]], patch, size)
    data = encode_dds(atlas)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    args.geometry_output.parent.mkdir(parents=True, exist_ok=True)
    args.geometry_output.write_text(geometry)
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.uint8(np.rint(atlas * 255))).save(args.preview)
    print(f"{hashlib.sha256(data).hexdigest()}  {args.output}")


if __name__ == "__main__":
    main()
