#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""Render a repeatable visual matrix for low-cloud morphology changes.

This is an offline production-shader preview, not a Minecraft frame capture.
It renders the same camera, sun, transport quality and exposure for each
weather preset so reviewers can compare cloud organization without changing
the renderer or presentation settings between cases.
"""
import argparse
from pathlib import Path
import subprocess
import sys


SCENARIOS = (
    ("fair_broken", 0.45, 0.0, 0.0,
     "Broken fair-weather cumulus"),
    ("cloud_rich", 0.85, 0.0, 0.0,
     "Cloud-rich fair-weather sky"),
    ("mixed_clouds", 0.72, 0.25, 0.0,
     "Mixed cumulus and stratiform development"),
    ("stratiform_deck", 0.82, 0.65, 0.0,
     "Cloud-rich stratiform deck"),
    ("storm_transition", 0.85, 1.0, 0.45,
     "Rain and thunder transition"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shader-root", type=Path,
                        help="Candidate shader root; defaults to the repository checkout")
    parser.add_argument("--reference-shader-root", type=Path,
                        help="Optional baseline shader root for a fixed-input A/B matrix")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--atmosphere-fixture", type=Path)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=288)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--skip-radiance", action="store_true",
                        help="Render opacity only when no atmosphere fixture is available")
    args = parser.parse_args()

    preview = Path(__file__).with_name("render_cloud_preview.py")
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.cache_dir or args.output / "texture-cache"

    variants = [("candidate", args.shader_root)]
    if args.reference_shader_root:
        variants.insert(0, ("reference", args.reference_shader_root))

    for variant, shader_root in variants:
        for name, coverage, weather, thunder, label in SCENARIOS:
            destination = args.output / variant / name if args.reference_shader_root else args.output / name
            command = [
                sys.executable, str(preview),
                "--repo", str(args.repo),
                "--output", str(destination),
                "--cache-dir", str(cache),
                "--label", variant + ": " + label,
                "--width", str(args.width),
                "--height", str(args.height),
                "--repeat", str(args.repeat),
                "--warmup",
                "--views", "top,zenith,45,horizon,zenith90",
                "--layers", "low",
                "--low-base", "800",
                "--low-thickness", "1500",
                "--low-shape-scale", "1024",
                "--low-extinction", "0.03",
                "--low-coverage", str(coverage),
                "--weather", str(weather),
                "--thunder", str(thunder),
                "--sun-elevation", "35",
                "--sun-azimuth", "20",
                "--exposure", "1.0",
                "--tone-map", "aces",
                "--steps", "384",
                "--light-steps", "16",
                "--radiance",
            ]
            if shader_root:
                command.extend(["--shader-root", str(shader_root)])
            if args.atmosphere_fixture:
                command.extend(["--atmosphere-fixture", str(args.atmosphere_fixture), "--air"])
            elif args.skip_radiance:
                command.remove("--radiance")
            print("\n=== {}/{}: coverage={}, weather={}, thunder={} ===".format(
                variant, name, coverage, weather, thunder), flush=True)
            subprocess.run(command, check=True)

    print(f"\nCloud morphology matrix saved under {args.output}", flush=True)


if __name__ == "__main__":
    main()
