# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: Apache-2.0

"""Extract a scalar cirrus morphology atlas from the three credited CC0 photos.

This is an offline asset preparation tool, not part of the build. Input paths
follow the source order in cirrus_sources.json. Requires NumPy and Pillow.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


DIRECTORY = Path(__file__).resolve().parent


def extract_patch(image, patch, size):
    left, top, right, bottom = patch["bounds"]
    crop = image.crop(tuple(round(p * s) for p, s in zip(
        patch["bounds"], (image.width, image.height, image.width, image.height))))
    rgb = np.asarray(crop.resize((size, size), Image.Resampling.LANCZOS), dtype=np.float64) / 255
    rgb = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    ratio = rgb[..., 0] / np.maximum(rgb[..., 2], 1e-5)
    y, x = np.mgrid[-1:1:complex(0, size), -1:1:complex(0, size)]
    fit = np.stack([x, y, x * y, x * x, y * y, np.ones_like(x)], -1)
    border = np.maximum(np.abs(x), np.abs(y)) > 0.80
    valid = (rgb[..., 2] > 0.08) & (ratio < 0.8)
    clear = border & valid
    # Reject bright cloud outliers while fitting the blue-sky colour gradient.
    for _ in range(4):
        coefficients = np.linalg.lstsq(fit[clear], ratio[clear], rcond=None)[0]
        residual = ratio - fit @ coefficients
        tolerance = max(0.003, np.percentile(np.abs(residual[clear]), 65) * 2)
        clear = border & valid & (residual < tolerance)
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
    size = atlas.shape[0]
    mip_count = size.bit_length()
    # DX10 R8_UNORM stores linear relative density, with no RGB or sRGB decode.
    header = [124, 0x2100F, size, size, size, 0, mip_count] + [0] * 11
    header += [32, 4, int.from_bytes(b"DX10", "little"), 0, 0, 0, 0, 0]
    header += [0x401008, 0, 0, 0, 0]
    data = bytearray(b"DDS " + struct.pack("<31I", *header) + struct.pack("<5I", 61, 3, 0, 1, 0))
    for level in range(mip_count):
        data.extend(np.uint8(np.rint(atlas * 255)).tobytes())
        if level + 1 < mip_count:
            atlas = atlas.reshape(atlas.shape[0] // 2, 2, atlas.shape[1] // 2, 2).mean(axis=(1, 3))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs=3, type=Path, metavar="PHOTO")
    parser.add_argument("--output", type=Path, default=DIRECTORY / "cirrus_density.dds")
    parser.add_argument("--preview", type=Path, help="Optional scalar PNG for visual inspection")
    args = parser.parse_args()
    metadata = json.loads((DIRECTORY / "cirrus_sources.json").read_text())
    images = []
    for path, source in zip(args.sources, metadata["sources"]):
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"Expected the original {source['name']}")
        images.append(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))
    size = metadata["tileSize"]
    atlas = np.zeros((size * 2, size * 2), dtype=np.float32)
    for index, patch in enumerate(metadata["patches"]):
        row, column = divmod(index, 2)
        atlas[row * size:(row + 1) * size, column * size:(column + 1) * size] = extract_patch(
            images[patch["source"]], patch, size)
    data = encode_dds(atlas)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.uint8(np.rint(atlas * 255))).save(args.preview)
    print(f"{hashlib.sha256(data).hexdigest()}  {args.output}")


if __name__ == "__main__":
    main()
