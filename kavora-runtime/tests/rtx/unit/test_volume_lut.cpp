// SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
// SPDX-License-Identifier: MIT
#include <array>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <random>
#include <vector>

#include "rtx/utility/volume_lut.h"

static void require(bool pass, const char* message) {
  if (!pass) {
    std::cerr << message << '\n';
    std::exit(1);
  }
}

int main() {
  using namespace dxvk;
  unsigned cases = 0;
  double maximumError = 0.0;
  for (float depth : {0.0f, 1e-10f, 1e-6f, 0.001f, 0.01f, 0.1f, 1.0f, 10.0f, 80.0f, 1000.0f}) {
    for (unsigned i = 0; i <= 100; ++i) {
      const float fraction = float(i) / 100.0f;
      const double expected = depth == 0.0f ? fraction
        : -std::expm1(-double(depth) * fraction) / -std::expm1(-double(depth));
      const float actual = volumeLutWeight(depth, fraction);
      maximumError = std::max(maximumError, std::abs(double(actual) - expected));
      require(std::isfinite(actual) && actual >= 0.0f && actual <= 1.0f, "invalid optical interpolation");
      require(std::abs(actual - expected) < 2e-5, "optical interpolation differs from independent expm1 reference");
      ++cases;
    }
    require(volumeLutWeight(depth, 0) == 0 && volumeLutWeight(depth, 1) == 1, "inexact endpoints");
  }
  for (float end : {0.001f, 20.0f, 1700.0f, 24000.0f, 96000.0f, 1500000.0f}) {
    for (float scale : {0.1f, 1.0f, 8.0f, 20.0f}) {
      float previous = 0.0f;
      for (unsigned i = 1; i <= 96; ++i) {
        const float fraction = float(i) / 96.0f;
        const float distance = volumeLutDistance(fraction, end, scale);
        require(distance > previous && distance <= end, "nonmonotone LUT grid");
        require(std::abs(volumeLutCoordinate(distance, end, scale) - fraction) < 2e-5f, "grid inverse mismatch");
        previous = distance;
        ++cases;
      }
      require(previous == end, "terminal distance must be exact");
    }
  }
  // Each light schedule uses the same code and node budget, including an opaque prefix.
  for (float radiance : {0.0f, 0.001f, 0.1f, 1.0f, 100.0f}) {
    for (float prefix : {0.0f, 0.01f, 1.0f, 10.0f, 1000.0f}) {
      for (float cell : {0.0001f, 0.1f, 1.0f, 10.0f}) {
        const float from = radiance * volumeLutOpacity(prefix);
        const float to = from + std::exp(-prefix) * radiance * volumeLutOpacity(cell);
        for (float f : {0.0f, 0.001f, 0.5f, 0.999f, 1.0f}) {
          const float actual = volumeLutRadiance(from, to, prefix, prefix + cell, f);
          const double expected = from + std::exp(-double(prefix)) * radiance * -std::expm1(-double(cell) * f);
          require(std::isfinite(actual), "opaque prefix produced NaN");
          require(std::abs(actual - expected) < 3e-5 * std::max(1.0f, radiance), "homogeneous transfer interpolation mismatch");
          ++cases;
        }
      }
    }
  }
  std::mt19937 random(20261117);
  std::uniform_real_distribution<float> uniform(0.0f, 1.0f);
  for (unsigned scenario = 0; scenario < 4096; ++scenario) {
    VolumeLutIntervals intervals = {};
    const float reach = std::pow(10.0f, -2.0f + 8.0f * uniform(random));
    for (unsigned medium = 0; medium < 7; ++medium) {
      intervals.starts[medium] = reach * uniform(random);
      intervals.ends[medium] = intervals.starts[medium] + reach * uniform(random);
    }
    VolumeLutGrid grid = createVolumeLutGrid(intervals, 1.0f);
    std::vector<float> knots{0.0f};
    float previous = 0.0f;
    for (unsigned node = 1; node <= 64; ++node) {
      const float next = grid.next(intervals, previous, 64);
      require(next >= previous && next <= grid.end, "merged grid has invalid node");
      require(next > previous || next == grid.end, "merged grid stalled");
      knots.push_back(next);
      previous = next;
    }
    require(previous == grid.end, "merged grid did not cover full atmosphere within budget");
    for (unsigned medium = 0; medium < 7; ++medium) {
      require(std::find(knots.begin(), knots.end(), intervals.starts[medium]) != knots.end(), "missing interval entry");
      require(std::find(knots.begin(), knots.end(), intervals.ends[medium]) != knots.end(), "missing interval exit");
    }
    ++cases;
  }
  std::cout << "PASS " << cases << " shared C++/Slang LUT scalar cases; max weight error " << maximumError << '\n';
}
