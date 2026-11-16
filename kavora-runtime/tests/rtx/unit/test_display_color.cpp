// SPDX-FileCopyrightText: Copyright (c) 2026 GBwater
// SPDX-License-Identifier: MIT
#include "../../../src/dxvk/shaders/dxvk_display_color.h"

#include <array>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace dxvk::display_color;

static void require(bool condition, const char* message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

int main() {
  for (const float value : {-16.0f, -1.0f, -0.04045f, -0.0031308f, -1e-8f,
      0.0f, 1e-8f, 0.0031308f, 0.04045f, 0.18f, 1.0f, 4.0f, 16.0f}) {
    require(std::abs(displaySrgbDecode(displaySrgbEncode(value)) - value)
      <= 2e-6f * std::max(1.0f, std::abs(value)), "extended sRGB round trip");
  }
  require(std::abs(displaySrgbEncode(0.0031308f) - 0.040449936f) < 1e-7f, "sRGB toe");

  const std::array<std::array<float, 2>, 6> pq = {{
    {0.0f, 0.000000730956f}, {1.0f, 0.1499457321f}, {100.0f, 0.5080784215f},
    {203.0f, 0.5806888810f}, {1000.0f, 0.7518270962f}, {10000.0f, 1.0f}
  }};
  for (const auto& sample : pq) {
    require(std::abs(displayPqEncodeNits(sample[0]) - sample[1]) < 2e-5f, "PQ display-nits reference");
  }
  const Rgb white = displayRec709ToRec2020(Rgb(1, 1, 1));
  require(std::abs(white.x - 1) < 1e-6f && std::abs(white.y - 1) < 1e-6f
    && std::abs(white.z - 1) < 1e-6f, "D65 white preservation");

  for (const float peak : {1.0f, 2.0f, 5.0f, 10.0f, 50.0f}) {
    float previous = 0.0f;
    for (int i = 0; i <= 2048; i++) {
      const float input = std::exp2(-24.0f + float(i) * 40.0f / 2048.0f);
      const Rgb output = displayHdrShoulder(Rgb(input, 0.5f * input, 0.125f * input), peak);
      require(std::isfinite(output.x) && output.x >= previous && output.x <= peak, "HDR shoulder bounds");
      require(std::abs(output.y - output.x * 0.5f) < 2e-6f
        && std::abs(output.z - output.x * 0.125f) < 2e-6f, "HDR color ratios");
      if (input <= 1.0f) {
        require(output.x == input, "HDR paper-white range");
      }
      previous = output.x;
    }
    const Rgb sdrPeak = displaySdrShoulder(Rgb(peak, peak, peak), peak);
    require(std::abs(sdrPeak.x - 1) < 1e-6f, "SDR fallback peak");
  }
  const Rgb sanitized = displaySanitizeColor(Rgb(-1, std::numeric_limits<float>::infinity(),
    std::numeric_limits<float>::quiet_NaN()));
  require(sanitized.x == 0 && sanitized.y == 0 && sanitized.z == 0, "invalid display inputs");
  std::cout << "PASS shared display math: transfer, PQ nits, white, monotonic shoulders and color ratios\n";
}
