// SPDX-FileCopyrightText: Copyright (c) 2026 Kavora contributors
// SPDX-License-Identifier: MIT
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>
#include "rtx/utility/cloud_source_lut.h"

static void require(bool pass, const char* message) {
  if (!pass) {
    std::cerr << message << '\n';
    std::exit(1);
  }
}

int main() {
  using namespace dxvk;
  unsigned checks = 0;
  for (unsigned quality : {0u, 4u, 8u, 12u, 16u, 32u}) {
    const unsigned n = cloudSourceResolution(quality);
    const unsigned width = cloudSourceAtlasWidth(n), height = cloudSourceAtlasHeight(n);
    std::vector<bool> occupied(width * height, false);
    for (unsigned component = 0; component < CLOUD_SOURCE_COMPONENTS; ++component)
      for (unsigned cascade = 0; cascade < CLOUD_SOURCE_CASCADES; ++cascade)
        for (unsigned z = 0; z < CLOUD_SOURCE_VERTICAL_NODES; ++z)
          for (unsigned y = 0; y < n; ++y)
            for (unsigned x = 0; x < n; ++x) {
              const unsigned ax = cloudSourceAtlasX(x, z, n);
              const unsigned ay = cloudSourceAtlasY(y, cascade, component, n);
              require(ax < width && ay < height && ay != 0, "atlas coordinate out of bounds or touches ambient row");
              require(!occupied[ay * width + ax], "atlas fields alias");
              occupied[ay * width + ax] = true;
              ++checks;
            }
    require(!occupied[0], "ambient quadrature header overwritten");
  }
  require(cloudSourceAtlasWidth(0) == 1 && cloudSourceAtlasHeight(0) == 1, "reference mode allocation changed");
  for (float g : {0.0f, 0.5f, 0.85f, 0.95f}) {
    for (unsigned angle = 0; angle <= 1000; ++angle) {
      const double cosine = -1.0 + 2.0 * angle / 1000.0;
      auto hg = [cosine](double anisotropy) {
        const double denominator = std::max(0.001, 1.0 + anisotropy * anisotropy - 2.0 * anisotropy * cosine);
        return (1.0 - anisotropy * anisotropy) / (4.0 * std::acos(-1.0) * std::pow(denominator, 1.5));
      };
      const double expected = 0.85 * hg(g) + 0.15 * hg(-0.25);
      const float phase = cloudSourcePhase(float(cosine), g);
      require(std::abs(phase - expected) < 1e-4 * std::max(1.0, expected), "directional phase changed");
      for (float transmission : {0.0f, 0.001f, 0.5f, 1.0f}) {
        const float beam = 100.0f, diffuse = 0.7f;
        const float before = beam * (phase * transmission + diffuse);
        const float factored = beam * transmission * phase + beam * diffuse;
        require(std::abs(before - factored) < 1e-5f * std::max(before, 1.0f), "source decomposition changed energy");
        ++checks;
      }
    }
  }
  double worst = 0;
  for (float radius : {6000000.0f, 6371000.0f, 7000000.0f})
    for (float altitude : {200.0f, 800.0f, 2300.0f, 6375.0f, 6425.0f})
      for (float x : {-96000.0f, -24000.0f, -1.0f, 0.0f, 24000.0f, 96000.0f})
        for (float z : {-96000.0f, 0.0f, 96000.0f}) {
          const float horizontal = x * x + z * z;
          const float y = cloudSourcePlaneHeight(radius, horizontal, altitude);
          const double actual = std::sqrt(double(horizontal) + std::pow(double(radius) + y, 2)) - radius;
          worst = std::max(worst, std::abs(actual - altitude));
          require(std::abs(actual - altitude) < 0.002, "curved cloud lattice leaves cloud altitude");
          ++checks;
        }
  for (float range : {1000.0f, 24000.0f, 96000.0f}) {
    float previous = 0;
    for (unsigned cascade = 0; cascade < CLOUD_SOURCE_CASCADES; ++cascade) {
      const float r = cloudSourceRadius(2048, range, cascade);
      require(r >= previous && r <= std::max(range, 8192.0f), "invalid cascade radius");
      previous = r;
      ++checks;
    }
  }
  std::cout << "PASS " << checks << " source-atlas layout/curvature cases; max altitude error " << worst << " m\n";
}
