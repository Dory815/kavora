# Cirrus morphology input

`cirrus_density.dds` is a linear scalar morphology atlas used once when the
native cloud weather texture is generated. It is not a sky photograph or an
illuminated cloud sprite. The weather alpha channel supplies density to the
same extinction and scattering functions as the rest of the cloud volume.

## Sources and reproduction

The three original photographs, source-page revisions, author names and
SHA-256 hashes are recorded in [cirrus_sources.json](cirrus_sources.json).
All three photographs were released under CC0. The shipped
[notice](../licenses/Cirrus-CC0.txt) credits them and describes the derivative.

Download the original JPEG files from the URLs in that manifest. With NumPy
and Pillow installed, supply them in manifest order:

```sh
python prepare_cirrus_density.py \
  /path/to/Cirrus_clouds_Haukipudas_Oulu_20170611.jpg \
  /path/to/Cirrus_from_Shorncliffe_Pier_Moora_Park_Shorncliffe_P1120160.jpg \
  /path/to/Cirrus_74_Sunbury_Street_Geebung_P1130433.jpg \
  --output cirrus_density.dds --preview /tmp/cirrus-density.png
```

The tool validates each original before processing. It does not download
anything and is not run by Gradle or at game startup. The committed DDS is
1024 by 1024, R8_UNORM, with eleven box-filtered mip levels: 1,398,249 bytes
including its header. Its SHA-256 is
`9729908fe1dbb72ec76aee09930d228750c57ecf1f69a0079886bfa067fdbdd2`.

## Extraction and interpretation

Four small groups were selected where blue-sky gaps bound their natural
filaments. The first selection follows a blue gap above a separate cloud
bank. An explicit mask removes foreground leaves at the upper-left corner
of the third selection. The selected regions exclude the photographs'
landscape and lens flare.

The tool linearizes the camera RGB values, fits a smooth local clear-sky
red/blue ratio from the crop border, rejects cloud outliers, and subtracts
the estimated camera-noise floor. The remaining colour excess defines a
nonnegative scalar. One scale is shared by all patches; no patch is
normalized to an arbitrary peak. Clear-sky padding and a small denoise
filter prevent quantization residue from forming tile borders.

This is a relative shape estimate. A single processed JPEG cannot determine
cloud optical depth, particle phase function or three-dimensional geometry.
Exposure and camera processing also limit the interpretation of its scalar
values. The atlas does not preserve RGB, the original sun colour or a baked
scattering solution. Its height profile, extinction and lighting are supplied
by the native physical volume model. Local perspective within each small
crop remains an approximation; the complete photographed sky is never tiled.

## Atlas contract

Tiles are arranged in reading order. Their square storage does not stretch
the world-space cloud: `cloud_shape.slang` restores each crop's width/height
ratio when placing it, and aligns its long axis with the regional flow.
`flowAngle` in the manifest records the corresponding authored orientation.

| Tile | Source | World width / height | Flow angle, radians |
| --- | --- | --- | --- |
| 0 | Estormiz | 0.8636364 | 1.21 |
| 1 | McPherson P1120160 | 2.2222222 | 0.11 |
| 2 | McPherson P1130433 | 0.4256757 | -1.42 |
| 3 | McPherson P1130433 | 0.7875000 | 1.40 |

Regional placement varies location, size, heading and transverse reflection.
A separate regional humidity field leaves contiguous clear areas. The
finished field is baked into the existing weather texture, including its
mip chain. Runtime rays sample that field once for the high layer; they
never sample the atlas or execute the placement loop.

When changing the manifest, inspect the derived scalar image for foreground,
border and noise artifacts, then inspect production-shader perspective views
from multiple world positions. Update the shader's tile metadata with any
changed crop bounds. Use independent natural photographs to judge feather
structure and whole-sky distribution; the source crops alone cannot validate
their placement or illumination. See the shared
[rendering diagnostics guide](../../../docs/RENDERING_DIAGNOSTICS.md).
