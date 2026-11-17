# SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
# SPDX-License-Identifier: MIT
"""CPU contract for standard-mode atmosphere checkpoint placement."""
import math
import unittest

CAPACITY = 6


def checkpoint_max_distance(froxel_distance, clouds_enabled, low_active,
                            high_active, low_distance, high_distance):
    distance = froxel_distance
    if clouds_enabled:
        if low_active:
            distance = max(distance, low_distance)
        if high_active:
            distance = max(distance, high_distance)
    return max(distance, 1e-3)


def cloud_checkpointing_enabled(froxel_distance, clouds_enabled, low_active,
                                 high_active, low_distance, high_distance):
    return checkpoint_max_distance(froxel_distance, clouds_enabled, low_active,
                                   high_active, low_distance, high_distance) > froxel_distance


def checkpoint_distance(index, maximum, exponent):
    return (index / CAPACITY) ** exponent * maximum


def checkpoint_for_distance(distance, maximum, exponent):
    w = min(1.0, max(0.0, distance / maximum)) ** (1.0 / exponent)
    index = min(CAPACITY, math.floor(w * CAPACITY))
    if index > 0 and checkpoint_distance(index, maximum, exponent) > distance:
        index -= 1
    return index


class AtmosphereCheckpointCoverageTests(unittest.TestCase):
    def test_active_cloud_range_is_covered(self):
        maximum = checkpoint_max_distance(24_000, True, True, True, 96_000, 80_000)
        self.assertEqual(maximum, 96_000)
        self.assertEqual(checkpoint_distance(CAPACITY, maximum, 4), 96_000)
        self.assertEqual(checkpoint_for_distance(96_000, maximum, 4), CAPACITY)

    def test_empty_clouds_keep_froxel_range(self):
        self.assertEqual(
            checkpoint_max_distance(24_000, True, False, False, 96_000, 80_000),
            24_000,
        )
        self.assertEqual(
            checkpoint_max_distance(24_000, False, True, True, 96_000, 80_000),
            24_000,
        )

    def test_cloud_range_inside_froxel_keeps_legacy_mapping(self):
        self.assertFalse(cloud_checkpointing_enabled(24_000, True, True, True, 16_000, 20_000))
        self.assertFalse(cloud_checkpointing_enabled(24_000, False, True, True, 96_000, 80_000))

    def test_checkpoint_selection_never_passes_endpoint(self):
        maximum = 96_000
        exponent = 4
        for index in range(1_001):
            distance = maximum * index / 1_000
            checkpoint = checkpoint_for_distance(distance, maximum, exponent)
            self.assertLessEqual(checkpoint_distance(checkpoint, maximum, exponent),
                                 distance + 1e-7)

    def test_full_cloud_ray_has_no_dense_cloud_tail(self):
        maximum = 96_000
        exponent = 4
        checkpoint = checkpoint_for_distance(maximum, maximum, exponent)
        begin = checkpoint_distance(checkpoint, maximum, exponent)
        self.assertEqual(checkpoint, CAPACITY)
        self.assertEqual(begin, maximum)
        self.assertEqual(maximum - begin, 0)

    def test_sparse_checkpoint_intervals_are_monotonic_and_bounded(self):
        maximum = 96_000
        exponent = 4
        distances = [checkpoint_distance(i, maximum, exponent)
                     for i in range(CAPACITY + 1)]
        self.assertEqual(distances, sorted(distances))
        gaps = [b - a for a, b in zip(distances, distances[1:])]
        expected_largest_gap = maximum * (1.0 - (1.0 - 1.0 / CAPACITY) ** exponent)
        self.assertAlmostEqual(max(gaps), expected_largest_gap)
        self.assertAlmostEqual(distances[-1], maximum)


if __name__ == "__main__":
    unittest.main(verbosity=2)
