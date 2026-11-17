# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""CPU-only tests of the visual comparison plan, not of rendered image quality."""
from pathlib import Path
import tempfile
import json
import subprocess
from unittest.mock import patch

import render_cloud_morphology_matrix as matrix
import unittest

from render_cloud_morphology_matrix import LOCATIONS, SCENARIOS, parser, plan


class MatrixPlanTests(unittest.TestCase):
    def args(self, *extra):
        return parser().parse_args(["--output", "scratch", *extra])

    def test_default_covers_regions_weather_and_lighting(self):
        cases = plan(self.args())
        self.assertEqual(len(cases), 4 * 4 * 5)
        self.assertEqual({case["location"] for case in cases}, set(LOCATIONS))
        self.assertEqual({case["scenario"] for case in cases}, {row[0] for row in SCENARIOS})
        self.assertTrue(all(case["status"] == "planned" for case in cases))
        for case in cases:
            command = case["command"]
            self.assertEqual(command[command.index("--layers") + 1], "both")
            self.assertIn("zenith", command[command.index("--views") + 1].split(","))
            self.assertEqual(command[command.index("--steps") + 1], "384")

    def test_reference_uses_matching_support_and_same_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            support = root / "kavora-runtime/tests/rtx/unit/test_cloud_transport.py"
            support.parent.mkdir(parents=True)
            support.write_text("# fixture")
            shaders = root / "kavora-runtime/src/dxvk/shaders"
            cases = plan(self.args("--reference-shader-root", str(shaders),
                                   "--locations", "user", "--scenarios", "cloud_rich"))
            self.assertEqual(len(cases), 8)
            for old, new in zip(cases[:4], cases[4:]):
                reference = Path(old["command"][old["command"].index("--repo") + 1])
                self.assertEqual(reference.resolve(), root.resolve())
                for option in ("--origin", "--low-coverage", "--steps", "--light-steps",
                               "--layers", "--low-max-distance", "--high-max-distance", "--sun-elevation"):
                    self.assertEqual(old["command"][old["command"].index(option) + 1],
                                     new["command"][new["command"].index(option) + 1])

    def test_atmosphere_fixture_does_not_get_conflicting_sun_arguments(self):
        cases = plan(self.args("--atmosphere-fixture", "fixture", "--locations", "user"))
        self.assertEqual(len(cases), 5)
        for case in cases:
            self.assertIn("--air", case["command"])
            self.assertIn("--radiance", case["command"])
            self.assertNotIn("--sun-elevation", case["command"])
            self.assertNotIn("--sun-azimuth", case["command"])

    def test_invalid_inputs_are_rejected(self):
        for arguments in (("--locations", "user,user"), ("--views", "missing"),
                          ("--scenarios", "missing"), ("--width", "0"),
                          ("--steps", "0"), ("--lighting-cases", "../escape:35:0"),
                          ("--lighting-cases", "bad:nan:0"), ("--low-max-distance", "nan"),
                          ("--lighting-cases", "same:35:0,same:30:90"),
                          ("--atmosphere-fixture", "fixture", "--skip-radiance")):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                plan(self.args(*arguments))

    def test_failed_or_stale_render_is_never_marked_complete(self):
        for failure in (subprocess.CalledProcessError(1, "renderer"),
                        subprocess.TimeoutExpired("renderer", 1), None):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                args = self.args("--output", directory, "--locations", "user",
                                 "--scenarios", "cloud_rich", "--lighting-cases", "day:35:0")
                case = plan(args)[0]
                destination = Path(case["output"])
                destination.mkdir(parents=True)
                (destination / "manifest.json").write_text(json.dumps({
                    "views": {view: {} for view in args.views.split(",")}}))
                with patch.object(
                        matrix, "parser", return_value=unittest.mock.Mock(parse_args=lambda: args)), \
                        patch.object(matrix.subprocess, "run", side_effect=failure):
                    with self.assertRaises(Exception):
                        matrix.main()
                result = json.loads((Path(directory) / "matrix.json").read_text())
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["cases"][0]["status"], "failed")
                self.assertTrue((destination / "render.log").exists())


    def test_opacity_mode_omits_radiance(self):
        self.assertTrue(all("--radiance" not in case["command"]
                            for case in plan(self.args("--skip-radiance"))))


if __name__ == "__main__":
    unittest.main()
